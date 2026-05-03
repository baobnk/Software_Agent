---
name: delivery_planning
description: Compute and write delivery gantt, per-role × per-week resource allocation, and 5-milestone deliverable schedule for BnK outsourcing projects. Use when filling sheet `3. Delivery Plan` or when the user asks for a project plan / timeline / staffing breakdown.
---

# Delivery Planning Skill

This skill teaches how to fill `3. Delivery Plan` in a BnK WBS workbook.
It assumes WBS state already exists in `workspace/wbs/_index.json`.

## Capacity rule (BnK outsourcing)

- **1 MD = 1 person × 1 working day** (8 hours).
- **20 MD per person per month** = 5 days/week × 4 weeks.
- For a project of `N` MD with deadline `T` months:
  - `team_size ≈ ceil(N / (T × 20))`, clipped to `[2, 8]`.
  - Example: 120 MD over 3 months → 120/60 = 2 → team of 2 full-time.
- A team of 1 is dangerous (no failure tolerance) — always at least 2.

## Allocation values

Use exactly these values in cells; never anything else.
| Value | Meaning |
|---|---|
| `1.0` | Full-time on the project that week |
| `0.5` | Half-time (typical for BA after kickoff, Tech Lead after architecture) |
| `0.2` | Light/sporadic (typical for Devops, BA during UAT) |

## 8 standard roles + allocation patterns

These are the rule-of-thumb patterns used by `compute_resource_allocation`. The
LLM may override them when the user requests specifics, but defaults are sane.

| Role | Allocation pattern |
|---|---|
| Project Manager | `1.0` every week, including UAT and post-launch |
| Business Analyst | `1.0` W1 (BRD writing), `0.5` W2, `0.2` during UAT |
| Technical Lead | `1.0` first 2 sprints (architecture), `0.5` after |
| Developer | `1.0` from coding-start week to Dev Done. `0` in UAT |
| AI Engineer | `0.5` W1-W2 (prototyping), `1.0` mid-coding, `0.5` UAT. Skip if non-AI project |
| Quality Controller | `0.5` W2, `1.0` from W3 to UAT end |
| Designer | `1.0` from W3 to Dev Done. Skip if backend-only |
| Devops | `0.2` W2 (env setup), `0.2` Dev Done, `0.2` UAT end |

## 5 standard outsourcing milestones

Names and deliverables match rows 30-34 of `3. Delivery Plan`. NEVER rename
these — clients expect this exact wording on contracts.

| # | Name | Default duration | Deliverable |
|---|---|---|---|
| 1 | Contract signoff | 1 day | Contract Signoff |
| 2 | Requirement Confirmation/Signoff | 1 week | BRD |
| 3 | Development Completion and UAT Initiation | `total_md / team_size / 5` weeks | System ready in UAT + Test cases / Test Report |
| 4 | Completion of UAT | 2 weeks (POC) or 4 weeks (full) | Source code + User Guide + Tech Specification |
| 5 | Completion of Post-Launch Support | 2 weeks | Post-launch support handover |

## HITL rule (NEVER skip)

Milestone dates ALWAYS require user confirmation before writing to the sheet.

```python
# 1) Compute proposed dates
compute_delivery_plan(start_date="2026-05-04", deadline_date="2026-08-04",
                      team_size=2, has_ai=True)

# 2) Pause for user review (graph interrupts)
confirm_delivery_milestones()    # → graph pauses; user adjusts dates;
                                  #   resume payload = list of confirmed milestones

# 3) Now write to the sheet
patch_workbook(xlsx_path, "write_master_planning",
               json.dumps(plan["gantt"]))
patch_workbook(xlsx_path, "write_resource_planning",
               json.dumps({"allocation": ..., "gantt": ..., "deadline_date": ...}))
patch_workbook(xlsx_path, "write_deliverable_milestones",
               json.dumps({"milestones": confirmed}))
```

## When to skip a role

- **No AI in the system** → set `has_ai=False`.
- **API-only / no UI** → set `has_designer=False`.
- **Solo POC** → user may waive Devops; cap allocation to `0.2`.

## Capacity warnings

If `compute_delivery_plan` returns a `capacity_warning`, surface it to the
user IMMEDIATELY. Common cases:

- Team too small: `Required X business days at team_size=N, but only Y available — compressing Z%`. The compression silently squeezes durations; the user should either accept, increase team_size, or extend deadline.
- Allocated capacity < project total MD: roles can't deliver the work in the allocated weeks. Increase team_size or specific role allocations.

## Reading module data

`compute_delivery_plan` reads modules + total MD from `workspace/wbs/_index.json`.
That file is populated by `upsert_task` calls. If the file is missing or has no
L1/L2 nodes, the tool returns an error; call `upsert_task` first.
