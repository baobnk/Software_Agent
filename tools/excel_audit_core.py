"""Read-only audit of a BnK WBS workbook.

Returns a structured report describing anything that would prevent the
file from opening cleanly in Excel: missing hierarchy rows, broken
VLOOKUP targets, junk rows past the data, missing roles, missing named
ranges, missing TOTAL row.

This is the entry point for `audit_workbook` @tool — see tools/excel_audit.py.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .excel_workbook_core import (
    EFFORT_DATA_START,
    PathLike,
    SHEET_DELIVERY,
    SHEET_EFFORT,
    SHEET_MASTER,
    SHEET_WBS,
    WBS_COL_FEATURE,
    WBS_COL_NUM,
    WBS_COL_REFCODE,
    WBS_DATA_START,
    cell_has_value,
    find_last_data_row,
    open_wb,
)

REQUIRED_NAMED_RANGES = {
    "proj_code", "proj_name",
    "pct_pm", "pct_ba", "pct_qc",
    "rate_pm", "rate_ba", "rate_dev", "rate_qc",
}

REQUIRED_ROLES_PCT = {"PM", "BA", "QC"}  # Developer is the base unit (100%)
REQUIRED_ROLES_RATE = {"PM", "BA", "Developer", "QC"}


def audit_workbook(path: PathLike) -> dict[str, Any]:
    """Return a structured audit dict for a BnK WBS workbook.

    Top-level keys:
      ok               — bool, True if no findings
      file             — absolute path
      sheets           — list of sheet names
      named_ranges     — dict[name → target cell]
      missing_named    — set of required names not present
      wbs              — { last_data_row, junk_row_count, has_total_row,
                           has_l1_rows, has_l2_rows, leaf_count }
      effort           — { module_ids: list[str], has_total_row,
                           vlookup_targets_present: bool }
      delivery         — { master_planning_filled, resource_roles, milestones_filled }
      master_data      — { roles_pct: list[str], roles_rate: list[str],
                           missing_roles: set[str] }
      findings         — list[str], human-readable issues
    """
    p = Path(path)
    wb = open_wb(p)

    findings: list[str] = []
    report: dict[str, Any] = {
        "ok": True,
        "file": str(p.resolve()),
        "sheets": list(wb.sheetnames),
        "named_ranges": {n: wb.defined_names[n].value for n in wb.defined_names},
        "findings": findings,
    }

    # ── Named ranges
    have = set(wb.defined_names)
    missing = REQUIRED_NAMED_RANGES - have
    report["missing_named"] = sorted(missing)
    if missing:
        findings.append(f"Missing named ranges: {sorted(missing)}")

    # ── 2. WBS sheet
    if SHEET_WBS not in wb.sheetnames:
        findings.append(f"Sheet missing: {SHEET_WBS}")
    else:
        ws = wb[SHEET_WBS]
        last = find_last_data_row(ws, start_row=WBS_DATA_START,
                                  check_cols=(WBS_COL_NUM, WBS_COL_REFCODE, WBS_COL_FEATURE))
        # Count only rows past `last` that actually have ANY non-None cell
        # (openpyxl's max_row may be inflated by dimension cache after delete_rows)
        junk = 0
        for r in range(last + 2, ws.max_row + 1):  # last+1 = TOTAL slot; junk starts at +2
            for c in range(1, ws.max_column + 1):
                if ws.cell(r, c).value is not None:
                    junk += 1
                    break

        # Detect L1/L2 rows: col B is a non-numeric str like "I", "I.A"
        l1_count = 0
        l2_count = 0
        leaf_count = 0
        total_row = False
        for r in range(WBS_DATA_START, last + 1):
            v = ws.cell(r, WBS_COL_NUM).value
            d = ws.cell(r, WBS_COL_FEATURE).value
            if isinstance(v, str):
                if "." in v:
                    l2_count += 1
                else:
                    l1_count += 1
            elif isinstance(v, (int, float)):
                leaf_count += 1
            if isinstance(d, str) and d.strip().upper() == "TOTAL":
                total_row = True

        report["wbs"] = {
            "last_data_row": last,
            "junk_row_count": junk,
            "has_total_row": total_row,
            "l1_row_count": l1_count,
            "l2_row_count": l2_count,
            "leaf_count": leaf_count,
        }
        if junk > 5:
            findings.append(f"WBS sheet has ~{junk} junk rows past row {last}")
        if l1_count == 0:
            findings.append("WBS sheet missing L1 phase rows (I, II, III) — Effort VLOOKUPs will fail")
        if l2_count == 0:
            findings.append("WBS sheet missing L2 module rows (I.A, I.B, ...) — Effort VLOOKUPs will fail")
        if not total_row:
            findings.append("WBS sheet missing TOTAL row")

    # ── 1. Effort sheet
    if SHEET_EFFORT not in wb.sheetnames:
        findings.append(f"Sheet missing: {SHEET_EFFORT}")
    else:
        ws = wb[SHEET_EFFORT]
        module_ids: list[str] = []
        total_row = False
        for r in range(EFFORT_DATA_START, ws.max_row + 1):
            b = ws.cell(r, 2).value
            c = ws.cell(r, 3).value
            if isinstance(b, str) and b.strip():
                module_ids.append(b.strip())
            if isinstance(c, str) and c.strip().upper() == "TOTAL":
                total_row = True

        wbs_ids = set()
        if SHEET_WBS in wb.sheetnames:
            wbs = wb[SHEET_WBS]
            for r in range(WBS_DATA_START, wbs.max_row + 1):
                v = wbs.cell(r, WBS_COL_NUM).value
                if isinstance(v, str):
                    wbs_ids.add(v.strip())
        unmatched = [m for m in module_ids if m not in wbs_ids]

        report["effort"] = {
            "module_ids": module_ids,
            "has_total_row": total_row,
            "unmatched_module_ids": unmatched,
        }
        if unmatched:
            findings.append(f"Effort sheet has {len(unmatched)} module IDs that don't match any WBS row: {unmatched[:5]}{'...' if len(unmatched) > 5 else ''}")

    # ── 3. Delivery Plan
    if SHEET_DELIVERY in wb.sheetnames:
        ws = wb[SHEET_DELIVERY]
        # Master Planning rows 7-17 — cols D, E for dates
        mp_filled = 0
        mp_total = 0
        for r in range(7, 18):
            if cell_has_value(ws, r, 2) or cell_has_value(ws, r, 3):
                mp_total += 1
                d = ws.cell(r, 4).value
                if d not in (None, "TBD", ""):
                    mp_filled += 1

        # Resource Planning rows 20-26
        roles = []
        for r in range(20, 30):
            v = ws.cell(r, 3).value
            if isinstance(v, str) and v.strip() and v.strip().upper() != "TOTAL":
                roles.append(v.strip())

        # Deliverables Milestone rows 30-34
        ms_filled = 0
        ms_total = 0
        for r in range(30, 36):
            if cell_has_value(ws, r, 3):
                ms_total += 1
                d = ws.cell(r, 4).value
                if d not in (None, "TBD", ""):
                    ms_filled += 1

        report["delivery"] = {
            "master_planning_filled": f"{mp_filled}/{mp_total}",
            "resource_roles": roles,
            "deliverable_milestones_filled": f"{ms_filled}/{ms_total}",
        }
        if mp_filled < mp_total:
            findings.append(f"Delivery Plan: {mp_total - mp_filled} module rows still TBD/blank")
        if "AI Engineer" not in roles and "AI/ML" not in roles:
            findings.append("Delivery Plan: no AI Engineer role in Resource Planning")
        if ms_filled < ms_total:
            findings.append(f"Delivery Plan: {ms_total - ms_filled} deliverable milestones still TBD")

    # ── 4. Master Data
    if SHEET_MASTER in wb.sheetnames:
        ws = wb[SHEET_MASTER]
        roles_pct: list[str] = []
        roles_rate: list[str] = []
        for r in range(2, ws.max_row + 1):
            label = ws.cell(r, 2).value
            val = ws.cell(r, 3).value
            if not isinstance(label, str):
                continue
            label = label.strip()
            if label in {"BU", "OB", "Role"} or not label:
                continue
            if isinstance(val, (int, float)) and val < 1:
                roles_pct.append(label)
            elif isinstance(val, (int, float)):
                roles_rate.append(label)
        missing_roles = (REQUIRED_ROLES_PCT - set(roles_pct)) | (REQUIRED_ROLES_RATE - set(roles_rate))
        report["master_data"] = {
            "roles_pct": roles_pct,
            "roles_rate": roles_rate,
            "missing_roles": sorted(missing_roles),
        }
        if missing_roles:
            findings.append(f"Master Data missing rates/percentages for: {sorted(missing_roles)}")

    report["ok"] = len(findings) == 0
    return report


def format_audit(report: dict[str, Any]) -> str:
    """Pretty-print audit report as human-readable text."""
    lines = []
    lines.append(f"AUDIT: {report['file']}")
    lines.append(f"OK: {report['ok']}")
    if report.get("findings"):
        lines.append("\nFindings:")
        for f in report["findings"]:
            lines.append(f"  - {f}")
    if report.get("wbs"):
        w = report["wbs"]
        lines.append(f"\nWBS: leaf={w['leaf_count']} L1={w['l1_row_count']} L2={w['l2_row_count']} "
                     f"last_row={w['last_data_row']} junk={w['junk_row_count']} total_row={w['has_total_row']}")
    if report.get("effort"):
        e = report["effort"]
        lines.append(f"Effort: modules={len(e['module_ids'])} unmatched={len(e['unmatched_module_ids'])} "
                     f"total_row={e['has_total_row']}")
    if report.get("delivery"):
        d = report["delivery"]
        lines.append(f"Delivery: master_planning={d['master_planning_filled']} "
                     f"milestones={d['deliverable_milestones_filled']} roles={d['resource_roles']}")
    if report.get("master_data"):
        m = report["master_data"]
        lines.append(f"Master Data: pct={m['roles_pct']} rate={m['roles_rate']} missing={m['missing_roles']}")
    return "\n".join(lines)
