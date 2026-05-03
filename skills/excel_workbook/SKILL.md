---
name: excel_workbook
description: Procedures for auditing and patching BnK WBS .xlsx files via the audit_workbook + patch_workbook tools. Use when fixing a half-filled or post-render WBS workbook, or when adding a new role / hierarchy / TOTAL row.
---

# Excel Workbook Skill

This skill covers the full repair workflow for a BnK WBS workbook. It is the
companion to `delivery_planning` — that one fills the Delivery Plan; this one
fixes everything else.

## Sheet & named-range conventions

A correct BnK WBS workbook has these sheets:

| Sheet | Purpose |
|---|---|
| `1. Effort` | Module × role effort + cost summary. VLOOKUPs into `2. WBS`. |
| `2. WBS` | L1 phase / L2 module / L3 sub-module / L4 leaf task hierarchy. |
| `3. Delivery Plan` | Gantt + resource allocation + deliverable milestones. |
| `3. Delivery Plan (By Month)` | Same gantt at month granularity. |
| `4. Master Data` | Rates (USD/MD) + role allocation percentages. |

Required workbook-scoped named ranges:

| Name | Points to |
|---|---|
| `proj_code` | `'2. WBS'!$D$2` |
| `proj_name` | `'2. WBS'!$B$3` |
| `proj_currency_rate` | `'1. Effort'!$H$1` |
| `pct_pm` / `pct_ba` / `pct_qc` | `'4. Master Data'!$C$4` / `$C$5` / `$C$7` |
| `rate_pm` / `rate_ba` / `rate_dev` / `rate_qc` | `'4. Master Data'!$C$11..C$14` |
| `pct_ai` / `rate_ai` | (added by `upsert_master_role` for AI Engineer projects) |

## Audit-then-patch workflow

```
audit_workbook(xlsx_path)          # 1. read-only, returns findings
                                   #
patch_workbook("upsert_master_role", ...)        # if missing AI Engineer
patch_workbook("inject_wbs_hierarchy", ...)      # if WBS missing L1/L2 rows
patch_workbook("clear_wbs_junk_rows", "{}")      # if junk past last data
patch_workbook("add_wbs_total_row", "{}")        # if no TOTAL row
patch_workbook("rebuild_effort_modules", ...)    # if Effort module IDs don't match WBS
patch_workbook("rebuild_effort_total", "{}")     # to fix hardcoded SUM()
```

## Operation payload schemas

### inject_wbs_hierarchy

```json
{
  "phases": [
    {
      "code": "I",
      "feature": "REQUIREMENT GATHERING",
      "modules": [
        {"code": "I.A", "feature": "Discovery", "leaf_codes": [1, 2, 3]},
        {"code": "I.B", "feature": "BRD",       "leaf_codes": [4, 5]}
      ]
    }
  ]
}
```

`leaf_codes` are the **numeric values in WBS col B** (not row indices). The
operation locates the leaf row by its col-B value and inserts the hierarchy
row immediately above it. Idempotent — codes that already exist are skipped.

### upsert_master_role

```json
{
  "role_label": "AI Engineer",
  "pct_on_dev": 0.0,
  "rate_usd": 600,
  "pct_named_range": "pct_ai",
  "rate_named_range": "rate_ai",
  "remark": "AI/ML engineering rate"
}
```

`pct_on_dev` = 0.0 means AI work is captured as md_be in WBS leaf tasks
rather than as an overhead percentage of dev. Set `pct_on_dev > 0` only if
you want a flat % of dev effort allocated to this role.

### clear_wbs_junk_rows / add_wbs_total_row / rebuild_effort_total

No payload. Empty `{}` is fine.

### rebuild_effort_modules

```json
{ "module_codes": ["I", "I.A", "I.B", "II", "II.A", "II.B", "II.C", "II.D", "III", "III.A", "III.B"] }
```

Order MUST be: each L1 phase followed by its L2 modules (canonical hierarchical
order, mirroring the WBS sheet).

### write_master_planning / write_resource_planning / write_deliverable_milestones

These take the JSON output of `compute_delivery_plan` directly. See
`delivery_planning` skill for end-to-end example.

## Critical invariants (validators enforce)

1. **Effort col B (module IDs) must match WBS col B.** If `2. WBS` has rows
   with col B = `"I"`, `"I.A"`, `"II"`, ..., `"III.B"`, then `1. Effort`
   col B MUST list the same codes in the same order. Otherwise VLOOKUP
   returns blank.

2. **WBS must have at least one L1 row per phase.** L4 leaves alone are not
   enough — the Effort sheet's TOTAL row sums L1 rows only.

3. **TOTAL row sums L1 only.** Summing all rows double-counts (L1 already
   rolls up children).

4. **Junk rows past max data hurt the file size and confuse Excel's
   autofilter.** Run `clear_wbs_junk_rows` after every render.

5. **Named ranges must resolve.** Adding a role without registering its
   named range will leave WBS / Effort formulas with `#NAME?` errors.

## Anti-patterns

- ❌ Editing `4. Master Data` cells directly without going through
  `upsert_master_role` — you'll forget the named range.
- ❌ Inserting columns into `1. Effort` mid-sheet — breaks the merged
  "Effort (MD)" / "Cost (USD)" headers. To add a new role's effort
  column, append to the right (cols P, Q) instead.
- ❌ Calling `inject_wbs_hierarchy` without first running `upsert_task`
  to populate the WBS state — you'll have nothing to roll up.
- ❌ Hardcoding sprint week values (W1..W20) in `3. Delivery Plan` cells —
  let `write_master_planning` compute them from gantt data.
