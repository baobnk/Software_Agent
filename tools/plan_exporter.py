"""plan_exporter.py — Export WBS + solution design thành implementation_plan.md

Reads:
  wbs_state.json        (WBS tasks L1-L4 với man-day estimates)
  technical_design.md   (9-step solution design)
  raw_features.md       (extracted requirements)

Writes:
  implementation_plan.md  (comprehensive markdown — L1-L4 WBS + effort + timeline)
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool
from loguru import logger as _log

_pe_log = _log.bind(ctx="plan_exporter")

try:
    from wbs_agent_kit.src.types import WBSDocument, WBSTask
except ImportError:
    sys.path.insert(0, str(Path(__file__).parents[2] / "bnk-agent" / "packages"))
    from wbs_agent_kit.src.types import WBSDocument, WBSTask  # type: ignore

from .workspace import read_model, read_text, write_text, WBS_STATE_FILE

PLAN_FILE = "implementation_plan.md"

# Assume 22 working days / month, 8h/day
_WORKING_DAYS_PER_MONTH = 22


def _indent(level: int) -> str:
    return "  " * (level - 1)


def _render_wbs_table(tasks: list[WBSTask]) -> str:
    """Render WBS tasks as a markdown table."""
    lines = [
        "| # | Code | Task / Phase | L | BE (md) | FE (md) | Total Dev |",
        "|---|------|--------------|---|---------|---------|-----------|",
    ]
    for i, t in enumerate(tasks, 1):
        indent = _indent(t.hierarchy_level)
        be = f"{t.md_be:.1f}" if t.md_be else "—"
        fe = f"{t.md_fe:.1f}" if t.md_fe else "—"
        total = t.md_be + t.md_fe
        total_str = f"**{total:.1f}**" if total > 0 else "—"
        name = f"{indent}{t.feature}"
        lines.append(f"| {i} | `{t.code}` | {name} | L{t.hierarchy_level} | {be} | {fe} | {total_str} |")
    return "\n".join(lines)


def _render_phase_breakdown(tasks: list[WBSTask]) -> str:
    """Summarize effort per L1 phase."""
    phases: dict[str, dict] = {}
    current_phase = ""

    for t in tasks:
        if t.hierarchy_level == 1:
            current_phase = t.code
            phases[current_phase] = {"name": t.feature, "be": 0.0, "fe": 0.0, "tasks": 0}
        elif t.hierarchy_level == 4 and current_phase:
            phases[current_phase]["be"] += t.md_be
            phases[current_phase]["fe"] += t.md_fe
            phases[current_phase]["tasks"] += 1

    lines = ["| Phase | Name | BE (md) | FE (md) | Total Dev | Leaf Tasks |",
             "|-------|------|---------|---------|-----------|------------|"]
    for code, p in phases.items():
        total = p["be"] + p["fe"]
        lines.append(
            f"| {code} | {p['name']} | {p['be']:.1f} | {p['fe']:.1f} | **{total:.1f}** | {p['tasks']} |"
        )
    return "\n".join(lines)


def _estimate_timeline(total_dev_md: float, team_size: int = 3) -> str:
    """Rough timeline assuming team_size devs working in parallel."""
    if total_dev_md <= 0 or team_size <= 0:
        return "N/A"
    # Add BA + QC + PM overhead (~45% default)
    total_all = total_dev_md * 1.45
    calendar_days = total_all / team_size
    months = calendar_days / _WORKING_DAYS_PER_MONTH
    start = date.today()
    end = start + timedelta(days=int(calendar_days * 1.4))  # 40% buffer
    return (
        f"~{months:.1f} months ({int(calendar_days)} working days) "
        f"with {team_size}-dev team\n"
        f"  Estimated start: {start.strftime('%Y-%m-%d')}  |  "
        f"Target end: {end.strftime('%Y-%m-%d')}"
    )


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def export_implementation_plan(
    project_name: str,
    team_size: int = 3,
    include_solution_design: bool = True,
) -> str:
    """Generate implementation_plan.md — comprehensive WBS + effort + timeline report.

    Reads wbs_state.json, technical_design.md, raw_features.md from workspace.
    Writes implementation_plan.md to workspace.

    Args:
        project_name:            Display name used in document header.
        team_size:               Number of developers (for timeline estimate).
        include_solution_design: Append solution design sections to the plan.

    Returns:
        Absolute path of the generated file + summary stats.
    """
    _pe_log.info(f"export_implementation_plan | {project_name!r}  team={team_size}")
    doc = read_model(WBS_STATE_FILE, WBSDocument)
    if doc is None:
        _pe_log.error("export_implementation_plan — wbs_state.json not found")
        return "[ERROR] wbs_state.json not found — run wbs_estimator_agent first."

    tasks = doc.tasks
    l4 = [t for t in tasks if t.hierarchy_level == 4]
    total_be  = sum(t.md_be for t in l4)
    total_fe  = sum(t.md_fe for t in l4)
    total_dev = total_be + total_fe
    total_ba  = total_dev * doc.master.pct_ba
    total_qc  = total_dev * doc.master.pct_qc
    total_pm  = total_dev * doc.master.pct_pm
    grand     = total_dev + total_ba + total_qc + total_pm
    _pe_log.info(f"  WBS: {len(tasks)} tasks, {len(l4)} L4, grand={grand:.1f} md")

    tech_design = read_text("technical_design.md") or ""
    raw_feat    = read_text("raw_features.md")     or ""

    today = date.today().strftime("%Y-%m-%d")
    timeline = _estimate_timeline(total_dev, team_size)

    # ── Extract key sections from technical_design.md ─────────────────────────
    def _extract_section(md: str, heading: str) -> str:
        """Pull the first heading-matching section from markdown."""
        lines = md.splitlines()
        capturing = False
        result: list[str] = []
        for line in lines:
            if heading.lower() in line.lower() and line.startswith("#"):
                capturing = True
                continue
            if capturing:
                if line.startswith("## ") and result:
                    break
                result.append(line)
        return "\n".join(result).strip()

    problem_section   = _extract_section(tech_design, "Xác nhận bài toán")
    approach_section  = _extract_section(tech_design, "Hướng tiếp cận")
    scope_section     = _extract_section(tech_design, "Phạm vi")
    risk_section      = _extract_section(tech_design, "Rủi ro")
    assumption_section= _extract_section(tech_design, "Giả định")

    # ── Build markdown ─────────────────────────────────────────────────────────
    md = f"""# Implementation Plan — {project_name}

> **Generated:** {today}  |  **Project:** {doc.project_name} (`{doc.project_code}`)
> **Status:** Draft for Review

---

## 1. Executive Summary

| Item | Value |
|------|-------|
| Project | {project_name} |
| Project Code | `{doc.project_code}` |
| Total Tasks (L4) | {len(l4)} |
| Dev Effort | {total_dev:.1f} man-days (BE: {total_be:.1f} + FE: {total_fe:.1f}) |
| BA Effort | {total_ba:.1f} man-days ({doc.master.pct_ba*100:.0f}% of dev) |
| QC Effort | {total_qc:.1f} man-days ({doc.master.pct_qc*100:.0f}% of dev) |
| PM Effort | {total_pm:.1f} man-days ({doc.master.pct_pm*100:.0f}% of dev) |
| **Grand Total** | **{grand:.1f} man-days** |
| Estimated Timeline | {timeline} |

---

## 2. Problem & Objectives

{problem_section or "_See raw_features.md Section 1 for details._"}

---

## 3. Solution Approach

{approach_section or "_See technical_design.md Section 2 for details._"}

---

## 4. Scope

{scope_section or "_See technical_design.md Section 7 for details._"}

---

## 5. Work Breakdown Structure (Full)

> **Legend:** L1 = Phase · L2 = Sub-phase · L3 = Module · L4 = Task (leaf)
> Man-days shown only on L4. L1–L3 totals are rollups.

{_render_wbs_table(tasks)}

---

## 6. Effort Summary by Phase

{_render_phase_breakdown(tasks)}

### Role Breakdown

| Role | Man-days | % | Rate (USD/day) | Cost (USD) |
|------|----------|---|----------------|------------|
| Backend Dev | {total_be:.1f} | {total_be/grand*100:.0f}% | {doc.master.rate_dev} | {total_be*doc.master.rate_dev:,.0f} |
| Frontend Dev | {total_fe:.1f} | {total_fe/grand*100:.0f}% | {doc.master.rate_dev} | {total_fe*doc.master.rate_dev:,.0f} |
| BA | {total_ba:.1f} | {total_ba/grand*100:.0f}% | {doc.master.rate_ba} | {total_ba*doc.master.rate_ba:,.0f} |
| QC | {total_qc:.1f} | {total_qc/grand*100:.0f}% | {doc.master.rate_qc} | {total_qc*doc.master.rate_qc:,.0f} |
| PM | {total_pm:.1f} | {total_pm/grand*100:.0f}% | {doc.master.rate_pm} | {total_pm*doc.master.rate_pm:,.0f} |
| **Total** | **{grand:.1f}** | **100%** | — | **{(total_be+total_fe)*doc.master.rate_dev + total_ba*doc.master.rate_ba + total_qc*doc.master.rate_qc + total_pm*doc.master.rate_pm:,.0f}** |

---

## 7. Timeline Estimate

```
{timeline}

Team composition assumed: {team_size} developers (BE + FE)
Working days/month: {_WORKING_DAYS_PER_MONTH}
Overhead buffer: 40% (integration, review, revision cycles)
```

### Indicative Milestone Schedule

| Milestone | Deliverable | Est. Duration |
|-----------|-------------|---------------|
| M0 | Kick-off & Environment Setup | 1 week |
| M1 | Phase I complete (Setup & Requirements) | 2 weeks |
| M2 | Phase II complete (Development) | {max(1, int(total_dev / team_size / _WORKING_DAYS_PER_MONTH * 0.7 + 0.5))} months |
| M3 | Phase III complete (Testing & UAT) | 3–4 weeks |
| M4 | Go-live & Handover | 1 week |

---

## 8. Estimation Assumptions

{assumption_section or "- Standard BnK estimation guidelines applied (see `config/domain_rules.yaml`)."}

---

## 9. Risk Registry

{risk_section or "_See technical_design.md Section 9 for full risk assessment._"}

---

## 10. Master Data (Billing Rates)

| Parameter | Value |
|-----------|-------|
| PM overhead | {doc.master.pct_pm*100:.0f}% of dev |
| BA overhead | {doc.master.pct_ba*100:.0f}% of dev |
| QC overhead | {doc.master.pct_qc*100:.0f}% of dev |
| Rate PM | USD {doc.master.rate_pm}/day |
| Rate BA | USD {doc.master.rate_ba}/day |
| Rate Dev | USD {doc.master.rate_dev}/day |
| Rate QC | USD {doc.master.rate_qc}/day |
| Currency rate | 1 USD = {doc.master.currency_rate:,.0f} VND |

---
"""

    if include_solution_design and tech_design:
        md += f"""
## Appendix A — Full Solution Design

{tech_design}

---
"""

    write_text(PLAN_FILE, md)
    from .workspace import get_workspace
    path = str(get_workspace() / PLAN_FILE)
    _pe_log.success(
        f"implementation_plan.md saved → {path}  "
        f"({len(md):,} chars, {len(l4)} L4 tasks, {grand:.1f} md)"
    )
    return (
        f"implementation_plan.md saved → {path}\n"
        f"Size: {len(md):,} chars\n"
        f"Tasks: {len(l4)} leaf tasks | {grand:.1f} man-days total | {timeline}"
    )


@tool
def get_plan_preview() -> str:
    """Return the first 3000 chars of implementation_plan.md for a quick review.

    Returns a message if the file has not been generated yet.
    """
    content = read_text(PLAN_FILE)
    if not content:
        return "[implementation_plan.md not found — run export_implementation_plan first]"
    preview = content[:3000]
    if len(content) > 3000:
        preview += f"\n\n... [{len(content):,} total chars — open file for full view]"
    return preview
