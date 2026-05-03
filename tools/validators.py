"""Deterministic validation tools for critic agent.

All checks are pure Python (no LLM judgment). Error codes are stable so
the supervisor can route by code pattern.

Code namespaces:
  FR_*   — Functional Requirement issues
  NFR_*  — Non-Functional Requirement issues
  WBS_*  — WBS structure issues
  TASK_* — Task-level issues
  TRACE_* — Traceability issues
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from langchain_core.tools import tool

# Both BRD and WBS now use section-sharded stores in this repo.
from packages import project_meta
from packages.brd import BRDStore
from packages.wbs import WBSStore

from .workspace import (
    write_json, read_json, get_workspace,
    ISSUES_FILE,
)


Severity = Literal["error", "warning"]

_NUMERIC_UNIT_RE = re.compile(
    r"[\d.]+\s*(?:ms|%|[KMGT]B|req\/s|rps|fps|tps|qps)",
    re.IGNORECASE,
)
_WORD_UNIT_RE = re.compile(
    r"\b[\d.]+(?:\s+\w+)?\s*(?:"
    r"milliseconds?|seconds?|minutes?|hours?|days?|weeks?|months?|bytes?"
    r"|users?|sessions?|connections?|requests?|transactions?|records?|items?"
    r"|threads?|processes?|nodes?|instances?|replicas?|calls?"
    r")\b",
    re.IGNORECASE,
)


def _has_measurable_unit(text: str) -> bool:
    return bool(_NUMERIC_UNIT_RE.search(text)) or bool(_WORD_UNIT_RE.search(text))


@dataclass
class ValidationIssue:
    severity: Severity
    code: str
    message: str
    section_id: str = ""


def _save_issues(issues: list[ValidationIssue]) -> None:
    write_json(ISSUES_FILE, [vars(i) for i in issues])


# ── BRD Validator ─────────────────────────────────────────────────────────────

@tool
def validate_brd() -> str:
    """Run all BRD validation rules. Returns PASS or list of issues.

    Checks: duplicate FR ids, missing NFR targets, empty descriptions,
    scope_in/out, constraints, assumptions, stakeholders, glossary count,
    abbreviations coverage, appendix items, FR numbering continuity.
    """
    store = BRDStore(get_workspace() / "brd")
    if not store.is_initialized():
        return "ERROR: BRD state not found. Has brd_drafter run yet?"
    doc = store.assemble()

    issues: list[ValidationIssue] = []

    # FR_DUPLICATE_ID
    fr_ids = [fr.fr_id for fr in doc.functional_requirements]
    seen: set[str] = set()
    for fid in fr_ids:
        if fid in seen:
            issues.append(ValidationIssue("error", "FR_DUPLICATE_ID", f"Duplicate FR id: {fid}"))
        seen.add(fid)

    # FR_EMPTY_DESCRIPTION / FR_SHORT_DESCRIPTION
    for fr in doc.functional_requirements:
        if not fr.description.strip():
            issues.append(ValidationIssue("error", "FR_EMPTY_DESCRIPTION",
                                          f"{fr.fr_id}: description is empty",
                                          fr.section_id))
        elif len(fr.description.strip()) < 50:
            issues.append(ValidationIssue("warning", "FR_SHORT_DESCRIPTION",
                                          f"{fr.fr_id}: description < 50 chars",
                                          fr.section_id))
        # FR_NO_ACCEPTANCE — every FR should have at least 1 acceptance criterion
        if not fr.acceptance_criteria:
            issues.append(ValidationIssue("warning", "FR_NO_ACCEPTANCE",
                                          f"{fr.fr_id}: no acceptance criteria",
                                          fr.section_id))

    # NFR_NO_TARGET — every NFR row must have a measurable unit
    for row in doc.nfr_rows:
        if not _has_measurable_unit(row.target):
            issues.append(ValidationIssue("error", "NFR_NO_TARGET",
                                          f"NFR {row.category}/{row.metric}: target {row.target!r} has no measurable unit"))

    # BRD_MISSING_PURPOSE / BACKGROUND / OBJECTIVES
    if not doc.purpose.strip():
        issues.append(ValidationIssue("error", "BRD_MISSING_PURPOSE", "§1.1 Purpose is empty"))
    if not doc.background.strip():
        issues.append(ValidationIssue("error", "BRD_MISSING_BACKGROUND", "§2.1 Background is empty"))
    if not doc.objectives.strip():
        issues.append(ValidationIssue("error", "BRD_MISSING_OBJECTIVES", "§2.2 Objectives is empty"))

    # BRD_NO_INTENDED_AUDIENCE — at least 2 audience rows expected
    if len(doc.intended_audience) < 2:
        issues.append(ValidationIssue("warning", "BRD_SHORT_AUDIENCE",
                                      f"§1.2 Intended Audience has {len(doc.intended_audience)} row(s); expected ≥ 2"))

    # BRD_NO_CONSTRAINTS — at least 3 constraints required
    if not doc.constraints:
        issues.append(ValidationIssue("error", "BRD_NO_CONSTRAINTS",
                                      "§2.3.1 Constraints is empty — must list ≥ 3 project constraints"))
    elif len(doc.constraints) < 3:
        issues.append(ValidationIssue("warning", "BRD_SHORT_CONSTRAINTS",
                                      f"§2.3.1 Constraints has {len(doc.constraints)} item(s); expected ≥ 3"))

    # BRD_NO_ASSUMPTIONS — at least 3 assumptions
    if not doc.assumptions:
        issues.append(ValidationIssue("error", "BRD_NO_ASSUMPTIONS",
                                      "§2.3.2 Assumptions is empty — must list ≥ 3 assumptions"))
    elif len(doc.assumptions) < 3:
        issues.append(ValidationIssue("warning", "BRD_SHORT_ASSUMPTIONS",
                                      f"§2.3.2 Assumptions has {len(doc.assumptions)} item(s); expected ≥ 3"))

    # BRD_NO_SCOPE_IN — scope_in is mandatory
    if not doc.scope_in:
        issues.append(ValidationIssue("error", "BRD_NO_SCOPE_IN",
                                      "§3.1 In Scope is empty — must list ≥ 4 capabilities / deliverables in scope"))
    elif len(doc.scope_in) < 4:
        issues.append(ValidationIssue("warning", "BRD_SHORT_SCOPE_IN",
                                      f"§3.1 In Scope has {len(doc.scope_in)} item(s); expected ≥ 4"))

    # BRD_NO_SCOPE — at least one item in scope_out
    if not doc.scope_out:
        issues.append(ValidationIssue("warning", "BRD_NO_SCOPE_OUT",
                                      "§3.2 Out of Scope is empty — explicitly list what is excluded"))

    # BRD_NO_STAKEHOLDERS
    if not doc.stakeholders:
        issues.append(ValidationIssue("error", "BRD_NO_STAKEHOLDERS", "§4 Stakeholders is empty"))
    elif len(doc.stakeholders) < 3:
        issues.append(ValidationIssue("warning", "BRD_SHORT_STAKEHOLDERS",
                                      f"§4 Stakeholders has {len(doc.stakeholders)} row(s); expected ≥ 3"))

    # BRD_SHORT_NFR — at least 4 NFR categories
    if len(doc.nfr_rows) < 4:
        issues.append(ValidationIssue("warning", "BRD_SHORT_NFR",
                                      f"§5.3 NFR has {len(doc.nfr_rows)} row(s); expected ≥ 4 categories "
                                      "(Performance, Scalability, Availability, Security, ...)"))

    # BRD_SHORT_GLOSSARY — at least 5 glossary entries
    if len(doc.glossary) < 5:
        issues.append(ValidationIssue("warning", "BRD_SHORT_GLOSSARY",
                                      f"§7 Glossary has {len(doc.glossary)} term(s); expected ≥ 5 domain terms"))

    # BRD_NO_ABBREVIATIONS — at least 5 abbreviation entries
    if not doc.abbreviations:
        issues.append(ValidationIssue("error", "BRD_NO_ABBREVIATIONS",
                                      "§7 Abbreviations is empty — extract all acronyms used in the document "
                                      "(LMS, AI, RAG, RBAC, API, etc.)"))
    elif len(doc.abbreviations) < 5:
        issues.append(ValidationIssue("warning", "BRD_SHORT_ABBREVIATIONS",
                                      f"§7 Abbreviations has {len(doc.abbreviations)} entry/entries; expected ≥ 5"))

    # BRD_NO_APPENDIX — appendix_items should reference deliverables / diagrams
    if not doc.appendix_items:
        issues.append(ValidationIssue("warning", "BRD_NO_APPENDIX",
                                      "§8 Appendix has no items — list reference materials "
                                      "(e.g. 'Appendix A: Use Case Diagram', 'Appendix B: Architecture Diagram')"))

    # FR numbering should start at FR1 and be contiguous
    if fr_ids:
        expected = [f"FR{i}" for i in range(1, len(fr_ids) + 1)]
        if sorted(fr_ids) != sorted(expected):
            issues.append(ValidationIssue("warning", "FR_NUMBERING_GAP",
                                          f"FR ids are not contiguous: {fr_ids}"))

    _save_issues(issues)
    if not issues:
        return "PASS — BRD validation clean."
    errors = [i for i in issues if i.severity == "error"]
    warns = [i for i in issues if i.severity == "warning"]
    lines = [f"FAIL — {len(errors)} error(s), {len(warns)} warning(s):"]
    for iss in issues:
        lines.append(f"  [{iss.severity.upper()}] {iss.code}: {iss.message}")
    return "\n".join(lines)


# ── WBS Validator ─────────────────────────────────────────────────────────────

@tool
def validate_wbs() -> str:
    """Run all WBS validation rules. Returns PASS or list of issues.

    Checks: L4 tasks must have md_be or md_fe > 0, hierarchy integrity,
    phase coverage (Setup, Development, Testing).
    """
    wbs_store = WBSStore(get_workspace() / "wbs")
    if not wbs_store.is_initialized():
        return "ERROR: WBS state not found."
    doc = wbs_store.assemble()

    issues: list[ValidationIssue] = []

    # TASK_ZERO_EFFORT — L4 tasks should have some effort
    for t in doc.tasks:
        if t.hierarchy_level == 4 and t.md_be == 0 and t.md_fe == 0:
            issues.append(ValidationIssue("warning", "TASK_ZERO_EFFORT",
                                          f"Task {t.code} ({t.feature}) has zero BE and FE effort"))

    # WBS_MISSING_PHASE — check Setup/Dev/Test-Deploy phases exist
    phase_features = [t.feature.lower() for t in doc.tasks if t.hierarchy_level == 1]
    required_keywords = {"setup", "development", "deploy"}
    missing = [kw for kw in required_keywords
               if not any(kw in f for f in phase_features)]
    if missing:
        issues.append(ValidationIssue("warning", "WBS_MISSING_PHASE",
                                      f"Missing expected WBS phases: {missing}"))

    # WBS_NO_TASKS
    if not doc.tasks:
        issues.append(ValidationIssue("error", "WBS_NO_TASKS", "WBS has no tasks"))

    _save_issues(issues)
    if not issues:
        return "PASS — WBS validation clean."
    errors = [i for i in issues if i.severity == "error"]
    warns = [i for i in issues if i.severity == "warning"]
    lines = [f"FAIL — {len(errors)} error(s), {len(warns)} warning(s):"]
    for iss in issues:
        lines.append(f"  [{iss.severity.upper()}] {iss.code}: {iss.message}")
    return "\n".join(lines)


# ── Traceability Validator ────────────────────────────────────────────────────

@tool
def validate_traceability() -> str:
    """Check that every FR has at least one WBS L4 task referencing it.

    Also checks for orphan WBS tasks that reference non-existent FRs.
    """
    brd_store = BRDStore(get_workspace() / "brd")
    wbs_store = WBSStore(get_workspace() / "wbs")
    if not brd_store.is_initialized() or not wbs_store.is_initialized():
        return "ERROR: Both BRD and WBS must exist for traceability check."
    brd = brd_store.assemble()
    wbs = wbs_store.assemble()

    issues: list[ValidationIssue] = []

    # ── META_MISMATCH — project metadata must match across BRD and WBS ───────
    if brd.project_code != wbs.project_code:
        issues.append(ValidationIssue(
            "error", "META_MISMATCH",
            f"project_code differs: BRD={brd.project_code!r} vs WBS={wbs.project_code!r}",
        ))
    if brd.project_name != wbs.project_name:
        issues.append(ValidationIssue(
            "error", "META_MISMATCH",
            f"project_name differs: BRD={brd.project_name!r} vs WBS={wbs.project_name!r}",
        ))
    canonical = project_meta.read(get_workspace())
    if canonical is not None:
        if canonical.project_code != brd.project_code:
            issues.append(ValidationIssue(
                "error", "META_DRIFT",
                f"BRD project_code {brd.project_code!r} drifted from canonical {canonical.project_code!r}",
            ))
        if canonical.project_code != wbs.project_code:
            issues.append(ValidationIssue(
                "error", "META_DRIFT",
                f"WBS project_code {wbs.project_code!r} drifted from canonical {canonical.project_code!r}",
            ))

    fr_ids = {fr.fr_id for fr in brd.functional_requirements}
    fr_section_ids = {fr.section_id for fr in brd.functional_requirements}

    # Which FRs are covered by WBS tasks?
    covered_frs: set[str] = set()
    for task in wbs.tasks:
        if task.hierarchy_level == 4:
            if task.source_feature_id:
                covered_frs.add(task.source_feature_id)
            # TRACE_ORPHAN_TASK — WBS task references non-existent FR
            if task.source_feature_id and task.source_feature_id not in fr_ids:
                issues.append(ValidationIssue("error", "TRACE_ORPHAN_TASK",
                                              f"Task {task.code} references non-existent {task.source_feature_id}"))

    # TRACE_UNCOVERED_FR — FR has no WBS task
    for fr_id in fr_ids:
        if fr_id not in covered_frs:
            issues.append(ValidationIssue("warning", "TRACE_UNCOVERED_FR",
                                          f"{fr_id} has no WBS task referencing it"))

    _save_issues(issues)
    if not issues:
        return f"PASS — All {len(fr_ids)} FRs have WBS coverage."
    errors = [i for i in issues if i.severity == "error"]
    warns = [i for i in issues if i.severity == "warning"]
    lines = [f"FAIL — {len(errors)} error(s), {len(warns)} warning(s):"]
    for iss in issues:
        lines.append(f"  [{iss.severity.upper()}] {iss.code}: {iss.message}")
    return "\n".join(lines)


@tool
def get_issues() -> str:
    """Return current validation issues from the last critic run."""
    raw = read_json(ISSUES_FILE)
    if not raw:
        return "No issues found (or critic has not run yet)."
    lines = [f"Total issues: {len(raw)}"]
    for iss in raw:
        lines.append(f"  [{iss['severity'].upper()}] {iss['code']}: {iss['message']}")
    return "\n".join(lines)
