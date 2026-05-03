# BnK WBS Template — Fill Tool Spec

> Detailed spec for Phase 10 tools that fill `[BnK] Template - WBS.xlsx`.
> Critical: PRESERVE all formulas (VLOOKUP, CONCATENATE, SUM) and formatting.

---

## Template structure (verified by openpyxl read)

Template path: `/mnt/f/code/agent/WBS_Agent/WBS/[BnK] Template - WBS.xlsx`

### Sheets
| Sheet | Role | Editable cells | Formulas (don't touch) |
|-------|------|---------------|----------------------|
| `0. How to use` | Documentation | – | – |
| `1. Effort` | Auto-summary | – | All cells (uses VLOOKUP from `2. WBS`) |
| `2. WBS` | **MAIN — agent fills here** | B, C, D, E, G, H, L columns of L4 rows | F (Total MD), I (BA), J (QC), K (PM), ref code formula |
| `3. Delivery Plan (By Month)` | Sprint plan, monthly view | D, E (Start/End dates), F-T (sprint cells) | C column (uses VLOOKUP) |
| `3. Delivery Plan` | Sprint plan, weekly view | Same | Same |
| `4. Master Data` | Multipliers + rates | C3-C6 (percentages), C10-C13 (rates) | – |

### Sheet "2. WBS" — Row anatomy

```
Row  | Col B    | Col C            | Col D         | Col E       | Col F  | Col G  | Col H | Col I    | Col J    | Col K    | Col L
-----+----------+------------------+---------------+-------------+--------+--------+-------+----------+----------+----------+----------
4    | #        | Ref. Code        | Features      | Description | Total  | BE     | FE    | BA       | QC       | PM       | Remark
                                                                  | (MD)   | (MD)   | (MD)  | (MD)     | (MD)     | (MD)     |

5    |          |                  |               |             | =SUM   | =SUM   | =SUM  | =SUM     | =SUM     | =SUM     |        ← Grand total formula

6    | I        |                  | SET UP & ...  |             | =SUM   | =SUM/2 |...    |          |          |          |        ← L1 phase row

7    | A        | (formula)        | Solution Des. |             | =SUM   | =SUM   |...    |          |          |          |        ← L2 (display "I.A")

8    | 1        | =CONCATENATE($D$2&"-",B9) | Database Design | + ... |=SUM | 1   | -     | =SUM*MD! | =SUM*MD! | =SUM*MD! |        ← L4 leaf
```

### Sheet "4. Master Data" — Cell map

```
C3 = PM percentage (default 0.05)
C4 = BA percentage (default 0.10)
C5 = Developer (empty, baseline)
C6 = QC percentage (default 0.30)
C10 = PM rate
C11 = BA rate
C12 = Developer rate
C13 = QC rate
A1 = "BU" header (don't change)
```

### Project Code cell

```
"2. WBS"!$D$2 = Project Code (e.g., "BNK")
   ↑ Used by CONCATENATE formula in C column for ref codes
```

---

## Fill Tool API

### 10.1 `load_wbs_template(template_path, output_path, project_code)`
```python
def load_wbs_template(
    template_path: str = None,           # default: /WBS/[BnK] Template - WBS.xlsx
    output_path: str = None,             # default: /workspace/wbs_filled.xlsx
    project_code: str = "BNK",
) -> str:
    """Copy template to workspace, set Project Code in cell '2. WBS'!D2.

    Returns: path to copied workbook (now ready for filling).
    Raises: ValueError if template not found.
    """
```

**Implementation:**
```python
import shutil
from openpyxl import load_workbook

shutil.copy(template_path, output_path)
wb = load_workbook(output_path)  # keep formulas
ws = wb["2. WBS"]
ws["D2"] = project_code           # only change this — let CONCATENATE auto-update
wb.save(output_path)
return output_path
```

### 10.2 `set_wbs_project_metadata(workbook_path, project_name, project_code, currency_rate_vnd_per_usd)`
```python
def set_wbs_project_metadata(
    workbook_path: str,
    project_name: str,
    project_code: str,
    currency_rate_vnd_per_usd: float = 24500,
) -> str:
    """Fill project name in '2. WBS'!B2 and currency rate in '1. Effort'!I1.

    Affects: '2. WBS' B2 (e.g. "WBS OF MBAL IDP PHASE 2"), I1 currency.
    """
```

### 10.3 `clear_template_placeholder_rows(workbook_path)`
```python
def clear_template_placeholder_rows(workbook_path: str) -> str:
    """Clear example rows 6-76 in '2. WBS' (keep header row 4 + summary row 5).

    Removes: features, descriptions, BE/FE values from L1-L4 example rows.
    Preserves: formulas, formatting, ref code generation.
    """
```

**Implementation:**
```python
from openpyxl.cell import Cell

EDITABLE_COLS_L4 = ["B", "D", "E", "G", "H", "L"]   # # / Feature / Desc / BE / FE / Remark
EDITABLE_COLS_L1L3 = ["B", "D"]                     # # / Feature

ws = wb["2. WBS"]
for row in range(6, 77):
    for col in EDITABLE_COLS_L4:
        cell = ws[f"{col}{row}"]
        if not cell.value or not str(cell.value).startswith("="):
            cell.value = None
```

### 10.4 `add_wbs_phase_l1_row(workbook_path, phase_id, name, row_num=None)`
```python
def add_wbs_phase_l1_row(
    workbook_path: str,
    phase_id: str,                       # "I" | "II" | "III"
    name: str,                           # "SET UP & INSTALLATION"
    row_num: int = None,                 # auto-compute next available
) -> dict:
    """Insert a Level-1 phase row.

    Returns: {row_num, ref_code: ""} — L1 has no ref_code.
    """
```

**Implementation:**
- Find next empty row (starts from row 6)
- Set `B{n} = phase_id` (string "I"/"II"/"III")
- Set `D{n} = name`
- Leave C, E, G-K untouched (existing SUM formulas auto-aggregate sub-rows)

### 10.5 `add_wbs_subphase_l2_row(workbook_path, parent_phase_id, subphase_letter, name, row_num=None)`
```python
def add_wbs_subphase_l2_row(
    workbook_path: str,
    parent_phase_id: str,                # "I"
    subphase_letter: str,                # "A"
    name: str,                           # "Solution Design"
    row_num: int = None,
) -> dict:
    """Insert a Level-2 sub-phase row, child of parent_phase_id.

    Cell B{n} = "A" (just the letter; display sheet shows "I.A" via formula)
    Returns: {row_num, full_id: "I.A"}
    """
```

### 10.6 `add_wbs_module_l3_row(workbook_path, parent_l2_full_id, module_num, name)`
```python
def add_wbs_module_l3_row(
    workbook_path: str,
    parent_l2_full_id: str,              # "II.A"
    module_num: int,                     # 1, 2, 3...
    name: str,                           # "Common Module"
) -> dict:
    """Insert an L3 module row (only used in larger projects)."""
```

### 10.7 `add_wbs_task_l4_row(workbook_path, ...)`  ← THE BIG ONE

```python
def add_wbs_task_l4_row(
    workbook_path: str,
    parent_l2_or_l3: str,                # "I.A" or "II.A.1"
    task_num: int,                       # 1, 2, 3...
    feature: str,                        # "Database Design"
    description: str,                    # "+ Design DB Schema\n+ Set up..."
    md_be: float = 0,                    # backend man-days
    md_fe: float = 0,                    # frontend man-days
    md_ai: float = 0,                    # AI man-days (some templates have this)
    remark: str = "",
    source_fr_id: str = "",              # for traceability
) -> dict:
    """Insert L4 leaf task with effort.

    Cells filled:
      B{n} = task_num                    (e.g., "1")
      C{n} = =CONCATENATE($D$2&"-",B{n}) (auto ref code)
      D{n} = feature                     (e.g., "Database Design")
      E{n} = description
      G{n} = md_be
      H{n} = md_fe (or "-" if 0)
      L{n} = remark
      F{n} = =SUM(G{n}:K{n})             (Total MD formula — DON'T overwrite)
      I{n} = =SUM(G{n}:H{n})*'4. Master Data'!$C$5  (BA formula — DON'T overwrite)
      J{n} = =SUM(G{n}:H{n})*'4. Master Data'!$C$7  (QC formula — DON'T overwrite)
      K{n} = =SUM(G{n}:J{n})*'4. Master Data'!$C$4  (PM formula — DON'T overwrite)

    Returns: {row_num, ref_code: f"{project_code}-{task_num}"}
    """
```

**CRITICAL implementation note:**
- The formulas in F, I, J, K columns must already exist in the row from template.
- If row was cleared in step 10.3, RESTORE these formulas.
- Helper: `_ensure_l4_formulas(ws, row, project_code)` injects them if missing.

```python
def _ensure_l4_formulas(ws, row: int):
    if not ws[f"C{row}"].value:
        ws[f"C{row}"] = f"=CONCATENATE($D$2&\"-\",B{row})"
    if not ws[f"F{row}"].value:
        ws[f"F{row}"] = f"=SUM(G{row}:K{row})"
    if not ws[f"I{row}"].value:
        ws[f"I{row}"] = f"=SUM(G{row}:H{row})*'4. Master Data'!$C$5"
    if not ws[f"J{row}"].value:
        ws[f"J{row}"] = f"=SUM(G{row}:H{row})*'4. Master Data'!$C$7"
    if not ws[f"K{row}"].value:
        ws[f"K{row}"] = f"=SUM(G{row}:J{row})*'4. Master Data'!$C$4"
```

### 10.8 `set_master_data(workbook_path, pm_pct, ba_pct, qc_pct, pm_rate, ba_rate, dev_rate, qc_rate, currency)`
```python
def set_master_data(
    workbook_path: str,
    pm_pct: float = 0.05,
    ba_pct: float = 0.10,
    qc_pct: float = 0.30,
    pm_rate: float = 500,
    ba_rate: float = 400,
    dev_rate: float = 450,
    qc_rate: float = 350,
    currency: str = "USD",
) -> str:
    """Set Master Data sheet values.

    Cells:
      C3 = pm_pct
      C4 = ba_pct
      C6 = qc_pct
      C10 = pm_rate
      C11 = ba_rate
      C12 = dev_rate
      C13 = qc_rate
    """
```

### 10.9 `fill_delivery_plan_modules(workbook_path, modules_with_dates)`
```python
def fill_delivery_plan_modules(
    workbook_path: str,
    modules: list[dict],                  # [{module_id, start_date, end_date, sprint_marks}]
) -> str:
    """Fill '3. Delivery Plan' module rows.

    Each module gets:
      D{n} = start_date (YYYY-MM-DD or "Sprint 1")
      E{n} = end_date
      F{n}, G{n}, ... = sprint marks (e.g., "X" or duration)
    """
```

### 10.10 `fill_delivery_plan_resources(workbook_path, resource_allocation)`
```python
def fill_delivery_plan_resources(
    workbook_path: str,
    resource_allocation: dict,            # {"PM": [0.3,0.3,...], "BA": [...], ...}
) -> str:
    """Fill '3. Delivery Plan' Resource Planning section.

    Default rows in template:
      17: Project Manager
      18: Technical Lead
      19: Developer
      20: Business Analyst
      21: Quality Controller
      22: Designer
      23: DevOps
    Each row gets values per sprint (S1..Sn) showing FTE allocation.
    """
```

### 10.11 `fill_effort_summary_sheet(workbook_path)`
```python
def fill_effort_summary_sheet(workbook_path: str) -> str:
    """Verify '1. Effort' sheet — formulas should auto-recalculate.

    No-op if formulas intact; logs anomalies if any cell shows #REF or #N/A.
    """
```

### 10.12 `verify_template_integrity(workbook_path)`
```python
def verify_template_integrity(workbook_path: str) -> dict:
    """Run sanity checks on filled template.

    Returns: {
        ok: bool,
        issues: [
            "Sheet '1. Effort' row 15 has #REF",
            "Master Data C5 (Developer) is empty (should be blank, not numeric)",
            ...
        ],
        stats: {
            total_l4_tasks: 47,
            total_md: 235.6,
            phases: ["I", "II", "III"],
            modules: 8,
        }
    }
    """
```

---

## Standard fill flow (orchestrator calls)

```python
# 1. Load + setup
load_wbs_template(project_code="BNK-MBAL")
set_wbs_project_metadata(project_name="MBAL IDP Phase 2", currency_rate_vnd_per_usd=24500)
clear_template_placeholder_rows()
set_master_data(pm_pct=0.10, ba_pct=0.20, qc_pct=0.40, ...)  # insurance domain

# 2. Phase I: Setup
add_wbs_phase_l1_row(phase_id="I", name="SET UP & INSTALLATION")
add_wbs_subphase_l2_row(parent_phase_id="I", subphase_letter="A", name="Solution Design")
add_wbs_task_l4_row(parent="I.A", task_num=1, feature="Database Design",
                     description="+ Design DB Schema\n+ Set up indexes",
                     md_be=2, md_fe=0)
add_wbs_task_l4_row(parent="I.A", task_num=2, feature="System Design",
                     description="+ HLD\n+ DLD",
                     md_be=8, md_fe=2)
# ... (more I.A tasks)

add_wbs_subphase_l2_row(parent_phase_id="I", subphase_letter="B", name="System Operation")
# ... (deployment setup, monitoring)

# 3. Phase II: Development (per FR/module)
add_wbs_phase_l1_row(phase_id="II", name="DEVELOPMENT")
for module in modules:
    add_wbs_subphase_l2_row(parent_phase_id="II", subphase_letter=letter, name=module.name)
    for task in module.tasks:
        add_wbs_task_l4_row(parent=f"II.{letter}", task_num=t.num,
                             feature=t.feature, description=t.desc,
                             md_be=t.md_be, md_fe=t.md_fe,
                             source_fr_id=t.source_fr_id)

# 4. Phase III: Testing & Deployment
add_wbs_phase_l1_row(phase_id="III", name="TESTING & DEPLOYMENT")
add_wbs_subphase_l2_row(parent_phase_id="III", subphase_letter="A", name="System Testing & UAT")
# ... add SIT, UAT, bug fix tasks
add_wbs_subphase_l2_row(parent_phase_id="III", subphase_letter="B", name="Deployment & Maintenance")
# ... deploy + hypercare

# 5. Delivery plan
fill_delivery_plan_modules(modules=[...])
fill_delivery_plan_resources(resource_allocation={"PM": [0.3]*7, "Dev": [0,2,2,3,4,4,4], ...})

# 6. Verify
result = verify_template_integrity()
assert result["ok"], result["issues"]
```

---

## Edge cases to handle

1. **More than 70 L4 tasks** — template has formulas referencing rows 6-76. For larger projects, need to:
   - Insert new rows (preserves formulas if openpyxl handles ref shifting)
   - OR extend the SUM/VLOOKUP ranges programmatically
   - Recommended: use `ws.insert_rows(idx, amount)` then re-fill — openpyxl auto-shifts formulas

2. **Multiple WBS sheets** — template has both `2. WBS` and `3. WBS_General_BK` (alternative layout for some projects). Default: fill `2. WBS` only. Add `target_sheet` param to override.

3. **Currency mismatch** — rates in C10-C13 must be USD if currency="USD"; conversion happens via cell I1 (rate).

4. **Number formatting** — md_be values should be numeric (1.5, not "1.5"). Use `cell.value = float(md_be)`.

5. **Description with newlines** — use `\n` literal; openpyxl preserves it; need `cell.alignment = Alignment(wrap_text=True)`.

6. **Empty cells (no value)** — for `md_fe=0`, template uses "-" string in some rows, blank in others. Convention: use blank (None), let formula compute.

---

## Tools accept the template at runtime — user controls path

```python
@tool
def load_wbs_template(
    template_path: str = "",
    project_code: str = "BNK",
) -> str:
    """If template_path is empty, use BNK_TEMPLATE_PATH env var or default."""
    if not template_path:
        template_path = os.environ.get(
            "BNK_TEMPLATE_PATH",
            "/mnt/f/code/agent/WBS_Agent/WBS/[BnK] Template - WBS.xlsx"
        )
    ...
```

So user can swap templates via env var if BnK updates the template later.
