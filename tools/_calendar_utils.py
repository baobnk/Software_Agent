"""Calendar helpers shared by delivery_planner_core and timeline_ops.

Pure functions; no IO, no openpyxl dependency.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

WORKING_DAYS_PER_WEEK = 5
WORKING_DAYS_PER_MONTH = 20  # 5 days × 4 weeks (BnK convention)


def add_business_days(start: date, days: int) -> date:
    """Skip weekends. `days=0` returns start unchanged."""
    if days <= 0:
        return start
    cur = start
    remaining = days
    while remaining > 0:
        cur = cur + timedelta(days=1)
        if cur.weekday() < 5:
            remaining -= 1
    return cur


def business_days_between(a: date, b: date) -> int:
    """Inclusive count of weekdays from `a` to `b`. Returns 0 if b < a."""
    if b < a:
        return 0
    days = 0
    cur = a
    while cur <= b:
        if cur.weekday() < 5:
            days += 1
        cur += timedelta(days=1)
    return days


def week_boundaries(start: date, num_weeks: int) -> list[tuple[date, date]]:
    """Return list of (week_start, week_end) Mon→Fri pairs covering `num_weeks`
    starting from the Monday of `start`'s week (or `start` itself if Mon)."""
    monday = start - timedelta(days=start.weekday())
    out = []
    for i in range(num_weeks):
        ws = monday + timedelta(weeks=i)
        we = ws + timedelta(days=4)
        out.append((ws, we))
    return out


def md_to_calendar_weeks(total_md: float, team_size: int) -> int:
    """Convert man-days + parallel team size into calendar weeks (rounded up)."""
    if team_size <= 0:
        team_size = 1
    weeks = total_md / (team_size * WORKING_DAYS_PER_WEEK)
    return max(1, math.ceil(weeks))


def derive_team_size(total_md: float, deadline_months: float) -> int:
    """Suggest team size given total MD and customer deadline in months.

    Rule of thumb (BnK outsourcing): one full-time engineer delivers ~20 MD/month.
    Clipped to [2, 8] — single-person projects need a buffer, large teams hit
    coordination overhead.
    """
    if deadline_months <= 0:
        return 2
    raw = total_md / (deadline_months * WORKING_DAYS_PER_MONTH)
    return max(2, min(8, math.ceil(raw)))


def week_index(d: date, anchor_monday: date) -> int:
    """1-based week index of `d` within the schedule starting at `anchor_monday`."""
    days = (d - anchor_monday).days
    return days // 7 + 1
