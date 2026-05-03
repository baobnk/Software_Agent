"""One-shot driver: fix Hotel_Recommendation_POC_WBS_v0_1_0.xlsx.

Pipeline (v0.2):
  1.  Audit input
  2.  Copy to v0_2_0
  3.  Update Master Data rates to BnK standard
  4.  Add AI Engineer role to Master Data
  5.  Consolidate WBS hierarchy (remove duplicate L4 flat leaves)
  6.  Insert AI/ML column into WBS sheet
  7.  Rebuild WBS L1/L2/L3 rollup formulas (now includes AI column)
  8.  Add TOTAL row to WBS
  9.  Clear junk rows from WBS
  10. Write Effort sheet headers + rebuild Effort module rows
  11. Normalize team_size to fit develop+UAT ≤ 2 months
  12. Compute delivery plan (gantt + resource allocation + milestones)
  13. HITL: confirm deliverable milestone dates
  14. Write Delivery Plan sheet
  15. Remove "3. Delivery Plan (By Month)" sheet (if present)
  16. Re-audit output

Usage:
  python scripts/fix_hotel_wbs.py \\
      --input /path/to/Hotel_Recommendation_POC_WBS_v0_1_0.xlsx \\
      --start 2026-05-04 --deadline 2026-08-04 \\
      --no-hitl     # skip prompt, accept proposed dates
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools._calendar_utils import derive_team_size
from tools.delivery_planner_core import (
    ModuleEffort,
    compute_gantt,
    compute_resource_allocation,
    normalize_team_size_for_constraint,
    propose_deliverable_milestones,
)
from tools.excel_audit_core import audit_workbook, format_audit
from tools.excel_delivery_core import (
    write_deliverable_milestones,
    write_master_planning,
    write_resource_planning,
)
from tools.excel_effort_core import (
    rebuild_for_modules,
    rebuild_total_row,
    write_effort_headers,
)
from tools.excel_master_data_core import update_role_pcts, update_role_rates, upsert_role
from tools.excel_wbs_core import (
    add_total_row,
    clear_junk_rows,
    consolidate_hierarchy,
    insert_ai_column_wbs,
    rebuild_l1_l2_rollups,
)
from tools.excel_workbook_core import (
    SHEET_DELIVERY_MONTH,
    SHEET_WBS,
    WBS_COL_AI,
    WBS_COL_BE,
    WBS_COL_FE,
    WBS_COL_FEATURE,
    WBS_COL_NUM,
    WBS_DATA_START,
    find_last_data_row,
    open_wb,
    save_wb,
)

# ── BnK standard rates (update only if user hasn't customised) ───────────────
BNK_RATES = {
    "PM": 2500,
    "BA": 2000,
    "Developer": 2500,
    "QC": 2000,
}
BNK_PCTS = {
    "PM": 0.05,
    "BA": 0.10,
    "QC": 0.10,
}
AI_RATE = 3000
AI_PCT = 0.0   # AI effort is tracked explicitly per task, not as a % of dev


def _read_wbs_modules(path: Path) -> tuple[list[ModuleEffort], float]:
    """Read consolidated WBS sheet → L1/L2 ModuleEffort list + total dev MD.

    dev MD = BE + FE + AI per L3/L4 row; aggregated up to L2 and L1.
    """
    wb = open_wb(path)
    ws = wb[SHEET_WBS]
    last = find_last_data_row(ws, start_row=WBS_DATA_START,
                              check_cols=(WBS_COL_NUM, WBS_COL_FEATURE))

    rows: list[dict] = []
    for r in range(WBS_DATA_START, last + 1):
        b = ws.cell(r, WBS_COL_NUM).value
        d = ws.cell(r, WBS_COL_FEATURE).value
        if not isinstance(b, str):
            continue
        b = b.strip()
        if not b or b.upper() == "TOTAL":
            continue
        be = ws.cell(r, WBS_COL_BE).value
        fe = ws.cell(r, WBS_COL_FE).value
        # AI column may not exist in older files; safely read it
        try:
            ai = ws.cell(r, WBS_COL_AI).value
        except Exception:
            ai = None
        be = float(be) if isinstance(be, (int, float)) else 0.0
        fe = float(fe) if isinstance(fe, (int, float)) else 0.0
        ai = float(ai) if isinstance(ai, (int, float)) else 0.0
        rows.append({
            "code": b, "feature": str(d) if d else "",
            "depth": b.count(".") + 1, "be": be, "fe": fe, "ai": ai,
        })

    # Aggregate L3 → L2 → L1 (dev MD = BE + FE + AI)
    md_by_code: dict[str, float] = {}
    for row in rows:
        if row["depth"] == 3:
            md_by_code[row["code"]] = row["be"] + row["fe"] + row["ai"]
    for row in rows:
        if row["depth"] == 2:
            prefix = row["code"] + "."
            md_by_code[row["code"]] = sum(
                md for c, md in md_by_code.items()
                if c.startswith(prefix) and c.count(".") == 2
            )
    for row in rows:
        if row["depth"] == 1:
            prefix = row["code"] + "."
            md_by_code[row["code"]] = sum(
                md for c, md in md_by_code.items()
                if c.startswith(prefix) and c.count(".") == 1
            )

    modules: list[ModuleEffort] = []
    l1_codes = [r["code"] for r in rows if r["depth"] == 1]
    seen: set[str] = set()
    for l1 in l1_codes:
        l1_row = next(r for r in rows if r["code"] == l1)
        modules.append(ModuleEffort(
            code=l1, feature=l1_row["feature"],
            md=md_by_code.get(l1, 0.0), is_phase=True,
        ))
        seen.add(l1)
        for r in rows:
            if r["depth"] == 2 and r["code"].startswith(l1 + "."):
                modules.append(ModuleEffort(
                    code=r["code"], feature=r["feature"],
                    md=md_by_code.get(r["code"], 0.0), is_phase=False,
                ))
                seen.add(r["code"])

    total_md = sum(md_by_code.get(c, 0.0) for c in l1_codes)
    return modules, total_md


def _hitl_confirm_milestones(proposed: list[dict]) -> list[dict]:
    """CLI HITL: display proposed milestones, accept edits, return confirmed list."""
    print("\n" + "=" * 70)
    print("HITL: Review proposed deliverable milestones (develop+UAT ≤ 2 months)")
    print("=" * 70)
    confirmed = [dict(m) for m in proposed]

    def _print_table():
        print(f"\n  {'#':>2}  {'Name':<48} {'Start':<12} {'End'}")
        print("  " + "-" * 82)
        for m in confirmed:
            note = f"  [{m.get('capacity_note','')}]" if m.get("capacity_note") else ""
            print(f"  {m['seq']:>2}  {m['name']:<48} {str(m['start']):<12} {str(m['end'])}{note}")
        print()

    while True:
        _print_table()
        cmd = input("  Enter=accept | 'edit <#>'=adjust | 'done'=confirm: ").strip()
        if not cmd or cmd.lower() == "done":
            break
        if cmd.lower().startswith("edit "):
            try:
                seq = int(cmd.split()[1])
            except (IndexError, ValueError):
                print("  Usage: edit <seq>")
                continue
            target = next((m for m in confirmed if m["seq"] == seq), None)
            if target is None:
                print(f"  Milestone #{seq} not found")
                continue
            for field_name, field_label in [("start", "Start"), ("end", "End")]:
                raw = input(f"    {field_label} [{target[field_name]}]: ").strip()
                if raw:
                    try:
                        target[field_name] = datetime.fromisoformat(raw).date()
                    except ValueError:
                        print(f"    Invalid date — keeping existing")
        else:
            print("  Unknown command. Try 'edit 3' or Enter to accept.")

    return confirmed


def main():
    ap = argparse.ArgumentParser(description="Fix BnK WBS Excel (add AI col, delivery plan, rates)")
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--start", required=True, type=str, help="Project start date YYYY-MM-DD")
    ap.add_argument("--deadline", required=True, type=str, help="Project deadline YYYY-MM-DD")
    ap.add_argument("--team-size", type=int, default=None,
                    help="Override auto-derived team size")
    ap.add_argument("--no-hitl", action="store_true",
                    help="Skip milestone confirmation prompt")
    ap.add_argument("--keep-delivery-month", action="store_true",
                    help="Keep '3. Delivery Plan (By Month)' sheet")
    args = ap.parse_args()

    src: Path = args.input.resolve()
    if not src.exists():
        sys.exit(f"Input not found: {src}")
    dst = src.with_name(src.stem.replace("v0_1_0", "v0_2_0") + src.suffix)
    if dst == src:
        dst = src.with_name(src.stem + "_fixed" + src.suffix)

    # ── 1. Audit input
    print(f"\n[1/16] Audit input: {src}")
    print(format_audit(audit_workbook(src)))

    # ── 2. Copy
    print(f"\n[2/16] Copy to: {dst}")
    shutil.copy2(src, dst)

    # ── 3. Update Master Data rates to BnK standard
    print(f"\n[3/16] Update Master Data rates → {BNK_RATES}")
    wb = open_wb(dst)
    rate_res = update_role_rates(wb, BNK_RATES)
    pct_res = update_role_pcts(wb, BNK_PCTS)
    for role, info in rate_res.items():
        print(f"  rate {role}: {info['old_rate']} → {info['new_rate']}")
    for role, info in pct_res.items():
        print(f"  pct  {role}: {info['old_pct']} → {info['new_pct']}")
    save_wb(wb, dst)

    # ── 4. Add AI Engineer role
    print(f"\n[4/16] Add AI Engineer role (rate={AI_RATE}, pct={AI_PCT})")
    wb = open_wb(dst)
    res = upsert_role(
        wb,
        role_label="AI Engineer",
        pct_on_dev=AI_PCT,
        rate_usd=AI_RATE,
        pct_named_range="pct_ai",
        rate_named_range="rate_ai",
        remark="AI/ML engineering",
    )
    save_wb(wb, dst)
    print(f"  AI Engineer: pct_row={res['pct_row']}, rate_row={res['rate_row']}")

    # ── 5. Consolidate WBS hierarchy (remove flat duplicate L4 leaf rows)
    print(f"\n[5/16] Consolidate WBS sheet")
    wb = open_wb(dst)
    cons = consolidate_hierarchy(wb)
    print(f"  {cons}")
    save_wb(wb, dst)

    # ── 6. Insert AI/ML column into WBS (between FE and BA)
    print(f"\n[6/16] Insert AI/ML column into WBS sheet")
    wb = open_wb(dst)
    ai_insert = insert_ai_column_wbs(wb)
    print(f"  {ai_insert}")
    save_wb(wb, dst)

    # ── 7. Rebuild WBS rollup formulas (now includes AI column)
    print(f"\n[7/16] Rebuild WBS L1/L2/L3 rollup formulas")
    wb = open_wb(dst)
    rb = rebuild_l1_l2_rollups(wb)
    print(f"  Rebuilt {rb['rebuilt_rows']} rows")
    save_wb(wb, dst)

    # ── 8. Add TOTAL row to WBS
    print(f"\n[8/16] Add WBS TOTAL row")
    wb = open_wb(dst)
    tot = add_total_row(wb)
    print(f"  TOTAL row at row {tot.get('row')} (summing {tot.get('summed_rows')})")
    save_wb(wb, dst)

    # ── 9. Clear junk rows from WBS
    print(f"\n[9/16] Clear WBS junk rows")
    wb = open_wb(dst)
    junk = clear_junk_rows(wb)
    print(f"  Removed {junk['removed']} junk rows (last data row={junk['kept_until_row']})")
    save_wb(wb, dst)

    # ── 10. Read modules + total dev MD
    print(f"\n[10/16] Read consolidated modules from WBS")
    modules, total_md = _read_wbs_modules(dst)
    print(f"  {len(modules)} modules, dev total_md = {total_md:.1f}")
    for m in modules:
        kind = "L1" if m.is_phase else "L2"
        print(f"    [{kind}] {m.code:<8} {m.md:>5.1f} MD  {m.feature[:50]}")

    if total_md <= 0:
        sys.exit("ERROR: total_md is 0 — nothing to schedule")

    # ── Rebuild Effort sheet
    print(f"\n[11/16] Rebuild Effort sheet (with AI column + formula PM/QC)")
    wb = open_wb(dst)
    write_effort_headers(wb)
    module_codes = [m.code for m in modules]
    em = rebuild_for_modules(wb, module_codes)
    print(f"  {em['module_count']} module rows, TOTAL at row {em['total_row']}")
    rt = rebuild_total_row(wb)
    print(f"  TOTAL sums L1 rows: {rt.get('summed_rows')}")
    save_wb(wb, dst)

    # ── 12. Normalize team size + compute delivery plan
    print(f"\n[12/16] Normalize timeline (develop+UAT ≤ 2 months)")
    start = datetime.fromisoformat(args.start).date()
    deadline = datetime.fromisoformat(args.deadline).date()

    if args.team_size:
        base_team = args.team_size
    else:
        deadline_months = (deadline - start).days / 30.0
        base_team = derive_team_size(total_md, deadline_months)

    # Enforce 2-month constraint
    min_team = normalize_team_size_for_constraint(total_md, max_total_months=2.0, uat_weeks=2)
    team_size = max(base_team, min_team)
    if team_size > base_team:
        print(f"  Team size raised {base_team}→{team_size} to satisfy 2-month constraint")
    else:
        print(f"  team_size={team_size} (base={base_team}, min_for_constraint={min_team})")
    print(f"  start={start}  deadline={deadline}  team_size={team_size}")

    gantt = compute_gantt(modules, total_md, start, deadline, team_size)
    if gantt.get("capacity_warning"):
        print(f"  ⚠ {gantt['capacity_warning']}")
    allocation = compute_resource_allocation(gantt, total_md, team_size, has_ai=True)
    if allocation.get("capacity_warning"):
        print(f"  ⚠ {allocation['capacity_warning']}")
    print(f"  Gantt: {gantt['total_weeks']} weeks; "
          f"coding ends W{allocation['coding_end_week']}, UAT ends W{allocation['uat_end_week']}")

    proposed = propose_deliverable_milestones(start, total_md, team_size)

    # ── 13. HITL confirm milestones
    if args.no_hitl:
        print(f"\n[13/16] HITL skipped — using proposed milestone dates")
        confirmed = proposed
    else:
        confirmed = _hitl_confirm_milestones(proposed)
    print("  Confirmed milestones:")
    for m in confirmed:
        print(f"    {m['seq']}. {m['name']}: {m['start']} → {m['end']}")

    # ── 14. Write Delivery Plan sheet
    print(f"\n[14/16] Write Delivery Plan sheet")
    wb = open_wb(dst)
    mp = write_master_planning(wb, gantt)
    print(f"  Master planning: {mp['rows_written']} rows over {mp['total_weeks']} weeks")
    rp = write_resource_planning(wb, allocation, gantt, deadline_date=deadline)
    print(f"  Resource planning: {rp['roles_written']} roles, TOTAL at row {rp['total_row']}")
    ms_w = write_deliverable_milestones(wb, confirmed)
    print(f"  Milestones: {ms_w['milestones_written']} written")
    save_wb(wb, dst)

    # ── 15. Remove "3. Delivery Plan (By Month)" sheet
    if not args.keep_delivery_month:
        print(f"\n[15/16] Remove '{SHEET_DELIVERY_MONTH}' sheet")
        wb = open_wb(dst)
        if SHEET_DELIVERY_MONTH in wb.sheetnames:
            del wb[SHEET_DELIVERY_MONTH]
            save_wb(wb, dst)
            print(f"  Removed.")
        else:
            print(f"  Sheet not found — skipped.")
    else:
        print(f"\n[15/16] Keeping '{SHEET_DELIVERY_MONTH}' (--keep-delivery-month)")

    # ── 16. Re-audit
    print(f"\n[16/16] Re-audit output: {dst}")
    print(format_audit(audit_workbook(dst)))
    print(f"\n✓ Done. Output: {dst}")


if __name__ == "__main__":
    main()
