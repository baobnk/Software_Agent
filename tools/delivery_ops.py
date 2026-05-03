"""LangChain @tool wrappers for delivery_planner_core.

Three tools:
  compute_delivery_plan(...)       — pure compute, returns gantt + allocation + milestones
  confirm_delivery_milestones(...) — HITL via LangGraph interrupt
  finalize_delivery_plan(...)      — write all 3 delivery sections to xlsx in one call

Per Rule §7, HITL must use `langgraph.types.interrupt`, not blocking input().
The orchestrator's `interrupt_on={"confirm_delivery_milestones": True}`
will pause the graph; API resumes via `Command(resume=...)`.
"""
from __future__ import annotations

import json
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool
from loguru import logger as _log

from ._calendar_utils import derive_team_size
from .delivery_planner_core import (
    DEFAULT_ROLES,
    ModuleEffort,
    compute_gantt,
    compute_resource_allocation,
    propose_deliverable_milestones,
)
from .workspace import get_workspace

_dp_log = _log.bind(ctx="delivery_ops")


def _read_modules_from_workspace() -> tuple[list[ModuleEffort], float]:
    """Build module list by aggregating L4 task effort upward to L1/L2 nodes.

    Strategy:
      1. Read L1/L2 structure nodes from 10_structure.json (provides hierarchy).
      2. Read every L4 task from 20_tasks/*.json (provides md_be/md_fe/md_ai).
      3. Aggregate L4 effort up to L2 parent (via parent_code or code prefix).
      4. Aggregate L2 effort up to L1 phase.

    This is required because structural nodes never store effort directly —
    effort lives only in L4 leaf tasks.
    """
    ws = get_workspace()
    wbs_dir = ws / "wbs"
    idx_path = wbs_dir / "_index.json"
    struct_path = wbs_dir / "10_structure.json"
    tasks_dir = wbs_dir / "20_tasks"

    if not idx_path.exists():
        return [], 0.0

    # ── Step 1: load L1/L2 nodes ─────────────────────────────────────────────
    l1_nodes: list[dict] = []
    l2_nodes: list[dict] = []

    if struct_path.exists():
        struct = json.loads(struct_path.read_text())
        for node in struct.get("nodes", []):
            lvl = node.get("hierarchy_level")
            if lvl == 1:
                l1_nodes.append(node)
            elif lvl == 2:
                l2_nodes.append(node)

    # ── Step 2: aggregate L4 task effort to L2 ───────────────────────────────
    l2_effort: dict[str, float] = {}  # code → total md

    if tasks_dir.exists():
        for task_file in tasks_dir.glob("*.json"):
            try:
                task = json.loads(task_file.read_text())
            except Exception:
                continue
            md = (
                (task.get("md_be") or 0.0)
                + (task.get("md_fe") or 0.0)
                + (task.get("md_ai") or 0.0)
            )
            if md <= 0:
                continue
            # Map this task to the nearest L2 ancestor via parent_code
            parent = task.get("parent_code") or ""
            if parent:
                # parent_code may be L2 ("I.A"), L3 ("I.A.1"), or L1 ("I")
                parts = parent.split(".")
                if len(parts) >= 2:
                    l2_code = ".".join(parts[:2])  # e.g. "I.A"
                else:
                    l2_code = parent              # L1 code as fallback
            else:
                # Derive from task code (e.g. "BNK-01" → no easy parent; use code prefix)
                code = task.get("code", "")
                parts = code.split(".")
                l2_code = ".".join(parts[:2]) if len(parts) >= 2 else code
            l2_effort[l2_code] = l2_effort.get(l2_code, 0.0) + md

    # Fallback: if no tasks found in 20_tasks, read totals from _index.json
    if not l2_effort:
        idx = json.loads(idx_path.read_text())
        for t in idx.get("tasks", []):
            md = (
                (t.get("md_be") or 0.0)
                + (t.get("md_fe") or 0.0)
                + (t.get("md_ai") or 0.0)
            )
            if md <= 0:
                continue
            parent = t.get("parent_code", "")
            parts = parent.split(".") if parent else []
            l2_code = ".".join(parts[:2]) if len(parts) >= 2 else parent or t.get("code", "?")
            l2_effort[l2_code] = l2_effort.get(l2_code, 0.0) + md

    # ── Step 3: aggregate L2 effort to L1 ────────────────────────────────────
    l1_effort: dict[str, float] = {}
    for l2_code, md in l2_effort.items():
        l1_code = l2_code.split(".")[0]  # "I.A" → "I"
        l1_effort[l1_code] = l1_effort.get(l1_code, 0.0) + md

    total_md = sum(l1_effort.values())

    # ── Step 4: build ordered ModuleEffort list ───────────────────────────────
    modules: list[ModuleEffort] = []

    # Use L1/L2 node order from 10_structure.json for deterministic gantt
    seen_l1: set[str] = set()
    seen_l2: set[str] = set()

    for node in l1_nodes:
        code = node["code"]
        md = l1_effort.get(code, 0.0)
        modules.append(ModuleEffort(
            code=code, feature=node.get("feature", code),
            md=md, is_phase=True,
        ))
        seen_l1.add(code)

    for node in l2_nodes:
        code = node["code"]
        md = l2_effort.get(code, 0.0)
        modules.append(ModuleEffort(
            code=code, feature=node.get("feature", code),
            md=md, is_phase=False,
        ))
        seen_l2.add(code)

    # Add any L2 modules found in task data but missing from 10_structure.json
    for l2_code in sorted(l2_effort):
        if l2_code not in seen_l2:
            l1_code = l2_code.split(".")[0]
            modules.append(ModuleEffort(
                code=l2_code, feature=l2_code,
                md=l2_effort[l2_code], is_phase=False,
            ))

    return modules, total_md


@tool
def compute_delivery_plan(
    start_date: str,
    deadline_date: str,
    team_size: Optional[int] = None,
    has_ai: bool = True,
    has_designer: bool = True,
) -> str:
    """Compute delivery gantt + per-role × per-week allocation + proposed milestones.

    Inputs:
      start_date    — ISO date "YYYY-MM-DD"
      deadline_date — ISO date "YYYY-MM-DD"
      team_size     — Optional. If None, derived from total_md / deadline.
      has_ai        — Include AI Engineer in roles (default True for AI projects).
      has_designer  — Include Designer.

    Reads module list + total MD from workspace/wbs/ (aggregates L4 task effort).

    Returns a human-readable summary. Full plan saved to workspace/delivery_plan.json.
    """
    _dp_log.info(f"compute_delivery_plan | start={start_date} deadline={deadline_date} team={team_size}")
    s = datetime.fromisoformat(start_date).date()
    d = datetime.fromisoformat(deadline_date).date()

    modules, total_md = _read_modules_from_workspace()
    if not modules or total_md <= 0:
        return ("ERROR: No WBS modules found in workspace/wbs/. "
                "Call upsert_task for each L1/L2 node first.")

    if team_size is None:
        deadline_months = (d - s).days / 30.0
        team_size = derive_team_size(total_md, deadline_months)

    gantt = compute_gantt(modules, total_md, s, d, team_size)
    allocation = compute_resource_allocation(
        gantt, total_md, team_size, has_ai=has_ai, has_designer=has_designer,
    )
    milestones = propose_deliverable_milestones(s, total_md, team_size)

    # Persist to workspace for downstream tools
    out = {
        "gantt": gantt,
        "allocation": allocation,
        "milestones_proposed": milestones,
        "team_size": team_size,
        "total_md": total_md,
        "start_date": str(s),
        "deadline_date": str(d),
    }
    plan_path = get_workspace() / "delivery_plan.json"
    plan_path.write_text(json.dumps(out, default=str, indent=2))

    summary = (
        f"Delivery plan computed: {total_md:.1f} MD, team_size={team_size}, "
        f"{gantt['total_weeks']} weeks. "
        f"Roles allocated: {list(allocation['roles'].keys())}. "
        f"Milestones proposed (need user confirm): {len(milestones)}. "
        f"Saved to {plan_path.name}."
    )
    if gantt.get("capacity_warning"):
        summary += f"\nWARNING: {gantt['capacity_warning']}"
    if allocation.get("capacity_warning"):
        summary += f"\nWARNING: {allocation['capacity_warning']}"
    return summary


@tool
def confirm_delivery_milestones() -> str:
    """Pause graph for user to review and confirm proposed milestone dates.

    Per Rule §7: HITL must go through LangGraph `interrupt`, not blocking input().
    The orchestrator should be configured with
    `interrupt_on={"confirm_delivery_milestones": True}`.

    The interrupt payload contains the proposed milestones. The user's resume
    payload (via `Command(resume=...)`) is expected to be a list of dicts with
    keys {seq, name, start, end, deliverable} where `start`/`end` are
    ISO date strings — possibly adjusted from the proposal.

    On resume, the confirmed milestones are persisted to
    workspace/delivery_plan.json under key `milestones_confirmed`.

    After this tool returns, call `finalize_delivery_plan(xlsx_path)` to write
    all three delivery sections to the Excel file.
    """
    from langgraph.types import interrupt as _interrupt

    plan_path = get_workspace() / "delivery_plan.json"
    if not plan_path.exists():
        return "ERROR: No delivery_plan.json found. Call compute_delivery_plan first."
    plan = json.loads(plan_path.read_text())
    proposed = plan.get("milestones_proposed", [])

    confirmed = _interrupt({
        "tool": "confirm_delivery_milestones",
        "message": (
            "Please review the proposed milestone dates. Adjust as needed and "
            "resume with the final list."
        ),
        "proposed": proposed,
    })

    # On resume, `confirmed` is the user's payload
    if not isinstance(confirmed, list):
        # If the user just approved without changes, use the proposed list
        confirmed = proposed

    plan["milestones_confirmed"] = confirmed
    plan_path.write_text(json.dumps(plan, default=str, indent=2))
    return f"Confirmed {len(confirmed)} milestones. Saved to {plan_path.name}. Now call finalize_delivery_plan(xlsx_path)."


@tool
def finalize_delivery_plan(xlsx_path: str) -> str:
    """Write all three Delivery Plan sections to the Excel file in one call.

    Reads workspace/delivery_plan.json (produced by compute_delivery_plan +
    confirm_delivery_milestones) and writes:
      - Master Planning gantt (module rows with Start/End + sprint marks)
      - Resource Planning (per-role × per-week allocation matrix)
      - Deliverable Milestones (confirmed dates, or proposed if not yet confirmed)

    Call this AFTER confirm_delivery_milestones returns. It replaces the three
    separate patch_workbook("write_master_planning" / "write_resource_planning" /
    "write_deliverable_milestones") calls.

    Args:
        xlsx_path: Absolute path to the WBS .xlsx file to update.
    """
    from .excel_delivery_core import (
        write_deliverable_milestones,
        write_master_planning,
        write_resource_planning,
    )
    from .excel_workbook_core import open_wb, save_wb

    plan_path = get_workspace() / "delivery_plan.json"
    if not plan_path.exists():
        return "ERROR: No delivery_plan.json. Call compute_delivery_plan first."

    plan = json.loads(plan_path.read_text())
    gantt = plan["gantt"]
    allocation = plan["allocation"]
    deadline_str = plan.get("deadline_date")
    deadline_d = datetime.fromisoformat(deadline_str).date() if deadline_str else None

    # Use confirmed milestones if available, otherwise fall back to proposed
    milestones = plan.get("milestones_confirmed") or plan.get("milestones_proposed", [])

    _dp_log.info(f"finalize_delivery_plan | xlsx={xlsx_path} weeks={gantt.get('total_weeks')} milestones={len(milestones)}")

    try:
        wb = open_wb(xlsx_path)
        r1 = write_master_planning(wb, gantt)
        r2 = write_resource_planning(wb, allocation, gantt, deadline_date=deadline_d)
        r3 = write_deliverable_milestones(wb, milestones)
        save_wb(wb, xlsx_path)
    except Exception as e:
        return f"ERROR writing delivery plan to Excel: {e}"

    return (
        f"Delivery plan written to {xlsx_path}: "
        f"master_planning rows={r1.get('rows_written')}, "
        f"resource_planning roles={r2.get('roles_written')}, "
        f"milestones={r3.get('milestones_written')}."
    )
