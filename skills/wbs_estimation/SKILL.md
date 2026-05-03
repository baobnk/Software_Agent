---
name: wbs_estimation
description: BnK WBS estimation — hierarchy rules, multipliers, benchmarks, FR-to-task mapping. Loaded by the WBS workflow's create_react_agent.
when_to_load: agents.wbs_workflow (always while building WBS)
---

# WBS Estimation — Schema & Conventions

You decompose `raw_features.md` + `technical_design.md` into a WBS that
will be rendered into a BnK-standard `.xlsx`. Pipeline-wise, you run
**before** `run_brd_workflow` — meaning you OWN the canonical project
metadata. Pick `project_code`, `project_name`, `language` carefully:
they go into `workspace/project.json` and BRD will inherit them.

## Pipeline position (WBS-first)

1. You init the project: `init_wbs(project_code, project_name, language)`.
2. You decompose into tasks (L1 → L2 → L3 → L4) and estimate L4 effort.
3. You generate the FR ids the BRD will later formalize. Every L4 task
   that maps to a feature should set `source_feature_id="FR1"` (or FR2, FR3, …).
4. brd_workflow then formalizes those exact FR ids in §5.2 of the BRD.

## Hierarchy

| Level | Role | Code style | Effort | Examples |
|---|---|---|---|---|
| L1 | Phase | Roman numerals | 0 (rollup) | I, II, III |
| L2 | Sub-phase | `Phase.Letter` | 0 | I.A, I.B, II.A |
| L3 | Module | `Phase.Letter.Number` | 0 | II.A.1, II.A.2 |
| L4 | Leaf task | `<Type>-<Num>` | `md_be` and/or `md_fe` set | REQ-01, BE-01, FE-01, QC-01, DEP-01 |

Standard BnK phase structure (use unless project demands otherwise):

```
I.   Project Setup & Requirements
     I.A. Project initiation & planning
     I.B. Requirement finalization
II.  Development                     ← one L2 per major module
     II.A. <Module 1>
        II.A.1. <Sub-module>
           BE-01, BE-02, FE-01, …
III. Testing & Deployment
     III.A. System testing & QA
     III.B. UAT & bug fixing
     III.C. Deployment & handover
```

## Estimation guidelines (BnK benchmarks, man-days)

| Pattern | BE | FE | Notes |
|---|---:|---:|---|
| Simple CRUD page | 1.0 | 1.5 | Standard list/form |
| Auth / security module | 2.0–3.0 | 0.5 | Includes role/permission |
| Report / dashboard | 1.0 | 2.0–3.0 | Per dashboard view |
| Data import/export | 1.5–2.5 | 0.5 | CSV/Excel parser |
| 3rd-party API integration | 2.0–4.0 | 0.5 | Per integrated system |
| AI/ML feature | 3.0–8.0 | 0.5–1.0 | Highly variable |
| Workflow / approval flow | 2.0–3.5 | 1.5 | Multi-step state machine |
| Notification (email/SMS) | 1.0 | 0.5 | Per channel |

Multipliers:
- ×1.3–1.5 for unfamiliar tech stack.
- ×1.2 for first-of-kind in BnK portfolio.
- ×0.8 for repeat patterns BnK has built before.
- Cap any single L4 task at 8 md — split if larger.

## FR-to-Task mapping (traceability)

Every L4 task that implements a business feature MUST set
`source_feature_id="FR1"` (the FR id you choose; BRD will match).

Cross-cutting tasks (testing, deployment, security audit) can have empty
`source_feature_id` — they exist independently of FRs.

## Common L4 task templates

```python
# Backend API endpoint for FR1
upsert_task(code="BE-01", feature="POST /documents endpoint",
            hierarchy_level=4, parent_code="II.A.1",
            md_be=2.0, md_fe=0,
            source_feature_id="FR1")

# Frontend upload UI
upsert_task(code="FE-01", feature="Upload form with progress bar",
            hierarchy_level=4, parent_code="II.A.1",
            md_be=0, md_fe=1.5,
            source_feature_id="FR1")

# Cross-cutting deployment
upsert_task(code="DEP-01", feature="CI pipeline + Docker compose",
            hierarchy_level=4, parent_code="III.C",
            md_be=1.5, md_fe=0)
```

## Master data (rates + multipliers)

`MasterData` defaults match BnK standard. Override only when client-specific.

| Field | Default | Meaning |
|---|---:|---|
| `pct_pm` | 0.05 | PM man-days = 5% of total dev |
| `pct_ba` | 0.10 | BA man-days = 10% of total dev |
| `pct_qc` | 0.30 | QC man-days = 30% of total dev |
| `rate_pm` | 500 | Hourly rate (USD) for PM |
| `rate_ba` | 400 | Hourly rate for BA |
| `rate_dev` | 450 | Hourly rate for BE/FE |
| `rate_qc` | 350 | Hourly rate for QC |
| `currency_rate` | 24500 | USD → VND conversion |

**md_ba, md_qc, md_pm are auto-computed** by the Excel template via
formulas. Do NOT set them on tasks — the template applies the percentages.

## Sanity checks before handoff

Before saying "WBS ready":
1. `get_wbs_summary()` → BE + FE total looks reasonable for project size?
   - Trivial (1-2 features): 5-15 md
   - Small (3-5 features): 15-40 md
   - Medium (5-15 features): 40-150 md
   - Large (15+ features): 150+ md
2. Phase III (Testing & Deployment) exists?
3. Every business FR has at least 1 L4 task referencing it?
4. No L4 task has md_be=0 AND md_fe=0 simultaneously (validator: `TASK_ZERO_EFFORT`)?

## Critic error code → fix

| Code | Fix |
|---|---|
| `WBS_NO_TASKS` | Call `upsert_task` for at least the standard phase structure |
| `WBS_MISSING_PHASE` | Add the missing L1 phase (Setup / Development / Testing) |
| `TASK_ZERO_EFFORT` | `upsert_task` with non-zero md_be or md_fe (warning only) |
| `TRACE_ORPHAN_TASK` | Task references FR id that BRD won't have. Pick a real FR id |
| `META_MISMATCH` / `META_DRIFT` | Re-run `init_wbs()` with the correct project_code |

## Render

After validation passes, call:
```
render_wbs()              # writes <workspace>/WBS.xlsx
```
This tool needs no `output_path` — it writes to a known location.

## Common mistakes

- ❌ Setting `md_ba`, `md_qc`, `md_pm` on tasks — the template auto-computes them.
- ❌ Mixing L1/L2/L3 (structural) with L4 (leaf) effort. L1/L2/L3 must have md_be=0, md_fe=0.
- ❌ Picking FR ids not derivable from raw_features (BRD won't be able to match).
- ❌ One mega-task with 20 md — split into smaller tasks (cap at 8 md).
- ❌ Forgetting Phase III. Testing + deployment is always required.
