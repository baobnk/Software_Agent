"""Agent tools for editing the WBS AST.

Section-sharded persistence via `packages.wbs.WBSStore` (metadata + master
in 00_metadata.json, structure L1/L2/L3 in 10_structure.json, one file per
L4 leaf task in 20_tasks/).

WBS-first pipeline: `init_wbs` writes the canonical
`workspace/project.json` so BRD can later inherit metadata.

WBS hierarchy:
  L1 — Phase       (I, II, III)         structural, no effort
  L2 — Sub-phase   (I.A, I.B)           structural, no effort
  L3 — Module      (I.A.1, I.A.2)       structural, no effort
  L4 — Task        (BNK-1, REQ-01)      ← only these have md_be / md_fe

Tool budget: **4** (within Rule §2 ≤8 per subagent).
  init_wbs, set_master_data, upsert_task, get_wbs_summary
"""
from __future__ import annotations

import threading
from typing import Literal, Optional

from langchain_core.tools import tool
from loguru import logger as _log

from packages.wbs import MasterData, WBSStore, WBSTask
from .workspace import get_workspace

_wbs_log = _log.bind(ctx="wbs_ops")

# Protects the read-modify-write cycle on shared section files (LangGraph
# may run tools in a thread pool).
_wbs_lock = threading.Lock()


def _store() -> WBSStore:
    return WBSStore(get_workspace() / "wbs")


# ── Tools ────────────────────────────────────────────────────────────────────

@tool
def init_wbs(
    project_code: str,
    project_name: str,
    language: Literal["en", "vi", "ja", "zh"] = "en",
    version: str = "0.1.0",
) -> str:
    """Initialize a fresh WBS draft. Call ONCE before adding tasks.

    WBS is the FIRST document in the canonical pipeline (WBS-first):
    this also writes `workspace/project.json` which BRD will later inherit.
    Pick `language` from the user's request: 'en', 'vi', 'ja', 'zh'.

    project_code: short BnK project code, e.g. "BNK-GEHP-001".
    """
    _wbs_log.info(f"init_wbs | code={project_code!r}  name={project_name!r}  lang={language!r}")
    with _wbs_lock:
        _store().init(project_code, project_name, language=language, version=version)
    return (
        f"WBS initialized: {project_name} ({project_code}, lang={language}). "
        f"Now call `upsert_task` for each L1/L2/L3 structural node, then for "
        f"each L4 leaf task with md_be / md_fe / md_ai estimates."
    )


@tool
def set_master_data(
    pct_pm: float = 0.05,
    pct_ba: float = 0.10,
    pct_qc: float = 0.10,
    pct_ai: float = 0.0,
    rate_pm: float = 2500,
    rate_ba: float = 2000,
    rate_dev: float = 2500,
    rate_qc: float = 2000,
    rate_ai: float = 3000,
    currency_rate: float = 24500,
) -> str:
    """Update WBS master data (effort ratios and billing rates).

    Defaults are BnK standard. Override only when the client specifies
    different rates — do NOT call this unless the brief explicitly mentions
    custom rates.

    pct_ai: AI Engineer ratio relative to dev total. Set >0 only for AI/ML projects.
    rate_ai: AI Engineer billing rate in USD/day (default 3000).
    """
    _wbs_log.info(
        f"set_master_data | pm={pct_pm} ba={pct_ba} qc={pct_qc} ai={pct_ai} "
        f"rate_dev={rate_dev} rate_ai={rate_ai} currency={currency_rate}"
    )
    with _wbs_lock:
        store = _store()
        if not store.is_initialized():
            return "ERROR: WBS not initialized. Call init_wbs first."
        store.update_master(MasterData(
            pct_pm=pct_pm, pct_ba=pct_ba, pct_qc=pct_qc, pct_ai=pct_ai,
            rate_pm=rate_pm, rate_ba=rate_ba, rate_dev=rate_dev,
            rate_qc=rate_qc, rate_ai=rate_ai, currency_rate=currency_rate,
        ))
    return "Master data updated."


@tool
def upsert_task(
    code: str,
    feature: str,
    hierarchy_level: int,
    md_be: float = 0.0,
    md_fe: float = 0.0,
    md_ai: float = 0.0,
    description: str = "",
    remark: str = "",
    ref_code: Optional[str] = None,
    parent_code: Optional[str] = None,
    source_feature_id: Optional[str] = None,
    source_section_id: Optional[str] = None,
    row_num: Optional[int] = None,
) -> str:
    """Add or update a task in the WBS.

    Routing by `hierarchy_level`:
      1, 2, 3 → structural nodes, written to 10_structure.json
      4       → L4 leaf task, written to its own file 20_tasks/<code>.json

    For L4 tasks: set md_be (backend), md_fe (frontend), md_ai (AI/ML) in man-days.
    md_ba, md_qc, md_pm are computed automatically from master percentages
    by the Excel template — do NOT set them here.

    md_ai: man-days for AI/ML work on this task (0 for non-AI tasks).
    source_feature_id: FR id this task traces to (e.g. "FR1").
    source_section_id: UUID from the FR's section_id (preserved across renames).
    """
    _wbs_log.debug(
        f"upsert_task | L{hierarchy_level} {code!r:12s} {feature[:40]!r} "
        f"be={md_be} fe={md_fe} ai={md_ai}"
    )
    with _wbs_lock:
        store = _store()
        if not store.is_initialized():
            return "ERROR: WBS not initialized. Call init_wbs first."

        if hierarchy_level not in (1, 2, 3, 4):
            return f"ERROR: hierarchy_level must be 1-4 (got {hierarchy_level})"

        task = WBSTask(
            code=code,
            feature=feature,
            hierarchy_level=hierarchy_level,  # type: ignore[arg-type]
            md_be=md_be,
            md_fe=md_fe,
            md_ai=md_ai,
            description=description,
            remark=remark,
            ref_code=ref_code,
            parent_code=parent_code,
            source_feature_id=source_feature_id,
            source_section_id=source_section_id,  # type: ignore[arg-type]
            row_num=row_num,
        )

        if hierarchy_level == 4:
            store.write_task(task)
            n = len(store.list_task_codes())
            return f"L4 task {code!r} upserted ({n} L4 tasks total)."
        else:
            store.upsert_node(task)
            return f"L{hierarchy_level} node {code!r} upserted in structure."


@tool
def get_wbs_summary() -> str:
    """Return a compact WBS status — reads ONLY the page index (~500 tokens)."""
    return _store().get_summary()
