"""Pure per-section CRUD operations on BRD sub-models.

Each function takes the **section sub-model** as its first argument (not the
full BRDDocument) so operations stay isolated and align 1:1 with the
section-sharded storage in `store.py`. Functions mutate in place and return
the (mutated) section for chaining.

Layout MIRRORS the template structure: one block per section.
Edit a section's behavior here — no need to touch tools/ or schema/ for
behavior-only changes.

Index:
  Cover / Doc Info     → set_metadata, add_version_entry, remove_version_entry
  §1 Introduction      → set_purpose,
                         add_audience_entry, upsert_audience_entry, remove_audience_entry
  §2 Business Context  → set_background, set_objectives,
                         add_constraint, remove_constraint,
                         add_assumption, remove_assumption
  §3 Project Scope     → add_scope_in, remove_scope_in,
                         add_scope_out, remove_scope_out
  §4 Stakeholders      → upsert_stakeholder, remove_stakeholder
  §5 Business Reqs     → upsert_nfr_row, remove_nfr_row,
                         set_data_requirements,
                         upsert_integration, remove_integration
                       (FR ops live in BRDStore — one file per FR)
  §6 Acceptance        → add_acceptance_criterion, remove_acceptance_criterion
  §7 Glossary          → upsert_glossary_entry, remove_glossary_entry,
                         upsert_abbreviation_entry, remove_abbreviation_entry
  §8 Appendix          → set_appendix, add_appendix_item
"""
from __future__ import annotations

from .schema import (
    AcceptanceSection,
    AppendixSection,
    AudienceEntry,
    ContextSection,
    DataReqSection,
    GlossaryEntry,
    GlossarySection,
    IntegrationRow,
    IntegrationsSection,
    IntroductionSection,
    Language,
    MetadataSection,
    NFRRow,
    NFRSection,
    ScopeSection,
    Stakeholder,
    StakeholdersSection,
    VersionEntry,
)


# ── Cover / Document Information ─────────────────────────────────────────────

def set_metadata(
    meta: MetadataSection,
    *,
    project_name: str | None = None,
    project_code: str | None = None,
    version: str | None = None,
    author: str | None = None,
    language: Language | None = None,
) -> MetadataSection:
    """Update one or more cover-page metadata fields."""
    if project_name is not None: meta.project_name = project_name
    if project_code is not None: meta.project_code = project_code
    if version       is not None: meta.version       = version
    if author        is not None: meta.author        = author
    if language      is not None: meta.language      = language
    return meta


def add_version_entry(meta: MetadataSection, entry: VersionEntry) -> MetadataSection:
    meta.version_history.append(entry)
    return meta


def remove_version_entry(meta: MetadataSection, version: str) -> MetadataSection:
    meta.version_history = [v for v in meta.version_history if v.version != version]
    return meta


# ── §1 Introduction ──────────────────────────────────────────────────────────

def set_purpose(intro: IntroductionSection, text: str) -> IntroductionSection:
    intro.purpose = text
    return intro


def add_audience_entry(intro: IntroductionSection, entry: AudienceEntry) -> IntroductionSection:
    intro.intended_audience.append(entry)
    return intro


def upsert_audience_entry(intro: IntroductionSection, entry: AudienceEntry) -> IntroductionSection:
    """Update by (role, party); append if missing."""
    for i, a in enumerate(intro.intended_audience):
        if a.role == entry.role and a.party == entry.party:
            intro.intended_audience[i] = entry
            return intro
    intro.intended_audience.append(entry)
    return intro


def remove_audience_entry(
    intro: IntroductionSection, role: str, party: str | None = None,
) -> IntroductionSection:
    intro.intended_audience = [
        a for a in intro.intended_audience
        if not (a.role == role and (party is None or a.party == party))
    ]
    return intro


# ── §2 Business Context ──────────────────────────────────────────────────────

def set_background(ctx: ContextSection, text: str) -> ContextSection:
    ctx.background = text
    return ctx


def set_objectives(ctx: ContextSection, text: str) -> ContextSection:
    ctx.objectives = text
    return ctx


def add_constraint(ctx: ContextSection, text: str) -> ContextSection:
    ctx.constraints.append(text)
    return ctx


def remove_constraint(ctx: ContextSection, index: int) -> ContextSection:
    if 0 <= index < len(ctx.constraints):
        ctx.constraints.pop(index)
    return ctx


def add_assumption(ctx: ContextSection, text: str) -> ContextSection:
    ctx.assumptions.append(text)
    return ctx


def remove_assumption(ctx: ContextSection, index: int) -> ContextSection:
    if 0 <= index < len(ctx.assumptions):
        ctx.assumptions.pop(index)
    return ctx


# ── §3 Project Scope ─────────────────────────────────────────────────────────

def add_scope_in(scope: ScopeSection, text: str) -> ScopeSection:
    scope.scope_in.append(text)
    return scope


def remove_scope_in(scope: ScopeSection, index: int) -> ScopeSection:
    if 0 <= index < len(scope.scope_in):
        scope.scope_in.pop(index)
    return scope


def add_scope_out(scope: ScopeSection, text: str) -> ScopeSection:
    scope.scope_out.append(text)
    return scope


def remove_scope_out(scope: ScopeSection, index: int) -> ScopeSection:
    if 0 <= index < len(scope.scope_out):
        scope.scope_out.pop(index)
    return scope


# ── §4 Stakeholders ──────────────────────────────────────────────────────────

def upsert_stakeholder(sec: StakeholdersSection, sh: Stakeholder) -> StakeholdersSection:
    """Update existing stakeholder by id, or append if id is new."""
    for i, existing in enumerate(sec.stakeholders):
        if existing.id == sh.id:
            sec.stakeholders[i] = sh
            return sec
    sec.stakeholders.append(sh)
    return sec


def remove_stakeholder(sec: StakeholdersSection, id: str) -> StakeholdersSection:
    sec.stakeholders = [s for s in sec.stakeholders if s.id != id]
    return sec


# ── §5.3 Non-Functional Requirements ─────────────────────────────────────────

def upsert_nfr_row(sec: NFRSection, nfr: NFRRow) -> NFRSection:
    """Update by (category, metric); append if missing."""
    for i, existing in enumerate(sec.nfr_rows):
        if existing.category == nfr.category and existing.metric == nfr.metric:
            sec.nfr_rows[i] = nfr
            return sec
    sec.nfr_rows.append(nfr)
    return sec


def remove_nfr_row(sec: NFRSection, category: str, metric: str) -> NFRSection:
    sec.nfr_rows = [
        n for n in sec.nfr_rows
        if not (n.category == category and n.metric == metric)
    ]
    return sec


# ── §5.4 Data Requirements ───────────────────────────────────────────────────

def set_data_requirements(sec: DataReqSection, text: str) -> DataReqSection:
    sec.data_requirements = text
    return sec


# ── §5.5 Integrations ────────────────────────────────────────────────────────

def upsert_integration(sec: IntegrationsSection, ig: IntegrationRow) -> IntegrationsSection:
    """Update by `system`; append if missing."""
    for i, existing in enumerate(sec.integrations):
        if existing.system == ig.system:
            sec.integrations[i] = ig
            return sec
    sec.integrations.append(ig)
    return sec


def remove_integration(sec: IntegrationsSection, system: str) -> IntegrationsSection:
    sec.integrations = [i for i in sec.integrations if i.system != system]
    return sec


# ── §6 Acceptance Criteria ───────────────────────────────────────────────────

def add_acceptance_criterion(sec: AcceptanceSection, text: str) -> AcceptanceSection:
    sec.acceptance_criteria.append(text)
    return sec


def remove_acceptance_criterion(sec: AcceptanceSection, index: int) -> AcceptanceSection:
    if 0 <= index < len(sec.acceptance_criteria):
        sec.acceptance_criteria.pop(index)
    return sec


# ── §7 Glossary & Abbreviations ──────────────────────────────────────────────

def upsert_glossary_entry(sec: GlossarySection, term: str, definition: str) -> GlossarySection:
    """Update by `term`; append if missing."""
    for i, g in enumerate(sec.glossary):
        if g.term == term:
            sec.glossary[i] = GlossaryEntry(term=term, definition=definition)
            return sec
    sec.glossary.append(GlossaryEntry(term=term, definition=definition))
    return sec


def remove_glossary_entry(sec: GlossarySection, term: str) -> GlossarySection:
    sec.glossary = [g for g in sec.glossary if g.term != term]
    return sec


def upsert_abbreviation_entry(sec: GlossarySection, term: str, definition: str) -> GlossarySection:
    """Update abbreviation by `term`; append if missing."""
    for i, a in enumerate(sec.abbreviations):
        if a.term == term:
            sec.abbreviations[i] = GlossaryEntry(term=term, definition=definition)
            return sec
    sec.abbreviations.append(GlossaryEntry(term=term, definition=definition))
    return sec


def remove_abbreviation_entry(sec: GlossarySection, term: str) -> GlossarySection:
    sec.abbreviations = [a for a in sec.abbreviations if a.term != term]
    return sec


# ── §8 Appendix ──────────────────────────────────────────────────────────────

def set_appendix(sec: AppendixSection, text: str) -> AppendixSection:
    """Set the appendix intro/description text."""
    sec.appendix = text
    return sec


def add_appendix_item(sec: AppendixSection, item: str) -> AppendixSection:
    """Append a named appendix item, e.g. 'Appendix A: Use Case Diagram'."""
    sec.appendix_items.append(item)
    return sec
