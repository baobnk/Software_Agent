# BnK DeepAgent — IMPLEMENTATION PLAN (FULL)

> Version 2.0 — incorporates: 12 real WBS file benchmarks, 24 domain rules,
> BnK Template fill tools, atomic tools (~85), HITL gates, incremental update.
> Status: **PLANNING COMPLETE — awaiting user approval before code**.

---

## Table of Contents

1. [Architecture overview](#1-architecture-overview)
2. [Pipeline — 11 phases × 85 tools](#2-pipeline)
3. [Phase 1 — Discovery (10 tools)](#phase-1-discovery)
4. [Phase 2 — Solution Architecture (8 tools)](#phase-2-solution-architecture)
5. [Phase 3 — Module Decomposition (5 tools)](#phase-3-module-decomposition)
6. [Phase 4 — Task Breakdown (22 tools)](#phase-4-task-breakdown)
7. [Phase 5 — Effort Estimation (16 tools)](#phase-5-effort-estimation)
8. [Phase 6 — Phase Planning (10 tools)](#phase-6-phase-planning)
9. [Phase 7 — Timeline (8 tools)](#phase-7-timeline)
10. [Phase 8 — Cost (10 tools)](#phase-8-cost)
11. [Phase 9 — Validation (10 tools)](#phase-9-validation)
12. [Phase 10 — Template Fill (12 tools)](#phase-10-template-fill)
13. [Phase 11 — Finalize & Export (5 tools)](#phase-11-finalize)
14. [Domain rules (24 domains)](#domain-rules)
15. [Effort benchmarks (from 12 real BnK WBS)](#effort-benchmarks)
16. [State files](#state-files)
17. [Agents map (10 specialists)](#agents-map)
18. [Implementation order](#implementation-order)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                ORCHESTRATOR (DeepAgent + CompositeBackend)          │
│  /input/   → ATTACHMENTS_DIR     /output/  → OUTPUT_DIR (user ctrl) │
│  /         → WORKSPACE_BASE      /AGENTS.md = persistent memory     │
└──┬─────────┬─────────┬──────────┬──────────┬──────────┬─────────────┘
   ▼         ▼         ▼          ▼          ▼          ▼
┌────────┬────────┬─────────┬──────────┬─────────┬─────────────┐
│Discovery│Analyst│Solution │ Effort  │ Timeline│Template Fill│
│   +    │  +    │Architect│Estimator│ Planner │     +       │
│Intake  │WebRAG │   +     │   +     │   +     │  Validator  │
│  +     │       │ Module  │ Phase   │  Cost   │     +       │
│Critic  │       │ Decomp  │ Planner │  Calc   │  Exporter   │
└────────┴────────┴─────────┴─────────┴─────────┴─────────────┘
```

**85 atomic tools** organized into **11 phases** executed by **10 specialist agents**.

---

## 2. Pipeline

```
START ──▶ [P1] Discovery (10 tools, HITL Q&A)
           ↓
        [P2] Solution Architecture (8 tools)
           ↓
        [P3] Module Decomposition (5 tools)
           ↓
        [P4] Task Breakdown (22 tools)  ◀── domain rules inject mandatory tasks
           ↓
        [P5] Effort Estimation (16 tools)  ◀── multipliers + benchmarks
           ↓
        [P6] Phase Planning (10 tools)
           ↓
        [P7] Timeline + Sprint (8 tools)
           ↓
        [P8] Cost Calculation (10 tools)
           ↓
        [P9] Validation (10 tools) ── FAIL ─▶ back to relevant phase (max 3 retries)
           ↓ PASS
        [P10] Template Fill (12 tools) ◀── fills BnK Template - WBS.xlsx
           ↓
        [HITL gate: user reviews summary]
           ↓
        [P11] Finalize & Export (5 tools)
           ↓
        END (.xlsx in OUTPUT_DIR/{project}/WBS/)
```

---

## Phase 1 — Discovery

**Agent:** `discovery_agent` — runs HITL Q&A, fills `project_context.json`.

| # | Tool | Args | Saves |
|---|------|------|-------|
| 1.1 | `set_client_industry` | industry, sub_industry, country, client_name, client_size | `industry` block |
| 1.2 | `set_client_domain_profile` | domain_key (lookup → 24 profiles) | `domain_profile` block |
| 1.3 | `set_budget_constraint` | type (fixed/T&M/flexible), amount_usd, amount_vnd, notes | `budget` block |
| 1.4 | `set_required_tech_stack` | must_use[], must_not_use[], preferred[] | `tech_constraints` block |
| 1.5 | `set_existing_systems` | systems[{name, type, integration_protocol, data_volume}] | `existing_systems` |
| 1.6 | `set_deployment_target` | env (cloud/on_prem/hybrid), provider, region, ha_strategy | `deployment` block |
| 1.7 | `set_compliance_requirements` | standards[] (PCI-DSS, ISO27001, HIPAA, PDPA, SOC2…) | `compliance` block |
| 1.8 | `set_team_composition` | be, fe, fs, qc, ba, pm, ai_ml, devops, designer, architect | `team` block |
| 1.9 | `set_delivery_constraints` | start_date, target_date, hard_deadline, milestones[] | `timeline_constraints` |
| 1.10 | `set_project_priorities` | top_priority (cost/time/quality/scope) + tradeoffs | `priorities` |

**HITL questions** the agent asks user (in `discovery_agent` prompt):
1. Khách hàng thuộc ngành gì? Quốc gia?
2. Budget? (fixed/flexible/T&M)
3. Tech stack constraints? (phải dùng X, không được dùng Y)
4. Hệ thống nào cần integrate?
5. Deploy ở đâu? (cloud/on-prem/hybrid)
6. Compliance? (PCI-DSS, HIPAA, PDPA, ...)
7. Team composition? (số người mỗi role)
8. Start date + hard deadline?
9. Priority: time vs cost vs quality vs scope?
10. Risk tolerance? (low/medium/high)

---

## Phase 2 — Solution Architecture

**Agent:** `solution_architect_agent` — propose technical solution BEFORE module decomposition.

| # | Tool | Args |
|---|------|------|
| 2.1 | `propose_architecture_type` | type, rationale, alternatives_considered[] |
| 2.2 | `propose_tech_stack_layer` | layer (BE/FE/DB/cache/queue/search/ai/infra), technologies[], version, rationale |
| 2.3 | `propose_infrastructure` | component, technology, sizing, ha_strategy, dr_strategy |
| 2.4 | `propose_security_architecture` | auth_method, encryption_at_rest, encryption_in_transit, secrets_mgmt, audit |
| 2.5 | `define_integration_pattern` | system_name, pattern (gateway/esb/p2p/event), protocol, complexity |
| 2.6 | `define_data_architecture` | strategy, schema_summary, retention_policy, backup_strategy |
| 2.7 | `add_architecture_diagram_ref` | name, type (context/sequence/deployment/component), file_path |
| 2.8 | `validate_solution_against_constraints` | (auto-checks vs P1 constraints) |

**Output:** `solution.json`

---

## Phase 3 — Module Decomposition

**Agent:** `module_decomposer_agent` — chia hệ thống thành modules.

| # | Tool | Args |
|---|------|------|
| 3.1 | `define_module` | module_id, name, type (feature/shared/infra/cross_cutting), description, owner |
| 3.2 | `link_fr_to_module` | fr_id, module_id, role (primary/contributor/consumer) |
| 3.3 | `define_module_dependency` | module_id, depends_on[], dep_type (hard/soft/optional) |
| 3.4 | `identify_shared_component` | component_id, name, used_by_modules[] |
| 3.5 | `set_module_complexity` | module_id, score (1-5), factors[] |

**Output:** `modules.json`

---

## Phase 4 — Task Breakdown

**Agent:** `task_breakdown_agent` — liệt kê tasks cho mỗi module + domain mandatory tasks.

### 4A. Setup Phase (4 tools, 1 lần / project)

| # | Tool | Mặc định effort |
|---|------|----------------|
| 4.1 | `add_kickoff_tasks` | charter, RACI, communication plan = ~3 MD BA |
| 4.2 | `add_environment_setup_tasks` | repo, IDE, branch strategy = ~2 MD BE |
| 4.3 | `add_cicd_bootstrap_tasks` | pipeline, registry = ~5 MD BE/DevOps |
| 4.4 | `add_design_phase_tasks` | HLD ~5-22d, DLD ~3-15d, API spec ~3-8d, UI/UX ~3-33d |

### 4B. Per-module tasks (8 tools)

| # | Tool | Effort defaults (median from BnK history) |
|---|------|------------------------------------------|
| 4.5 | `add_module_db_schema_task` | 1.1-13.2 MD (med 5.5) |
| 4.6 | `add_module_api_design_task` | 3 MD typical |
| 4.7 | `add_module_be_task` | 0.5-15 MD per task |
| 4.8 | `add_module_fe_task` | 0.5-25 MD per task (CRUD list ~16, form ~24) |
| 4.9 | `add_module_ui_design_task` | 3-10 MD per module |
| 4.10 | `add_module_integration_task` | 8-15 MD per integration |
| 4.11 | `add_module_unit_test_task` | embedded in dev (15-20% of dev) |
| 4.12 | `add_module_documentation_task` | 1-3 MD |

### 4C. Cross-cutting tasks (10 tools)

| # | Tool | Effort defaults |
|---|------|----------------|
| 4.13 | `add_qa_tasks` | test_plan ~3, system_test 7-105 (depends size) |
| 4.14 | `add_performance_test_tasks` | load+stress+endurance = 3-10 MD |
| 4.15 | `add_security_test_tasks` | SAST + DAST + pen_test = 3-10 MD (banking +5) |
| 4.16 | `add_devops_tasks` | monitoring + logging + alerting + backup = 5-15 MD |
| 4.17 | `add_uat_support_tasks` | UAT 1-4 weeks × 5-10 MD/week |
| 4.18 | `add_deployment_tasks` | per env: 1-3 MD; CAB approval +2 MD; rollback plan +1 MD |
| 4.19 | `add_user_documentation_tasks` | user manual ~3, training material ~2 |
| 4.20 | `add_training_handover_tasks` | 1-2 MD per session |
| 4.21 | `add_hypercare_tasks` | ~10% of total dev (median) |
| 4.22 | `add_ai_ml_lifecycle_tasks` | data collect 10 + label 11 + prep 17 + train 19 + tune 10 + benchmark 3 + inference 7 = ~80 MD/model |

**Auto-injection from domain profile:** `add_*` tools tự động inject mandatory tasks dựa trên P1 industry. Ví dụ banking → tự động add `pen_test`, `cab_approval`, `compliance_doc` tasks.

**Output:** `wbs_tasks.json` (raw, no effort yet)

---

## Phase 5 — Effort Estimation

**Agent:** `effort_estimator_agent` — apply multipliers, write effort back to tasks.

| # | Tool | Args |
|---|------|------|
| 5.1 | `set_task_baseline_effort` | task_id, base_md_be, base_md_fe, base_md_ai, role |
| 5.2 | `score_task_complexity` | task_id, score (1-5), factors[] |
| 5.3 | `lookup_benchmark_effort` | task_category, complexity → returns median MD from BnK history |
| 5.4 | `mark_task_dependencies` | task_id, blocking_tasks[], dep_type |
| 5.5 | `apply_domain_multiplier` | (auto from `domain_profile`) |
| 5.6 | `apply_seniority_factor` | junior 1.30 / mid 1.00 / senior 0.80 / mixed 1.10 |
| 5.7 | `apply_integration_overhead` | each external integration +0.3-1 MD |
| 5.8 | `apply_compliance_overhead` | PCI-DSS +5d, HIPAA +4d, ISO27001 +3d |
| 5.9 | `apply_learning_curve_buffer` | new_tech_list[] → +1-3 MD per new tech |
| 5.10 | `apply_risk_buffer` | category, pct (10-30%) |
| 5.11 | `compute_qc_effort` | by domain (insurance 40%, AI 30%, std 25%) |
| 5.12 | `compute_ba_effort` | by domain (insurance 20%, AI 15%, std 10%) |
| 5.13 | `compute_pm_effort` | 5-10% of (dev + ba + qc) |
| 5.14 | `compute_devops_effort` | env_count × 5 + ha_complexity bonus |
| 5.15 | `compute_security_extra_effort` | compliance[] → extra MD |
| 5.16 | `finalize_task_efforts` | apply all multipliers, write back |

**Output:** `wbs_tasks.json` (with adjusted effort)

---

## Phase 6 — Phase Planning

**Agent:** `phase_planner_agent` — group tasks into BnK 3-phase template (or custom).

| # | Tool | BnK template phase |
|---|------|-------------------|
| 6.1 | `assemble_phase_setup` | Phase I: Setup & Installation |
| 6.2 | `assemble_phase_design` | Phase I.B: Design (HLD, DLD) |
| 6.3 | `assemble_phase_development` | Phase II: Development (per module) |
| 6.4 | `assemble_phase_system_testing` | Phase III.A.1 |
| 6.5 | `assemble_phase_integration_testing` | Phase III.A.2 |
| 6.6 | `assemble_phase_uat` | Phase III.A.3 (banking 4w, std 1-2w) |
| 6.7 | `assemble_phase_deployment` | Phase III.B (DEV/UAT/PROD; CAB if banking) |
| 6.8 | `assemble_phase_documentation` | cross-cutting |
| 6.9 | `assemble_phase_training` | optional, enterprise mandatory |
| 6.10 | `assemble_phase_hypercare` | post go-live (default 1-3 months) |

**Standard phase distribution (from BnK history):**
- Setup: ~8% of total
- Development: ~80% of total
- Testing/Deploy: ~12% of total

**Output:** `wbs_phases.json`

---

## Phase 7 — Timeline

**Agent:** `timeline_planner_agent` — sprint plan + milestones + calendar.

| # | Tool | Args |
|---|------|------|
| 7.1 | `set_sprint_config` | length_weeks (default 2), capacity_per_dev_per_sprint (default 8.5 MD) |
| 7.2 | `assign_task_to_sprint` | task_id, sprint_number |
| 7.3 | `compute_sprint_capacity_check` | (auto-validate no sprint over-allocated) |
| 7.4 | `define_milestone` | name, date, deliverables[], gate_criteria |
| 7.5 | `compute_critical_path` | (Hamilton-style dependency walk) |
| 7.6 | `compute_calendar_timeline` | start_date → working days, account holidays |
| 7.7 | `validate_timeline_vs_deadline` | target_date check |
| 7.8 | `generate_resource_allocation_plan` | (per role per sprint, fills "3. Delivery Plan" sheet) |

**Standard milestones:** Kickoff → BRD signed → Dev start → MVP → UAT entry → UAT exit → Go-live → Hypercare end

**Output:** `timeline.json`

---

## Phase 8 — Cost

**Agent:** `cost_calculator_agent`

| # | Tool | Args |
|---|------|------|
| 8.1 | `set_role_rates` | rates_dict, currency (USD/VND) |
| 8.2 | `compute_module_cost` | per module |
| 8.3 | `compute_phase_cost` | per phase |
| 8.4 | `compute_role_breakdown_cost` | per role |
| 8.5 | `compute_total_cost` | grand total |
| 8.6 | `apply_currency_conversion` | rate (default 24500 VND/USD) |
| 8.7 | `apply_margin` | margin_pct, type (gross/net) |
| 8.8 | `add_optional_service` | name, effort_md, cost (training, support, maintenance) |
| 8.9 | `add_post_golive_support` | months, support_pct (default 1%/month of total) |
| 8.10 | `compute_proposal_pricing` | for proposal generation |

**Default rates (BnK standard):** PM 500, BA 400, Dev 450, QC 350 USD/MD; conversion 24,500 VND/USD.

**Output:** `cost.json`

---

## Phase 9 — Validation

**Agent:** `wbs_validator_agent` — deterministic Python checks (no LLM judgment).

| # | Tool | Code | Severity |
|---|------|------|----------|
| 9.1 | `validate_fr_coverage` | TRACE_UNCOVERED_FR | error |
| 9.2 | `validate_phase_coverage` | WBS_MISSING_PHASE | error |
| 9.3 | `validate_module_completeness` | MODULE_INCOMPLETE | warning |
| 9.4 | `validate_effort_distribution` | TASK_TOO_BIG (>5d), TASK_TOO_SMALL (<0.25d) | warning |
| 9.5 | `validate_qc_ratio` | QC_OUT_OF_RANGE | warning |
| 9.6 | `validate_timeline_feasibility` | TIMELINE_INFEASIBLE | error |
| 9.7 | `validate_cost_vs_budget` | COST_OVER_BUDGET | warning |
| 9.8 | `validate_team_capacity` | CAPACITY_OVERLOAD | error |
| 9.9 | `validate_domain_mandatory_tasks` | DOMAIN_TASK_MISSING | error (banking → must have pen_test, etc.) |
| 9.10 | `generate_validation_report` | full JSON + human-readable |

**Output:** `validation_report.json`

---

## Phase 10 — Template Fill

**Agent:** `template_filler_agent` — fills BnK Template - WBS.xlsx using openpyxl. **Critical: preserves all formulas, VLOOKUP, formatting.**

Template path: `/mnt/f/code/agent/WBS_Agent/WBS/[BnK] Template - WBS.xlsx`

| # | Tool | Sheet | Action |
|---|------|-------|--------|
| 10.1 | `load_wbs_template` | (all) | copies template → workspace, opens with openpyxl |
| 10.2 | `set_wbs_project_metadata` | "2. WBS" | row 1: Project Code = `D2` cell; row 2: WBS title |
| 10.3 | `clear_template_placeholder_rows` | "2. WBS" | clears rows 5-76 example data (keeps header + formulas) |
| 10.4 | `add_wbs_phase_l1_row` | "2. WBS" | inserts row "I", "II", "III" with feature name |
| 10.5 | `add_wbs_subphase_l2_row` | "2. WBS" | inserts "I.A", "II.B", auto-formula for sub-totals |
| 10.6 | `add_wbs_module_l3_row` | "2. WBS" | inserts L3 module |
| 10.7 | `add_wbs_task_l4_row` | "2. WBS" | inserts leaf with be_md, fe_md, description, remark; ref_code auto via CONCATENATE formula |
| 10.8 | `set_master_data` | "4. Master Data" | PM/BA/Dev/QC percentages + rates |
| 10.9 | `fill_delivery_plan_modules` | "3. Delivery Plan" | start_date, end_date, sprint allocation per module |
| 10.10 | `fill_delivery_plan_resources` | "3. Delivery Plan" | resource allocation per role per sprint (PM, TL, Dev, BA, QC, Designer, DevOps) |
| 10.11 | `fill_effort_summary_sheet` | "1. Effort" | (formulas auto-recalculate, just verify) |
| 10.12 | `verify_template_integrity` | (all) | check no formula broken, all VLOOKUP refs valid |

**Key implementation detail:** Excel formulas like `=VLOOKUP($B6,'2. WBS'!$B$5:$L$76,2,...)` and `=CONCATENATE($D$2&"-",B9)` MUST be preserved. Use `openpyxl.load_workbook(keep_vba=True, data_only=False)` and never overwrite formula cells; only fill data cells (B, C, D, F, G column for L4 rows; B, C for L1-L3).

**Output:** `wbs_filled.xlsx` (workspace)

---

## Phase 11 — Finalize

**Agent:** `wbs_finalizer_agent`

| # | Tool | Action |
|---|------|--------|
| 11.1 | `generate_wbs_summary_report` | human-readable summary (effort, cost, timeline) |
| 11.2 | `request_user_approval` | HITL gate — show summary, ask user to confirm |
| 11.3 | `apply_user_revisions` | atomic patches (no full regeneration) |
| 11.4 | `save_wbs_to_output` | save filled .xlsx to `OUTPUT_DIR/{project}/WBS/` |
| 11.5 | `upload_to_s3_optional` | if `ENABLE_S3_UPLOAD=true` |

---

## Domain Rules

**24 domains** with full multipliers, mandatory tasks, deployment defaults.

| # | Domain | BE × | QC % | BA % | UAT wks | Buffer % | Deploy days | Mandatory tasks |
|---|--------|------|------|------|---------|----------|-------------|-----------------|
| 1 | **banking** | 1.30 | 40% | 20% | 4 | 20 | 5 | pen_test, cab_approval, compliance_doc, dr_test, audit_trail, sast, dast |
| 2 | **fintech** | 1.20 | 35% | 15% | 3 | 18 | 3 | pen_test, kyc_compliance, audit_trail, sast |
| 3 | **insurance** | 1.25 | 40% | 20% | 3 | 18 | 4 | regulatory_audit, audit_trail, business_rule_validation, doc_generation |
| 4 | **healthcare** | 1.20 | 35% | 18% | 3 | 18 | 3 | hipaa_audit, data_privacy_review, audit_trail, anonymization |
| 5 | **government** | 1.15 | 35% | 25% | 4 | 25 | 5 | security_clearance_review, srs_signoff, uat_report, training_doc, vapt |
| 6 | **defense / military** | 1.40 | 45% | 25% | 6 | 30 | 7 | air_gapped_test, security_clearance, supply_chain_audit, classified_review |
| 7 | **ecommerce** | 1.10 | 28% | 12% | 2 | 12 | 2 | payment_security_audit, load_test, accessibility_audit |
| 8 | **retail / pos** | 1.10 | 28% | 13% | 2 | 12 | 3 | offline_mode_test, pos_certification, payment_audit |
| 9 | **logistics / supply chain** | 1.15 | 30% | 14% | 2 | 15 | 2 | realtime_test, gps_integration_test, multi_carrier_audit |
| 10 | **transportation / mobility** | 1.20 | 32% | 14% | 2 | 18 | 3 | safety_audit, gps_certification, latency_test, geo_compliance |
| 11 | **telecom / 5G** | 1.30 | 38% | 18% | 4 | 20 | 5 | tmf_compliance, ha_failover_test, nfv_compliance, oss_bss_audit |
| 12 | **manufacturing / iot** | 1.20 | 32% | 14% | 3 | 18 | 4 | edge_calibration, ot_security, sensor_fmea, plc_integration |
| 13 | **energy / oil&gas** | 1.30 | 38% | 18% | 4 | 22 | 5 | scada_security, asset_audit, hazop, hse_review, opc_ua_test |
| 14 | **agriculture / agritech** | 1.10 | 28% | 14% | 2 | 14 | 2 | sensor_field_test, weather_data_validation, offline_sync |
| 15 | **education / edtech** | 1.10 | 28% | 13% | 2 | 12 | 2 | accessibility_audit (WCAG), parental_consent, content_review |
| 16 | **media / streaming** | 1.15 | 30% | 12% | 2 | 14 | 2 | drm_audit, cdn_test, encoding_test, copyright_check |
| 17 | **gaming** | 1.15 | 35% | 10% | 2 | 18 | 2 | latency_test, multiplayer_load_test, anti_cheat_audit |
| 18 | **F&B / hospitality** | 1.10 | 28% | 12% | 2 | 12 | 2 | offline_pos_test, payment_audit, multi_outlet_test |
| 19 | **real estate / proptech** | 1.10 | 28% | 13% | 2 | 12 | 2 | listing_data_validation, geo_compliance, escrow_audit |
| 20 | **legal tech** | 1.15 | 30% | 18% | 3 | 16 | 3 | legal_review, contract_audit, doc_anonymization, data_retention |
| 21 | **HR tech / payroll** | 1.15 | 30% | 16% | 3 | 16 | 3 | payroll_audit, tax_compliance, gdpr_audit |
| 22 | **AI/ML platform** | 1.10 | 30% | 15% | 2 | 20 | 3 | model_validation, data_lineage, mlops_pipeline_test, drift_monitoring |
| 23 | **blockchain / web3** | 1.30 | 40% | 18% | 4 | 25 | 5 | smart_contract_audit, formal_verification, gas_optimization, key_mgmt |
| 24 | **NGO / non-profit** | 1.0 | 25% | 12% | 2 | 10 | 1 | donor_audit, low_budget_optimization |
| 25 | **research / academia** | 1.0 | 20% | 10% | 1 | 10 | 1 | open_data_compliance, reproducibility |
| 26 | **standard / SaaS** | 1.0 | 25% | 12% | 2 | 10 | 1 | (baseline) |

### Domain rule structure (every domain has)

```yaml
banking:
  multipliers:
    be_multiplier: 1.30
    fe_multiplier: 1.05
    ai_multiplier: 1.20
  ratios:
    qc_pct: 0.40
    ba_pct: 0.20
    pm_pct: 0.10
  durations:
    uat_weeks: 4
    deploy_days_per_env: 5
    hypercare_weeks: 12
  buffers:
    base_buffer_pct: 20
    integration_overhead_md: 1.0       # per integration
  mandatory_tasks:
    - {id: pen_test,         category: security,   md: 5,  role: be}
    - {id: cab_approval,     category: deploy,     md: 2,  role: pm}
    - {id: compliance_doc,   category: doc,        md: 3,  role: ba}
    - {id: dr_test,          category: deploy,     md: 3,  role: be}
    - {id: audit_trail,      category: feature,    md: 5,  role: be}
    - {id: sast,             category: security,   md: 2,  role: be}
    - {id: dast,             category: security,   md: 2,  role: be}
  default_deployment_env: on_premise
  default_compliance: [PCI-DSS, ISO 27001]
  default_archs_recommended:
    - microservices
    - modular_monolith
  default_archs_avoided:
    - serverless                       # too opaque for audit
  notes: "On-prem likely. CAB approval gates each deploy. Multi-round UAT."
```

---

## Effort Benchmarks

**Source:** 12 real BnK WBS files (>650 leaf tasks). Use **median**, not avg.

### Quick lookup (default if exact category not found)

| Task category | Median MD | Range |
|---------------|-----------|-------|
| Database/Schema design | 5.5 | 1.1–13.2 |
| HLD / System architecture | 7.7 | 0.7–22 |
| API design | 3 | 1–8 |
| UI/UX design (per module) | 3.3 | 3.3–33 |
| Code base setup | 2.2 | 1–11 |
| CRUD list/view page | 15.8 | 3.1–24.6 |
| CRUD form/upload | 24.6 | 12.3–24.6 |
| Search/filter | 17.6 | 5.3–21.1 |
| Auth/login (FE) | 1.5 | 0.5–5 |
| Role/permission UI | 12.3 | 1.8–17.6 |
| Audit log | 12.3 | 2.8–24.6 |
| Workflow/business rules | 4.0 | 3.1–26.4 |
| Notification/email/SMS | 8.8 | 1.4–14.1 |
| Renewal/SLA flow | 17.6 | 12.3–24.6 |
| Report/dashboard | 12.3 | 0.8–24.6 |
| Export PDF/Excel | 3.5 | 3–4 |
| 3rd party integration | 13.2 | 1.5–52.8 |
| AI — data collect/label | 11.0 | 3.5–16 |
| AI — data prep | 17.0 | 2–17 |
| AI — train model | 19.0 | 6.3–88 |
| AI — inference API | 6.6 | 1.3–118 |
| AI — benchmark | 3.3 | 1.9–3.7 |
| LLM tuning | 10 | 5–45 |
| OCR training | 20 | – |
| SIT (small project) | 7.7 | 2.9–8 |
| SIT (large insurance) | 105 | 60–158 |
| UAT support | 6.3 | 5–10 (per cycle) |
| Bug fix bucket | 10 | 5–158 |
| Deployment per env | 6.6 | 1–79 |
| Production deploy | 2 | 2–5 |
| Hypercare | 11 | 1.7–53 |
| Documentation | 3 | 3 |
| Training (1 cohort) | 4.2 | 2–4.2 |
| Edge/IoT calibration | 5.5 | 2.2–6.6 |

### AI lifecycle bundle

For 1 ML model: data collect (10) + label (11) + prep (17) + train (19) + tuning (10) + benchmark (3) + inference (7) + integration (10) = **~87 MD per model**.

### Project size envelope (for sanity check)

- **Lending baseline:** ~130 MD
- **AI/CV solution per feature:** 200–350 MD
- **IoT mid-size:** 150–200 MD
- **Insurance system:** 1500–2600 MD
- **AI platform internal:** 3000+ MD

### Phase distribution (use as default split)

- Setup: 8%
- Development: 80%
- Testing/Deploy: 12%

---

## State Files

```
workspace/{session_id}/
├── project_context.json        # P1 — discovery output
├── solution.json               # P2 — architecture proposal
├── modules.json                # P3 — module decomposition
├── wbs_tasks.json              # P4-P5 — tasks with effort
├── wbs_phases.json             # P6 — phase grouping
├── timeline.json               # P7 — sprint + milestones
├── cost.json                   # P8 — cost breakdown
├── validation_report.json      # P9 — validation issues
├── wbs_filled.xlsx             # P10 — filled BnK template
└── effort_model.json           # global multipliers active for session
```

---

## Agents Map

| Agent | Phase(s) | Tools count | Model recommendation |
|-------|---------|-------------|---------------------|
| `discovery_agent` | P1 | 10 | claude-sonnet-4-6 (HITL Q&A needs nuance) |
| `intake_agent` | (input parse) | 8 | gpt-5.4-mini |
| `analyst_agent` | (deep analysis) | 8 | claude-sonnet-4-6 |
| `solution_architect_agent` | P2 | 8 | claude-sonnet-4-6 (architecture decisions) |
| `module_decomposer_agent` | P3 | 5 | gpt-5.4-mini |
| `task_breakdown_agent` | P4 | 22 | gpt-5.4-mini |
| `effort_estimator_agent` | P5 | 16 | gpt-5.4-mini (deterministic) |
| `phase_planner_agent` | P6 | 10 | gpt-5.4-mini |
| `timeline_planner_agent` | P7 | 8 | gpt-5.4-mini |
| `cost_calculator_agent` | P8 | 10 | gpt-5.4-mini |
| `wbs_validator_agent` | P9 | 10 | gpt-5.4-mini (deterministic checks) |
| `template_filler_agent` | P10 | 12 | gpt-5.4-mini |
| `wbs_finalizer_agent` | P11 | 5 | gpt-5.4-mini |

**Total:** 13 specialist agents (some reused for BRD as well).

---

## Implementation Order

| Sprint | Goal | Files |
|--------|------|-------|
| **S1** | Domain rules YAML + benchmark JSON | `config/domain_rules.yaml`, `config/effort_benchmarks.json` |
| **S2** | Phase 1 tools + discovery agent | `tools/discovery_ops.py`, `agents/discovery.py` |
| **S3** | Phase 2-3 tools + agents | `tools/solution_ops.py`, `tools/module_ops.py`, `agents/solution_architect.py`, `agents/module_decomposer.py` |
| **S4** | Phase 4 tools (22 tools) + task_breakdown agent | `tools/task_ops.py`, `agents/task_breakdown.py` |
| **S5** | Phase 5 tools (16 tools) + effort_estimator agent | `tools/effort_ops.py`, `agents/effort_estimator.py` |
| **S6** | Phase 6-7 + agents | `tools/phase_ops.py`, `tools/timeline_ops.py`, agents |
| **S7** | Phase 8-9 + agents | `tools/cost_ops.py`, `tools/wbs_validators.py`, agents |
| **S8** | Phase 10 — Template Fill (CRITICAL) | `tools/template_filler.py`, `agents/template_filler.py` |
| **S9** | Phase 11 + orchestrator integration | `tools/finalize_ops.py`, update `orchestrator.py` |
| **S10** | E2E test on GEHP, MBAL fixtures | `tests/test_e2e_*.py` |

Each sprint = 1 commit. After S5 we have a working WBS for simple projects; S8 is when banking-grade output is ready.

---

## Critical Implementation Rules

1. **Tool atomicity:** Every tool does ONE thing. No tool both creates and modifies state of multiple entities.
2. **Idempotent updates:** Calling a tool twice with same args = same result (no duplicates).
3. **Section IDs everywhere:** Every entity has a stable UUID for incremental patches.
4. **Pydantic at every boundary:** Tools validate args + return values via Pydantic schemas.
5. **Template formulas preserved:** When filling Excel, NEVER overwrite formula cells.
6. **Domain rules from YAML:** Hardcoded `DOMAIN_PROFILES` in Python is for fallback only; primary source is `config/domain_rules.yaml` so non-developers can edit.
7. **Benchmarks queryable:** `lookup_benchmark_effort(category, complexity)` is the agent's primary effort source — not LLM imagination.
8. **HITL gates:** P1 (after discovery) + P10 (before file save) are the two interrupt points.
9. **Incremental update:** User says "đổi effort task X thành 3d" → agent calls `set_task_baseline_effort(X, 3)` + `finalize_task_efforts()` only. No regeneration.
10. **Folder control:** `OUTPUT_DIR` env + `set_output_dir` tool + API `POST /sessions/{id}/output-dir` — three layers.

---

## What's NOT in this plan (deferred)

- **Proposal generation** (PowerPoint with diagrams) — Phase 12, deferred per user request
- **Real-time collaboration** (multi-user editing) — out of scope
- **Auto-refresh from changing requirements** (CDC) — manual refresh OK
- **Vector store for RAG** — Phase 1.5 (between S2 and S3): build FAISS index over `BRD/`, `WBS/`, `Proposal/` folders for similar-project lookup
- **WebSearch via Tavily** — included in `analyst_agent` tools, requires `TAVILY_API_KEY`

---

**End of plan. User approval required before code.**
