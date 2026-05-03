"""Pure-compute delivery planning.

Four independent functions, no IO, no openpyxl dependency:

  normalize_team_size_for_constraint(...)  → min team_size so dev+UAT ≤ N months
  compute_gantt(modules, ...)              → per-module Start/End + sprint marks
  compute_resource_allocation(...)         → per-role × per-week allocation matrix
  propose_deliverable_milestones(...)      → 5 standard outsourcing milestones

Conventions (BnK outsourcing):
  • 1 MD = 1 person · 1 working day. Working week = 5 days, 20 MD/person/month.
  • Allocation values: 1.0 (full-time), 0.5 (half), 0.2 (light/sporadic).
  • 8 standard roles: Project Manager, Technical Lead, Developer,
    Business Analyst, Quality Controller, Designer, Devops, AI Engineer.
  • Timeline constraint (default): develop + UAT ≤ 2 months.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable

from ._calendar_utils import (
    WORKING_DAYS_PER_WEEK,
    add_business_days,
    business_days_between,
    md_to_calendar_weeks,
    week_boundaries,
    week_index,
)


# ── Timeline normalization ───────────────────────────────────────────────────

def normalize_team_size_for_constraint(
    total_md: float,
    max_total_months: float = 2.0,
    uat_weeks: int = 2,
) -> int:
    """Return minimum team_size so develop + UAT fits within max_total_months.

    Formula:
      max_dev_days = max_total_months × 20 − uat_weeks × 5
      min_team_size = ceil(total_md / max_dev_days)   clipped to [2, 12]

    Example: 54 MD, 2 months, 2 weeks UAT → max_dev=30 → ceil(54/30)=2.
    """
    working_days_per_month = 20
    max_total_days = int(max_total_months * working_days_per_month)
    uat_days = uat_weeks * 5
    max_dev_days = max(5, max_total_days - uat_days)
    min_size = math.ceil(total_md / max_dev_days)
    return max(2, min(min_size, 12))


# ── Module gantt ─────────────────────────────────────────────────────────────

@dataclass
class ModuleEffort:
    code: str          # "I", "I.A", "II", ...
    feature: str
    md: float          # man-days for this module
    is_phase: bool     # L1 (True) or L2 (False)


@dataclass
class ModuleSchedule:
    code: str
    feature: str
    is_phase: bool
    md: float
    start: date
    end: date
    week_start: int    # 1-based
    week_end: int


def compute_gantt(
    modules: list[ModuleEffort],
    total_md: float,
    start_date: date,
    deadline_date: date,
    team_size: int,
) -> dict:
    """Return per-module schedule + global sprint calendar.

    Algorithm: walk modules in order; each L2 module consumes
    `md / team_size` business days; L1 phase rows span their L2 children.

    If the cumulative duration exceeds (deadline - start), we proportionally
    shrink each module's duration so total ≤ deadline span. This still
    surfaces a `capacity_warning` in the result.
    """
    if total_md <= 0 or team_size <= 0:
        return {"modules": [], "sprints": [], "capacity_warning": "invalid input"}

    # Effective MD per L2 module; phase rows derive from children
    l2 = [m for m in modules if not m.is_phase]
    l2_total = sum(m.md for m in l2) or total_md

    # Available calendar business days
    avail_days = max(1, business_days_between(start_date, deadline_date))
    # Required business days at given team size (parallel across L2 modules
    # only — assume sequential within each module).
    raw_days = sum(max(1, round(m.md / team_size)) for m in l2)

    # Compression factor (≤ 1.0)
    if raw_days > avail_days:
        compress = avail_days / raw_days
        capacity_warning = (
            f"Required {raw_days} business days at team_size={team_size}, "
            f"but only {avail_days} available — compressing {1 - compress:.0%}"
        )
    else:
        compress = 1.0
        capacity_warning = None

    schedules: dict[str, tuple[date, date]] = {}  # code → (start, end)
    cursor = start_date

    for mod in l2:
        days = max(1, round(mod.md / team_size * compress))
        s = cursor
        e = add_business_days(s, days - 1)
        if e > deadline_date:
            e = deadline_date
        schedules[mod.code] = (s, e)
        # Advance cursor by `days` business days (next module starts the day after)
        cursor = add_business_days(s, days)
        if cursor > deadline_date:
            cursor = deadline_date

    # Phase (L1) rows span all their child modules
    phase_codes = [m.code for m in modules if m.is_phase]
    for ph in phase_codes:
        children = [c for c in schedules if c.startswith(ph + ".")]
        if children:
            s = min(schedules[c][0] for c in children)
            e = max(schedules[c][1] for c in children)
            schedules[ph] = (s, e)

    # Build week calendar (covering start → max end)
    end_overall = max(deadline_date, *(e for _, e in schedules.values()))
    total_weeks = ((end_overall - start_date).days // 7) + 1
    monday = start_date - timedelta(days=start_date.weekday())
    weeks = week_boundaries(monday, total_weeks)

    out_modules: list[ModuleSchedule] = []
    by_code = {m.code: m for m in modules}
    for code in (m.code for m in modules):  # preserve original order
        if code not in schedules:
            continue
        s, e = schedules[code]
        ws_idx = week_index(s, monday)
        we_idx = week_index(e, monday)
        m = by_code[code]
        out_modules.append(ModuleSchedule(
            code=code, feature=m.feature, is_phase=m.is_phase,
            md=m.md, start=s, end=e,
            week_start=ws_idx, week_end=we_idx,
        ))

    return {
        "modules": [ms.__dict__ for ms in out_modules],
        "sprints": [
            {"index": i + 1, "week_start": str(ws), "week_end": str(we)}
            for i, (ws, we) in enumerate(weeks)
        ],
        "anchor_monday": str(monday),
        "total_weeks": total_weeks,
        "capacity_warning": capacity_warning,
    }


# ── Resource allocation ──────────────────────────────────────────────────────

# Default 8 roles in the order they appear in `3. Delivery Plan` Resource Planning
DEFAULT_ROLES = [
    "Project Manager",
    "Technical Lead",
    "Developer",
    "Business Analyst",
    "Quality Controller",
    "Designer",
    "Devops",
    "AI Engineer",
]


def compute_resource_allocation(
    gantt: dict,
    total_md: float,
    team_size: int,
    has_ai: bool = True,
    has_designer: bool = True,
    coding_start_week: int = 2,
    uat_weeks: int = 2,
) -> dict:
    """Return per-role × per-week allocation map.

    Patterns (rule-of-thumb for outsourcing):
      Project Manager   : 1.0 every week, including UAT and post-launch buffer.
      Business Analyst  : 1.0 W1 (BRD writing), 0.5 W2 (clarifications),
                          0.2 every UAT week (acceptance criteria review).
      Technical Lead    : 1.0 first 2 sprints (architecture); 0.5 thereafter.
      Developer         : 1.0 from `coding_start_week` until end of coding window
                          (Dev Done milestone). 0.0 in UAT.
      AI Engineer       : 0.5 first 2 weeks (prototyping), 1.0 mid-coding window,
                          0.5 in UAT. Skipped if has_ai=False.
      Quality Controller: 0.5 in W2, 1.0 from W3 to end of UAT.
      Designer          : 1.0 from W3 to end of coding window. Skipped if False.
      Devops            : 0.2 in W2 (env setup), 0.2 at Dev Done week,
                          0.2 at UAT end (deploy).
    """
    sprints = gantt["sprints"]
    total_weeks = gantt["total_weeks"]
    if total_weeks <= 0:
        return {"roles": {}, "total_weeks": 0}

    # Coding window = weeks containing any L2 module
    l2_modules = [m for m in gantt["modules"] if not m["is_phase"]]
    if not l2_modules:
        coding_end = total_weeks
    else:
        coding_end = max(m["week_end"] for m in l2_modules)

    uat_end = min(total_weeks, coding_end + uat_weeks)

    def empty_row() -> dict[int, float]:
        return {w: 0.0 for w in range(1, total_weeks + 1)}

    roles: dict[str, dict[int, float]] = {r: empty_row() for r in DEFAULT_ROLES}

    # Project Manager — full-time, all weeks
    for w in range(1, uat_end + 1):
        roles["Project Manager"][w] = 1.0

    # Business Analyst
    if total_weeks >= 1:
        roles["Business Analyst"][1] = 1.0
    if total_weeks >= 2:
        roles["Business Analyst"][2] = 0.5
    for w in range(coding_end + 1, uat_end + 1):
        roles["Business Analyst"][w] = 0.2

    # Technical Lead
    for w in range(1, min(2, total_weeks) + 1):
        roles["Technical Lead"][w] = 1.0
    for w in range(3, coding_end + 1):
        roles["Technical Lead"][w] = 0.5

    # Developer
    for w in range(coding_start_week, coding_end + 1):
        roles["Developer"][w] = 1.0

    # AI Engineer
    if has_ai:
        for w in range(1, min(2, total_weeks) + 1):
            roles["AI Engineer"][w] = 0.5
        mid_start = max(coding_start_week, 3)
        mid_end = max(mid_start, coding_end - 1)
        for w in range(mid_start, mid_end + 1):
            roles["AI Engineer"][w] = 1.0
        for w in range(coding_end + 1, uat_end + 1):
            roles["AI Engineer"][w] = 0.5
    else:
        roles.pop("AI Engineer")

    # Quality Controller
    if total_weeks >= 2:
        roles["Quality Controller"][2] = 0.5
    for w in range(3, uat_end + 1):
        roles["Quality Controller"][w] = 1.0

    # Designer
    if has_designer:
        for w in range(3, coding_end + 1):
            roles["Designer"][w] = 1.0
    else:
        roles.pop("Designer")

    # Devops
    if total_weeks >= 2:
        roles["Devops"][2] = 0.2
    if coding_end >= 1:
        roles["Devops"][coding_end] = 0.2
    if uat_end >= 1:
        roles["Devops"][uat_end] = 0.2

    # Capacity check: sum allocations × 5 days
    total_capacity_md = sum(
        sum(week_alloc.values()) * WORKING_DAYS_PER_WEEK
        for week_alloc in roles.values()
    )
    capacity_warning = None
    if total_capacity_md < total_md:
        capacity_warning = (
            f"Allocated capacity {total_capacity_md:.0f} MD < project total {total_md:.0f} MD. "
            f"Consider increasing team_size or extending deadline."
        )

    return {
        "roles": {r: dict(weeks) for r, weeks in roles.items()},
        "total_weeks": total_weeks,
        "coding_end_week": coding_end,
        "uat_end_week": uat_end,
        "total_capacity_md": total_capacity_md,
        "capacity_warning": capacity_warning,
    }


# ── Deliverable milestones ───────────────────────────────────────────────────

def propose_deliverable_milestones(
    start_date: date,
    total_md: float,
    team_size: int,
    has_post_launch: bool = True,
    max_develop_plus_uat_months: float = 2.0,
) -> list[dict]:
    """Return 5 standard BnK outsourcing milestones with proposed dates.

    Enforces: develop_weeks + uat_weeks ≤ max_develop_plus_uat_months × 4 weeks.
    If the naive timeline exceeds this, team_size is scaled up automatically
    and a `capacity_note` is added to the development milestone dict.

    Milestone structure per row in `3. Delivery Plan` (rows 30-34):
      seq | name | start | end | deliverable (col F)
    """
    # UAT length: 2 weeks for POC (≤100 MD), 4 weeks for full project
    uat_weeks = 2 if total_md <= 100 else 4
    max_weeks = int(max_develop_plus_uat_months * 4)  # 2 months = 8 weeks
    max_dev_weeks = max_weeks - uat_weeks

    coding_weeks = md_to_calendar_weeks(total_md, team_size)
    capacity_note = None
    if coding_weeks > max_dev_weeks:
        min_size = normalize_team_size_for_constraint(
            total_md,
            max_total_months=max_develop_plus_uat_months,
            uat_weeks=uat_weeks,
        )
        capacity_note = (
            f"team_size scaled {team_size}→{min_size} to fit {max_develop_plus_uat_months:.0f}-month constraint"
        )
        team_size = min_size
        coding_weeks = md_to_calendar_weeks(total_md, team_size)

    contract = {
        "seq": 1,
        "name": "Contract Signoff",
        "start": start_date,
        "end": start_date,
        "deliverable": "Signed contract & project kick-off confirmation",
    }

    brd_end = add_business_days(start_date, 5)  # 1 sprint of BA work
    requirement = {
        "seq": 2,
        "name": "Requirement Confirmation / BRD Signoff",
        "start": start_date,
        "end": brd_end,
        "deliverable": "Business Requirement Document (BRD) — reviewed and signed off by client",
    }

    dev_start = add_business_days(brd_end, 1)
    dev_end = add_business_days(dev_start, coding_weeks * 5 - 1)
    development: dict = {
        "seq": 3,
        "name": "Development Complete — UAT Ready",
        "start": dev_start,
        "end": dev_end,
        "deliverable": (
            "System deployed to UAT environment; "
            "test cases prepared; test report template shared with client"
        ),
    }
    if capacity_note:
        development["capacity_note"] = capacity_note

    uat_start = add_business_days(dev_end, 1)
    uat_end = add_business_days(uat_start, uat_weeks * 5 - 1)
    uat = {
        "seq": 4,
        "name": "UAT Complete — Acceptance Signoff",
        "start": uat_start,
        "end": uat_end,
        "deliverable": (
            "Signed UAT acceptance; source code handover; "
            "system documentation (User Guide + Technical Spec)"
        ),
    }

    out = [contract, requirement, development, uat]

    if has_post_launch:
        ps_start = add_business_days(uat_end, 1)
        ps_end = add_business_days(ps_start, 10 - 1)  # 2-week support window
        out.append({
            "seq": 5,
            "name": "Post-Launch Support Complete",
            "start": ps_start,
            "end": ps_end,
            "deliverable": "Bug-fix SLA fulfilled; warranty period closed; handover report",
        })

    return out
