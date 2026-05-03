"""Agent tools for editing the BRD AST.

Section-sharded persistence via `packages.brd.BRDStore` (one file per section,
one file per FR). Each tool reads/writes ONLY the relevant section file,
saving ~95% tokens vs. the previous monolithic brd_state.json layout.

Per-section CRUD logic lives in `packages.brd.operations` — this module is
the agent-facing dispatcher.

Tool budget: **6** (within Rule §2 ≤8 per subagent).
  init_brd, set_brd_text, add_brd_list_item,
  upsert_brd_row, upsert_fr, get_brd_summary
"""
from __future__ import annotations

import json
from typing import Callable, Literal

from langchain_core.tools import tool
from pydantic import BaseModel

from packages.brd import (
    AudienceEntry,
    BRDStore,
    FunctionalRequirement,
    IntegrationRow,
    NFRRow,
    Stakeholder,
)
from packages.brd import operations as ops
from packages.wbs import WBSStore
from .workspace import get_workspace


# ── Cross-store relink helper (BRD rename → WBS task source_feature_id) ──────

def _relink_wbs_tasks(old_fr_id: str, new_fr_id: str) -> int:
    """Update every L4 WBS task whose source_feature_id == old_fr_id.

    Returns the number of tasks relinked. No-op if WBS not initialized.
    """
    wbs = WBSStore(get_workspace() / "wbs")
    if not wbs.is_initialized():
        return 0
    count = 0
    for code in wbs.list_task_codes():
        task = wbs.read_task(code)
        if task is not None and task.source_feature_id == old_fr_id:
            task.source_feature_id = new_fr_id
            wbs.write_task(task)
            count += 1
    return count


# ── Store accessor (resolves the per-session BRD root directory) ─────────────

def _store() -> BRDStore:
    """Return a BRDStore rooted at <session_workspace>/brd/."""
    return BRDStore(get_workspace() / "brd")


# ── Type aliases for tool args ───────────────────────────────────────────────

SCALAR_FIELD = Literal[
    "purpose", "background", "objectives", "data_requirements", "appendix",
]
LIST_FIELD = Literal[
    "constraints", "assumptions", "scope_in", "scope_out",
    "acceptance_criteria", "appendix_items",
]
TABLE_NAME = Literal[
    "intended_audience", "stakeholders", "nfr_rows", "integrations",
    "glossary", "abbreviations",
]


# ── Field → (section_id, operation) dispatch tables ──────────────────────────
# These bind the agent-facing field names to the correct section file and
# operations.py function. Add a new field by appending one row here.

# Each entry: scalar_field_name -> (section_id, ops_function_taking_section_and_value)
_SCALAR_DISPATCH: dict[str, tuple[str, Callable]] = {
    "purpose":           ("introduction", ops.set_purpose),
    "background":        ("context",      ops.set_background),
    "objectives":        ("context",      ops.set_objectives),
    "data_requirements": ("data_req",     ops.set_data_requirements),
    "appendix":          ("appendix",     ops.set_appendix),
}

# list_field_name -> (section_id, ops_add_function)
_LIST_DISPATCH: dict[str, tuple[str, Callable]] = {
    "constraints":         ("context",    ops.add_constraint),
    "assumptions":         ("context",    ops.add_assumption),
    "scope_in":            ("scope",      ops.add_scope_in),
    "scope_out":           ("scope",      ops.add_scope_out),
    "acceptance_criteria": ("acceptance", ops.add_acceptance_criterion),
    "appendix_items":      ("appendix",   ops.add_appendix_item),
}

# table_name -> (section_id, row_pydantic_class, ops_upsert_function)
# `upsert_fn` takes (section, row_model) — except glossary/abbreviations which take (term, definition).
_TABLE_DISPATCH: dict[str, tuple[str, type[BaseModel] | None, Callable]] = {
    "intended_audience": ("introduction", AudienceEntry,    ops.upsert_audience_entry),
    "stakeholders":      ("stakeholders", Stakeholder,      ops.upsert_stakeholder),
    "nfr_rows":          ("nfr",          NFRRow,           ops.upsert_nfr_row),
    "integrations":      ("integrations", IntegrationRow,   ops.upsert_integration),
    "glossary":          ("glossary",     None,             ops.upsert_glossary_entry),      # special shape
    "abbreviations":     ("glossary",     None,             ops.upsert_abbreviation_entry),  # same section file
}


# ── Tools ────────────────────────────────────────────────────────────────────

@tool
def init_brd(
    project_name: str | None = None,
    project_code: str | None = None,
    language: Literal["en", "vi", "ja", "zh"] | None = None,
    author: str | None = None,
    version: str | None = None,
) -> str:
    """Create a fresh BRD draft. Initializes the section directory + page index.

    **WBS-first pipeline:** by default this **inherits** project_name,
    project_code, language, version from `workspace/project.json` written
    by `init_wbs`. Pass arguments here only to override / patch the
    canonical metadata.

    If no canonical metadata exists yet (BRD-first fallback), `project_name`
    and `project_code` are required.

    Overwrites any existing BRD draft.
    """
    store = _store()
    try:
        store.init(
            project_name=project_name,
            project_code=project_code,
            language=language,
            author=author,
            version=version,
        )
    except FileNotFoundError as e:
        return f"ERROR: {e}"

    # Read back what was actually used (may be inherited from canonical)
    meta = store.read_section("metadata")
    return (
        f"BRD initialized: {meta.project_name} ({meta.project_code}, lang={meta.language}). "
        f"Now call `set_brd_text` for purpose/background/objectives, "
        f"`add_brd_list_item` for constraints/assumptions/scope, "
        f"`upsert_fr` for each FR, and `upsert_brd_row` for tables."
    )


@tool
def set_brd_text(field: SCALAR_FIELD, value: str) -> str:
    """Set one of the BRD's scalar text fields.

    Accepted fields:
      - purpose            → §1.1 Purpose
      - background         → §2.1 Background
      - objectives         → §2.2 Objectives
      - data_requirements  → §5.4 Data Requirements
      - appendix           → §8 Appendix
    """
    if field not in _SCALAR_DISPATCH:
        return f"ERROR: unknown field {field!r}. Allowed: {list(_SCALAR_DISPATCH)}"

    store = _store()
    if not store.is_initialized():
        return "ERROR: BRD not initialized. Call init_brd first."

    section_id, fn = _SCALAR_DISPATCH[field]
    section = store.read_section(section_id)
    fn(section, value)
    store.write_section(section_id, section)
    return f"Set {field} ({len(value)} chars) in §{section_id}."


@tool
def add_brd_list_item(list_name: LIST_FIELD, item: str) -> str:
    """Append a bullet item to a BRD list section.

    Lists:
      - constraints         → §2.3.1 Constraints
      - assumptions         → §2.3.2 Assumptions
      - scope_in            → §3.1 In Scope  (min 4 items required)
      - scope_out           → §3.2 Out of Scope
      - acceptance_criteria → §6 Acceptance Criteria
      - appendix_items      → §8 Appendix items list
                              Format: "Appendix A: <title/description>"
    """
    if list_name not in _LIST_DISPATCH:
        return f"ERROR: unknown list {list_name!r}. Allowed: {list(_LIST_DISPATCH)}"

    store = _store()
    if not store.is_initialized():
        return "ERROR: BRD not initialized."

    section_id, fn = _LIST_DISPATCH[list_name]
    section = store.read_section(section_id)
    fn(section, item)
    store.write_section(section_id, section)
    n = len(getattr(section, list_name))
    return f"Added to {list_name} ({n} items total)."


@tool
def upsert_brd_row(table: TABLE_NAME, payload_json: str) -> str:
    """Add or update one row of a BRD table.

    Required JSON shape per table:
      intended_audience  → {"role": str, "party": str, "responsibility": str}
      stakeholders       → {"id": str, "name": str, "role": str, "responsibility": str}
      nfr_rows           → {"category": str, "metric": str, "target": str  ← MUST include unit (ms/%/req-s)}
      integrations       → {"system": str, "direction": "Inbound"|"Outbound"|"Bidirectional", "protocol": str, "note": str}
      glossary           → {"term": str, "definition": str}  ← domain terms with full definitions
      abbreviations      → {"term": str, "definition": str}  ← acronym/abbrev → full form (e.g. LMS, AI, RAG)

    Upsert key per table:
      intended_audience: (role, party)
      stakeholders:      id
      nfr_rows:          (category, metric)
      integrations:      system
      glossary:          term
      abbreviations:     term
    """
    if table not in _TABLE_DISPATCH:
        return f"ERROR: unknown table {table!r}. Allowed: {list(_TABLE_DISPATCH)}"

    store = _store()
    if not store.is_initialized():
        return "ERROR: BRD not initialized."

    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        try:
            from json_repair import repair_json
            payload = repair_json(payload_json, return_objects=True, ensure_ascii=False)
            if not isinstance(payload, dict):
                return "ERROR: expected JSON object for payload_json"
        except Exception as e:
            return f"ERROR: invalid JSON and repair failed: {e}"

    section_id, row_cls, fn = _TABLE_DISPATCH[table]
    section = store.read_section(section_id)

    try:
        if table in ("glossary", "abbreviations"):
            fn(section, payload["term"], payload["definition"])
        else:
            fn(section, row_cls(**payload))
    except Exception as e:
        return f"ERROR validating {table} payload: {e}"

    store.write_section(section_id, section)

    # Map table name → actual list attribute on the section model
    _LIST_ATTR = {
        "intended_audience": "intended_audience",
        "stakeholders":      "stakeholders",
        "nfr_rows":          "nfr_rows",
        "integrations":      "integrations",
        "glossary":          "glossary",
        "abbreviations":     "abbreviations",
    }
    n = len(getattr(section, _LIST_ATTR[table]))
    return f"Upserted row into {table} ({n} rows total)."


@tool
def upsert_fr(payload_json: str, rename_from: str | None = None) -> str:
    """Add, update, or RENAME one Functional Requirement (§5.2).

    Required JSON shape:
      {
        "fr_id": "FR1",                  ← MUST be unique, no gaps
        "name": "Document Upload",
        "priority": "Critical"|"High"|"Medium"|"Low"|"Future",
        "short_description": "≤ 20 words",
        "description": "3-6 sentences explaining WHAT and WHY",
        "user_stories": ["As a <role>, I want <goal> so that <benefit>", ...],
        "acceptance_criteria": ["Given <ctx>, When <action>, Then <result>", ...],
        "interface_notes": "API endpoint, UI screen, or data flow"
      }

    **Update mode (default):** if `payload_json.fr_id` already exists, the
    existing UUID `section_id` is preserved so cross-references stay valid.

    **Rename mode:** pass `rename_from="FR2"` AND `payload_json.fr_id="FR3"`
    to atomically:
      1. Copy the old FR's UUID to the new fr_id (so WBS still traces it)
      2. Write the new FR file (with merged content from payload)
      3. Delete the old FR file
      4. Auto-relink every WBS L4 task with source_feature_id="FR2" → "FR3"

    Use rename mode whenever the user asks to renumber an FR. Without it,
    you would orphan WBS tasks.
    """
    store = _store()
    if not store.is_initialized():
        return "ERROR: BRD not initialized."

    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        try:
            from json_repair import repair_json
            payload = repair_json(payload_json, return_objects=True, ensure_ascii=False)
            if not isinstance(payload, dict):
                return "ERROR: expected JSON object for payload_json"
        except Exception as e:
            return f"ERROR: invalid FR JSON and repair failed: {e}"
    try:
        fr = FunctionalRequirement(**payload)
    except Exception as e:
        return f"ERROR: invalid FR payload: {e}"

    # ── Rename branch ────────────────────────────────────────────────────────
    if rename_from is not None:
        if rename_from == fr.fr_id:
            return f"ERROR: rename_from and new fr_id are both {fr.fr_id!r} — nothing to rename."
        old = store.read_fr(rename_from)
        if old is None:
            return f"ERROR: source FR {rename_from!r} does not exist — cannot rename."
        # Preserve UUID across the rename; the new FR carries the old section_id
        fr.section_id = old.section_id
        store.write_fr(fr)
        store.remove_fr(rename_from)
        # Propagate to WBS
        relinked = _relink_wbs_tasks(rename_from, fr.fr_id)
        n = len(store.list_fr_ids())
        return (
            f"Renamed {rename_from} → {fr.fr_id} ({fr.name}). "
            f"Auto-relinked {relinked} WBS task(s). Total FRs: {n}."
        )

    # ── Default upsert branch ────────────────────────────────────────────────
    saved = store.write_fr(fr)
    n = len(store.list_fr_ids())
    return (
        f"Upserted {saved.fr_id} ({saved.name}, priority={saved.priority}). "
        f"Total FRs: {n}."
    )


@tool
def get_brd_summary() -> str:
    """Return a compact, human-readable BRD status — reads ONLY the page index.

    Cheap (~500 tokens) — use freely to check progress between edits.
    """
    return _store().get_summary()
