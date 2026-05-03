"""Pydantic AST for the BnK BRD v2 template.

One Pydantic model per template section. Field names match the docxtpl
variables in `templates/brd/BnK_BRD_Template_v2.0_*.docx`. Changing a field
here requires updating both the template AND `operations.py` in the same
commit.

Section-to-model mapping:
  Cover               → BRDDocument top-level scalars
  Document Info       → BRDDocument.version_history
  §1 Introduction     → BRDDocument.purpose, .intended_audience
  §2 Business Context → .background, .objectives, .constraints, .assumptions
  §3 Project Scope    → .scope_in, .scope_out
  §4 Stakeholders     → .stakeholders
  §5 Business Reqs    → .functional_requirements, .nfr_rows,
                        .data_requirements, .integrations
  §6 Acceptance       → .acceptance_criteria
  §7 Glossary         → .glossary
  §8 Appendix         → .appendix
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

# ── Type aliases ─────────────────────────────────────────────────────────────

Language = Literal["en", "vi", "ja", "zh"]
Priority = Literal["Critical", "High", "Medium", "Low", "Future"]
Direction = Literal["Inbound", "Outbound", "Bidirectional"]


def _new_id() -> str:
    return str(uuid.uuid4())


# ── Section row models ───────────────────────────────────────────────────────

class VersionEntry(BaseModel):
    """One row in the Document Information / Version History table."""
    version: str
    date: str
    description: str
    author: str


class AudienceEntry(BaseModel):
    """One row in §1.2 Intended Audience table."""
    role: str
    party: str
    responsibility: str


class Stakeholder(BaseModel):
    """One row in §4 Stakeholders table."""
    id: str
    name: str
    role: str
    responsibility: str


class FunctionalRequirement(BaseModel):
    """One Functional Requirement (used in both §5.1 overview table
    and §5.2 detail loop)."""
    section_id: str = Field(default_factory=_new_id)
    fr_id: str                 # "FR1", "FR2", ...
    name: str
    priority: Priority = "Medium"
    short_description: str = ""
    description: str = ""
    user_stories: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    interface_notes: str = ""


class NFRRow(BaseModel):
    """One row in §5.3 Non-Functional Requirements table."""
    category: str              # Performance, Scalability, Availability, ...
    metric: str
    target: str                # MUST include unit (ms, %, req/s, ...)


class IntegrationRow(BaseModel):
    """One row in §5.5 Integration Requirements table."""
    system: str
    direction: Direction = "Inbound"
    protocol: str              # REST, gRPC, LDAP, S3, ...
    note: str = ""


class GlossaryEntry(BaseModel):
    """One row in §7 Glossary table."""
    term: str
    definition: str


# ── Section sub-models (each persists to its own file in BRDStore) ───────────
#
# These mirror BRDDocument fields, grouped by template section. The store
# layer reads/writes one section at a time, then `BRDDocument` is re-assembled
# only at render/validation time.

class MetadataSection(BaseModel):
    """Cover-page + version-history fields. → 00_metadata.json"""
    project_name: str = ""
    project_code: str = ""
    version: str = "0.1.0"
    author: str = "BnK Solution"
    created_at: str = Field(default_factory=lambda: date.today().isoformat())
    language: Language = "en"
    version_history: list[VersionEntry] = Field(default_factory=list)


class IntroductionSection(BaseModel):
    """§1 Introduction. → 01_introduction.json"""
    purpose: str = ""
    intended_audience: list[AudienceEntry] = Field(default_factory=list)


class ContextSection(BaseModel):
    """§2 Business Context. → 02_context.json"""
    background: str = ""
    objectives: str = ""
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class ScopeSection(BaseModel):
    """§3 Project Scope. → 03_scope.json"""
    scope_in: list[str] = Field(default_factory=list)
    scope_out: list[str] = Field(default_factory=list)


class StakeholdersSection(BaseModel):
    """§4 Stakeholders. → 04_stakeholders.json"""
    stakeholders: list[Stakeholder] = Field(default_factory=list)


class NFRSection(BaseModel):
    """§5.3 Non-Functional Requirements. → 05_3_nfr.json"""
    nfr_rows: list[NFRRow] = Field(default_factory=list)


class DataReqSection(BaseModel):
    """§5.4 Data Requirements. → 05_4_data.json"""
    data_requirements: str = ""


class IntegrationsSection(BaseModel):
    """§5.5 Integration Requirements. → 05_5_integrations.json"""
    integrations: list[IntegrationRow] = Field(default_factory=list)


class AcceptanceSection(BaseModel):
    """§6 Acceptance Criteria. → 06_acceptance.json"""
    acceptance_criteria: list[str] = Field(default_factory=list)


class GlossarySection(BaseModel):
    """§7 Glossary & Abbreviations. → 07_glossary.json"""
    glossary: list[GlossaryEntry] = Field(default_factory=list)
    abbreviations: list[GlossaryEntry] = Field(default_factory=list)


class AppendixSection(BaseModel):
    """§8 Appendix. → 08_appendix.json"""
    appendix: str = ""
    appendix_items: list[str] = Field(default_factory=list)


# ── Root model ───────────────────────────────────────────────────────────────

class BRDDocument(BaseModel):
    """Root BRD AST. Filled by brd_drafter agent, rendered by exporter."""

    # ── Metadata (cover + doc info) ──────────────────────────────────────────
    project_name: str
    project_code: str
    version: str = "0.1.0"
    author: str = "BnK Solution"
    created_at: str = Field(default_factory=lambda: date.today().isoformat())
    language: Language = "en"
    version_history: list[VersionEntry] = Field(default_factory=list)

    # ── §1 Introduction ──────────────────────────────────────────────────────
    purpose: str = ""
    intended_audience: list[AudienceEntry] = Field(default_factory=list)

    # ── §2 Business Context ──────────────────────────────────────────────────
    background: str = ""
    objectives: str = ""
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)

    # ── §3 Project Scope ─────────────────────────────────────────────────────
    scope_in: list[str] = Field(default_factory=list)
    scope_out: list[str] = Field(default_factory=list)

    # ── §4 Stakeholders ──────────────────────────────────────────────────────
    stakeholders: list[Stakeholder] = Field(default_factory=list)

    # ── §5 Business Requirements ─────────────────────────────────────────────
    functional_requirements: list[FunctionalRequirement] = Field(default_factory=list)
    nfr_rows: list[NFRRow] = Field(default_factory=list)
    data_requirements: str = ""
    integrations: list[IntegrationRow] = Field(default_factory=list)

    # ── §6 Acceptance Criteria ───────────────────────────────────────────────
    acceptance_criteria: list[str] = Field(default_factory=list)

    # ── §7 Glossary & Abbreviations ──────────────────────────────────────────
    glossary: list[GlossaryEntry] = Field(default_factory=list)
    abbreviations: list[GlossaryEntry] = Field(default_factory=list)

    # ── §8 Appendix ──────────────────────────────────────────────────────────
    appendix: str = ""
    appendix_items: list[str] = Field(default_factory=list)
