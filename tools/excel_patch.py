"""LangChain @tool wrapper for all excel_*_core mutators.

Smart-dispatch single tool: `patch_workbook(xlsx_path, operation, payload)`.
Procedure (when to call which operation) is taught via SKILL.md, not tools.

Operations:
  - inject_wbs_hierarchy   : payload = {"phases": [{"code", "feature", "modules": [{"code", "feature", "leaf_codes": [...]}]}]}
  - clear_wbs_junk_rows    : payload = {}
  - add_wbs_total_row      : payload = {"label": "TOTAL"}    (label optional)
  - insert_ai_column_wbs   : payload = {}   — idempotent, inserts AI/ML (MD) col in WBS
  - rebuild_wbs_rollups    : payload = {}   — rewrite all L1/L2/L3 SUM+pct formulas
  - upsert_master_role     : payload = {"role_label", "pct_on_dev", "rate_usd",
                                         "pct_named_range", "rate_named_range",
                                         "remark"}
  - rebuild_effort_total   : payload = {}
  - rebuild_effort_modules : payload = {"module_codes": [...]}
  - write_effort_headers   : payload = {}   — write standard header row in Effort sheet
  - write_master_planning  : payload = gantt dict (output of compute_delivery_plan)
  - write_resource_planning: payload = {"allocation": {...}, "gantt": {...}, "deadline_date": "YYYY-MM-DD"}
  - write_deliverable_milestones: payload = {"milestones": [...]}

Single tool keeps the agent's @tool budget down (Rule §2). The dispatcher
loads the workbook, runs the op, saves; payload is JSON-serializable.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from langchain_core.tools import tool
from loguru import logger as _log

from .excel_delivery_core import (
    write_deliverable_milestones,
    write_master_planning,
    write_resource_planning,
)
from .excel_effort_core import rebuild_for_modules, rebuild_total_row, write_effort_headers
from .excel_master_data_core import upsert_role
from .excel_wbs_core import (
    add_total_row,
    clear_junk_rows,
    consolidate_hierarchy,
    derive_hierarchy_from_state,
    inject_hierarchy_rows,
    insert_ai_column_wbs,
    rebuild_l1_l2_rollups,
)
from .excel_workbook_core import open_wb, save_wb

_patch_log = _log.bind(ctx="excel_patch")


def _parse_date(v) -> date:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        return datetime.fromisoformat(v).date()
    raise ValueError(f"Unparseable date: {v!r}")


def _dispatch(operation: str, wb, payload: dict) -> Any:
    """Run one operation against the open workbook. Returns op-specific result."""
    if operation == "inject_wbs_hierarchy":
        spec = derive_hierarchy_from_state(payload.get("phases", []))
        return inject_hierarchy_rows(wb, spec)

    if operation == "clear_wbs_junk_rows":
        return clear_junk_rows(wb)

    if operation == "consolidate_wbs_hierarchy":
        return consolidate_hierarchy(wb)

    if operation == "rebuild_wbs_rollups":
        return rebuild_l1_l2_rollups(wb)

    if operation == "add_wbs_total_row":
        return add_total_row(wb, label=payload.get("label", "TOTAL"))

    if operation == "insert_ai_column_wbs":
        result = insert_ai_column_wbs(wb)
        if result.get("action") != "skipped":
            rebuild_l1_l2_rollups(wb)  # rewrite formulas after column shift
        return result

    if operation == "write_effort_headers":
        write_effort_headers(wb)
        return {"done": True}

    if operation == "upsert_master_role":
        missing = [k for k in ("role_label", "pct_named_range", "rate_named_range") if k not in payload]
        if missing:
            return {"error": f"upsert_master_role missing required keys: {missing}. "
                             f"Required: role_label, pct_named_range, rate_named_range. "
                             f"Optional: pct_on_dev, rate_usd, remark."}
        return upsert_role(
            wb,
            role_label=payload["role_label"],
            pct_on_dev=float(payload.get("pct_on_dev", 0.0)),
            rate_usd=float(payload.get("rate_usd", 0.0)),
            pct_named_range=payload["pct_named_range"],
            rate_named_range=payload["rate_named_range"],
            remark=payload.get("remark", ""),
        )

    if operation == "rebuild_effort_total":
        return rebuild_total_row(wb)

    if operation == "rebuild_effort_modules":
        if "module_codes" not in payload:
            return {"error": "rebuild_effort_modules requires payload={\"module_codes\": [...]}"}
        return rebuild_for_modules(wb, payload["module_codes"])

    if operation == "write_master_planning":
        return write_master_planning(wb, payload)

    if operation == "write_resource_planning":
        missing = [k for k in ("allocation", "gantt") if k not in payload]
        if missing:
            return {"error": f"write_resource_planning missing required keys: {missing}"}
        deadline = payload.get("deadline_date")
        deadline_d = _parse_date(deadline) if deadline else None
        return write_resource_planning(
            wb, payload["allocation"], payload["gantt"], deadline_date=deadline_d,
        )

    if operation == "write_deliverable_milestones":
        if "milestones" not in payload:
            return {"error": "write_deliverable_milestones requires payload={\"milestones\": [...]}"}
        return write_deliverable_milestones(wb, payload["milestones"])

    raise ValueError(f"Unknown operation: {operation!r}")


@tool
def patch_workbook(xlsx_path: str, operation: str, payload_json: str = "{}") -> str:
    """Mutate a BnK WBS .xlsx by running one named operation.

    Operations (see skills/excel_workbook for full schemas):
      inject_wbs_hierarchy        — insert L1/L2 phase/module rows above leaf tasks
      clear_wbs_junk_rows         — delete blank rows past last WBS data
      add_wbs_total_row           — append TOTAL row to WBS sheet
      insert_ai_column_wbs        — insert AI/ML (MD) column into WBS; auto-rebuilds formulas
      rebuild_wbs_rollups         — rewrite all rollup + pct formulas in WBS
      write_effort_headers        — write standard header row in Effort sheet
      upsert_master_role          — add/update a role row in Master Data
      rebuild_effort_total        — fix Effort TOTAL formula to sum all modules
      rebuild_effort_modules      — rewrite Effort module rows (col B) to match WBS
      write_master_planning       — fill Master Plan gantt from compute_delivery_plan
      write_resource_planning     — fill per-role × per-week allocation matrix
      write_deliverable_milestones — fill confirmed milestone Start/End dates

    The workbook is loaded, mutated, and saved to the SAME path. For non-destructive
    workflows, copy the file first and call this on the copy.

    `payload_json` is a JSON string — use this so the tool stays one positional
    schema regardless of operation.
    """
    _patch_log.info(f"patch_workbook | op={operation} path={xlsx_path}")
    try:
        payload = json.loads(payload_json) if payload_json else {}
    except json.JSONDecodeError as e:
        return f"ERROR patch_workbook: invalid payload_json — {e}"
    try:
        wb = open_wb(xlsx_path)
        result = _dispatch(operation, wb, payload)
        # Only save if dispatch didn't return an error dict
        if not (isinstance(result, dict) and "error" in result):
            save_wb(wb, xlsx_path)
        return f"OK {operation}: {json.dumps(result, default=str)}"
    except Exception as e:
        _patch_log.exception(f"patch_workbook error | op={operation}")
        return f"ERROR patch_workbook({operation}): {e}"
