# Tools Inventory — Full Audit + Consolidation Plan

> **Goal:** Identify duplicates, parametrizable patterns, and shared utilities → reduce tool count from ~270 raw to ~150 consolidated.
>
> **Created:** 2026-04-26 · for design review before implementation.

---

## Executive Summary

| Metric | Count |
|--------|------:|
| **Raw tool slots** (sum across all agents) | **~285** |
| **Unique implementations needed** (after dedup) | **~155** |
| **Reduction** | **~46%** |
| Shared tools (used by ≥2 agents) | 28 |
| Agent-specific tools (used by 1 agent) | 127 |
| Parametrizable patterns (collapse N tools into 1) | 6 patterns saving ~32 tools |

### Key consolidations recommended

1. **`update_nfr_category × 4`** → 1 tool with `category` param (-3 tools)
2. **`propose_*_stack × 9`** → 1 tool with `layer` param (-8 tools)
3. **`assemble_phase_* × 10`** → 1 tool with `phase_type` param (-9 tools)
4. **`apply_*_overhead × 5`** → 1 tool with `overhead_type` param (-4 tools)
5. **`mcp_drawio_create_*_diagram × 8`** → 1 tool with `diagram_type` template (-7 tools)
6. **`add_module_*_task × 8`** → 1 tool with `task_type` enum (-7 tools)
7. **`load_*` family scattered** → 4 shared tools (load_req, load_sol, load_brd, load_wbs)

---

## 1. Total Tool Count by Module

### Per-agent raw counts (as currently designed)

| Agent | Raw tools | After consolidation |
|-------|----------:|--------------------:|
| Requirement Agent | 26 | 22 |
| Solution Proposal Agent | 51 | 33 |
| BRD Workflow | 70 | 42 |
| WBS Workflow | 98 | 60 |
| Proposal Workflow | ~40 | 28 |
| Shared utilities | — | 28 |
| **TOTAL** | **285** | **155** |

---

## 2. Agent-by-Agent Detail

### 2.1 Requirement Agent (26 raw → 22 consolidated)

| Group | Raw | Consolidated | Notes |
|-------|----:|-------------:|-------|
| File reading | 10 | 7 | `read_file(path, format)` replaces read_pdf/docx/pptx/xlsx/md/image (-4) |
| Extraction (LLM) | 7 | 7 | each is conceptually distinct, keep |
| Domain classification | 3 | 3 | keep |
| Gap analysis + HITL | 4 | 3 | merge prepare_clarifying_questions into ask_clarifying_questions |
| Validation + save | 2 | 2 | keep |

**Specific tools:**
```
read_file(path, format)             ← consolidated 6 readers
list_input_files(dir)
classify_files(file_list)
prioritize_files(classified)
consolidate_to_md(extracted_files)
extract_business_context(consolidated_md)
extract_objectives()
extract_stakeholders()
extract_raw_frs()
extract_raw_nfrs()
extract_constraints()
extract_integrations()
identify_domain()
lookup_domain_profile(domain)       ← SHARED with WBS, Solution
detect_compliance_signals(text)
check_critical_fields_present()
ask_clarifying_questions(qs[])      ← HITL (merged with prepare)
parse_clarification_response()
validate_completeness()
save_requirement_analysis()
```

### 2.2 Solution Proposal Agent (51 raw → 33 consolidated)

| Group | Raw | Consolidated | Notes |
|-------|----:|-------------:|-------|
| Foundation | 4 | 4 (3 shared) | load_requirement_analysis, load_domain_profile already shared |
| Architecture | 3 | 3 | keep |
| Tech stack | 9 | 1 | **`propose_tech_stack(layer, techs, version, why)`** with layer enum (BE/FE/DB/cache/queue/search/AI/infra) |
| Deployment | 5 | 5 | keep |
| Integration | 3 | 3 | keep |
| Security | 6 | 6 | keep |
| Modules | 4 | 3 | identify_shared_components → SHARED with WBS |
| Diagrams (MCP) | 5 | 5 | SHARED with BRD as `mcp_drawio_*` family |
| Feedback loop | 8 | 8 | keep all (each distinct intent path) |
| Approval | 4 | 4 | keep |

**Big consolidation: 9 propose_*_stack tools → 1 tool**
```python
# BEFORE: 9 separate tools
propose_be_stack(techs)
propose_fe_stack(techs)
propose_db_stack(techs)
propose_cache(techs)
propose_queue(techs)
propose_search(techs)
propose_ai_stack(techs)
propose_infra_stack(techs)
validate_against_must_use()

# AFTER: 1 parametrized tool + 1 validator
propose_tech_stack(layer: Literal["be","fe","db","cache","queue","search","ai","infra"],
                   technologies: list[str], version: str, rationale: str)
validate_against_must_use()
```

### 2.3 BRD Workflow (70 raw → 42 consolidated)

| Group | Raw | Consolidated | Notes |
|-------|----:|-------------:|-------|
| Foundation | 5 | 5 (4 shared) | load_* family shared |
| Exec & strategic | 6 | 6 | keep |
| Stakeholder | 5 | 5 | keep |
| Scope & process | 10 | 7 | drawio tools shared |
| User needs & rules | 4 | 4 | keep |
| Functional + diagrams | 9 | 7 | drawio tools shared |
| Interfaces + NFR | 14 | 7 | **update_nfr_category × 4** → 1 tool with category param (-3); **MCP drawio shared** |
| Risk & appendix | 6 | 5 | mcp_drawio_create_risk_matrix shared |
| Critic + refiner + render | 11 | 11 | keep all (each distinct check) |

**Big consolidation: NFR**
```python
# BEFORE
update_nfr_category("performance", rows)
update_nfr_category("safety", rows)
update_nfr_category("security", rows)
update_nfr_category("quality", rows)

# AFTER (already parameterized!)
update_nfr_category(category: Literal["performance","safety","security","quality"], rows: list[NFRRow])
# So actually this is ALREADY 1 tool — just listed × 4 in spec for clarity. KEEP as 1.
```

### 2.4 WBS Workflow (98 raw → 60 consolidated) — biggest reduction

| Phase | Raw | Consolidated | Reduction strategy |
|-------|----:|-------------:|---------|
| P1 Module Decomp | 5 | 5 (1 shared) | identify_shared_component shared with Solution |
| **P2 Task Breakdown** | **22** | **8** | **Big consolidation** below |
| P3 Effort Estimator | 16 | 11 | apply_*_overhead × 5 → 1 with type enum (-4) |
| **P4 Phase Planner** | **10** | **2** | **`assemble_phase(phase_type, ...)`** with enum |
| P5 Timeline | 8 | 8 | keep |
| P6 Cost | 10 | 8 | combine compute_*_cost into compute_cost(scope=) |
| P7 Validator | 10 | 10 | keep (each distinct rule) |
| P8 Template Filler | 12 | 8 | add_wbs_*_row × 4 → 1 with level param (-3); other consolidations |
| P9 Finalizer | 5 | 5 | keep |

**Big consolidation: P2 Task Breakdown (22 → 8)**
```python
# BEFORE: 22 separate tools
add_kickoff_tasks() / add_environment_setup_tasks() / add_cicd_bootstrap_tasks() / add_design_phase_tasks()
add_module_db_schema_task() / add_module_api_design_task() / add_module_be_task() / add_module_fe_task() /
add_module_ui_design_task() / add_module_integration_task() / add_module_unit_test_task() / add_module_documentation_task()
add_qa_tasks() / add_performance_test_tasks() / add_security_test_tasks() / add_devops_tasks() /
add_uat_support_tasks() / add_deployment_tasks() / add_user_documentation_tasks() / add_training_handover_tasks() /
add_hypercare_tasks() / add_ai_ml_lifecycle_tasks()

# AFTER: 8 parametric tools
add_setup_task(setup_type: Literal["kickoff","env","cicd","design"], ...)         # 4 → 1
add_module_task(module_id, task_type: Literal["db","api","be","fe","ui","integ","unit_test","doc"], ...)   # 8 → 1
add_qa_task(qa_type: Literal["plan","exec","perf","sec","regression"], ...)        # 5 → 1
add_devops_task(devops_type: Literal["monitor","log","alert","backup"], ...)       # 1 → 1
add_uat_support_task(weeks, support_md_per_week)                                    # 1 → 1
add_deployment_task(env: Literal["dev","uat","staging","prod"], cab_approval, ...)  # 1 → 1
add_documentation_task(doc_type: Literal["user_manual","training_material"], ...)  # 2 → 1
add_ai_ml_lifecycle_task(stage: Literal["collect","label","prep","train","tune","benchmark","inference"], ...)  # 1 → 1
add_training_task(sessions, hours_per_session, attendees)                           # 1 → 1
add_hypercare_task(weeks, support_md_per_week)                                      # 1 → 1
```

**Big consolidation: P4 Phase Planning (10 → 2)**
```python
# BEFORE
assemble_phase_setup() / assemble_phase_design() / assemble_phase_development() /
assemble_phase_system_testing() / assemble_phase_integration_testing() /
assemble_phase_uat() / assemble_phase_deployment() / assemble_phase_documentation() /
assemble_phase_training() / assemble_phase_hypercare()

# AFTER
PhaseType = Literal["setup", "design", "development", "system_test",
                    "integration_test", "uat", "deployment",
                    "documentation", "training", "hypercare"]
assemble_phase(phase_type: PhaseType, tasks: list[Task], ...)
finalize_all_phases()
```

**Big consolidation: P3 Effort Multipliers (5 → 1)**
```python
# BEFORE
apply_domain_multiplier()
apply_seniority_factor()
apply_integration_overhead()
apply_compliance_overhead()
apply_learning_curve_buffer()
apply_risk_buffer()

# AFTER
OverheadType = Literal["domain","seniority","integration","compliance","learning","risk"]
apply_overhead(overhead_type: OverheadType, value: float, scope: str = "all")
# Plus: finalize_task_efforts() applies all in correct order
```

### 2.5 Proposal Workflow (~40 raw → 28 consolidated)

Detail TBD when Proposal phase is implemented (Sprint 8). Estimated:
- executive_summary: 3
- solution_pitcher: 4
- case_study (RAG): 5
- pricing_agent: 6
- slide_layouter (python-pptx): 8
- exporter: 2

---

## 3. Cross-Agent Overlap Matrix

### Tools used by ≥2 agents (28 shared)

| Tool | Used by | Module |
|------|---------|--------|
| `load_requirement_analysis()` | Solution, BRD, WBS, Proposal | shared/loaders.py |
| `load_solution()` | BRD, WBS, Proposal | shared/loaders.py |
| `load_brd_state()` | WBS, Proposal | shared/loaders.py |
| `load_wbs_state()` | Proposal | shared/loaders.py |
| `lookup_domain_profile(domain)` | Requirement, Solution, WBS | shared/domain.py |
| `lookup_benchmark_effort(category, complexity)` | WBS, Proposal | shared/benchmarks.py |
| `identify_shared_components()` | Solution, WBS | shared/modules.py |
| `mcp_drawio_start_session()` | Solution, BRD | shared/mcp_drawio.py |
| `mcp_drawio_create_new_diagram(xml)` | Solution, BRD | shared/mcp_drawio.py |
| `mcp_drawio_edit_diagram(operations)` | Solution, BRD | shared/mcp_drawio.py |
| `mcp_drawio_get_diagram()` | Solution, BRD | shared/mcp_drawio.py |
| `mcp_drawio_export_diagram(path)` | Solution, BRD | shared/mcp_drawio.py |
| `read_file(path, format)` | Requirement, BRD (mockups) | shared/file_io.py |
| `read_json(filename)` | All agents | shared/workspace.py |
| `write_json(filename, data)` | All agents | shared/workspace.py |
| `read_text(filename)` | All agents | shared/workspace.py |
| `write_text(filename, content)` | All agents | shared/workspace.py |
| `get_workspace()` | All agents | shared/workspace.py |
| `set_workspace(path)` | Orchestrator | shared/workspace.py |
| `ask_user(question)` | Requirement, Solution, BRD HITL | shared/hitl.py |
| `request_approval(summary)` | Solution, WBS, BRD | shared/hitl.py |
| `detect_approval(message)` | Solution, BRD, WBS | shared/hitl.py |
| `set_output_dir(path)` | Orchestrator + all workflows | shared/folder.py |
| `get_output_paths(project, type, version)` | All exporters | shared/folder.py |
| `create_project_folder(project, output_dir)` | All exporters | shared/folder.py |
| `upload_to_s3(local_path, key)` | All exporters | shared/folder.py |
| `save_to_output_dir(workspace_file, type)` | All exporters | shared/folder.py |
| `emit_sse_event(event_name, data)` | All agents (HITL/progress) | shared/sse.py |

---

## 4. Final File Layout (after consolidation)

```
tools/
├── __init__.py                ← exports ALL_TOOLS = [...]
│
├── shared/                    ← 28 shared tools
│   ├── workspace.py           ← read/write JSON, get/set workspace (8 tools)
│   ├── loaders.py             ← load_requirement_analysis, load_solution, load_brd_state, load_wbs_state (4)
│   ├── domain.py              ← lookup_domain_profile (1)
│   ├── benchmarks.py          ← lookup_benchmark_effort (1)
│   ├── mcp_drawio.py          ← 5 MCP wrappers
│   ├── file_io.py             ← read_file (consolidated PDF/DOCX/...) (3)
│   ├── hitl.py                ← ask_user, request_approval, detect_approval, parse_clarification_response (4)
│   ├── folder.py              ← set_output_dir, get_output_paths, save_to_output_dir, upload_to_s3, create_project_folder (5)
│   └── sse.py                 ← emit_sse_event (1)
│
├── requirement_ops.py         ← 22 Requirement-specific (extraction, gap analysis)
├── solution_ops.py            ← 33 Solution-specific (architecture, tech stack, modules)
├── feedback_ops.py            ← 8 chat loop tools (intent classify, patch, snapshot, restore)
│
├── brd_ops.py                 ← 30 BRD section tools (init, set_*, upsert_fr, ...)
├── brd_diagram_ops.py         ← 8 BRD-specific drawio templates (BPMN, use case, sequence, DFD, state, risk_matrix)
│                                 (uses shared/mcp_drawio.py underneath)
├── brd_validators.py          ← 7 BRD critic + refiner
├── brd_renderer.py            ← render_brd_to_docx (subprocess)
│
├── wbs/                       ← WBS-specific (60 tools)
│   ├── module_ops.py          ← P1 (5 tools)
│   ├── task_ops.py            ← P2 consolidated (8 tools, parametric)
│   ├── effort_ops.py          ← P3 (11 tools, apply_overhead consolidated)
│   ├── phase_ops.py           ← P4 consolidated (2 tools: assemble_phase, finalize_all_phases)
│   ├── timeline_ops.py        ← P5 (8 tools)
│   ├── cost_ops.py            ← P6 (8 tools)
│   ├── validators.py          ← P7 (10 tools)
│   ├── template_filler.py     ← P8 (8 tools)
│   └── finalizer.py           ← P9 (5 tools)
│
└── proposal/                  ← Proposal-specific (28 tools)
    ├── ...
```

**Total file count:** ~22 modules
**Total tools:** ~155 (after consolidation, was 285 raw)

---

## 5. Tools to KEEP separate (no consolidation)

Tools that LOOK similar but should NOT be merged because each has distinct logic / domain knowledge:

### Validators (every check is different)
```
validate_brd                    # FR uniqueness, NFR units, completeness
validate_wbs                    # task structure, effort distribution
validate_traceability_matrix    # FR ↔ BR ↔ AC coverage 100%
validate_acceptance_criteria    # AC uses BDD format
validate_completeness           # all sections filled
validate_fr_coverage            # all FRs have ≥1 task
validate_phase_coverage         # Setup/Dev/Test/Deploy present
validate_module_completeness    # each module has API+DB+BE+FE+test+doc
validate_effort_distribution    # no task >5d
validate_qc_ratio               # 25-40% range
validate_timeline_feasibility   # vs deadline
validate_cost_vs_budget
validate_team_capacity
validate_domain_mandatory_tasks # banking → pen_test, etc.
```
13 tools — each is a different rule with different code path. **Keep all.**

### Refiner checks (each is a different invariant)
```
check_language_consistency      # no random English in VI
check_fr_numbering_continuity   # FR1, FR2, ...
check_terminology_consistency   # same term used
check_business_rule_coverage    # every BR referenced ≥1 FR
check_abbreviation_coverage     # every abbr in glossary
```
5 tools — distinct refinement rules. **Keep all.**

### Feedback loop (each intent has different code path)
```
receive_message
classify_intent                 # REFINE | QUESTION | ROLLBACK | APPROVE | RESTART
identify_change_target          # which field/diagram?
save_diff_snapshot              # before patch
apply_atomic_patch              # mutate state
re_validate                     # vs constraints
explain_decision                # for QUESTION
restore_snapshot                # for ROLLBACK
```
8 tools — each handles a distinct branch. **Keep all.**

---

## 6. Quick consolidation impact

```
BEFORE:  285 tools across 30+ files
AFTER:   155 tools across 22 files (~46% reduction)

Saved by:
  - 9 propose_*_stack    → 1   (-8)
  - 22 add_*_task        → 8   (-14)
  - 10 assemble_phase_*  → 2   (-8)
  - 6 apply_*_overhead   → 1   (-5)
  - 5 read_pdf/docx/...  → 1   (-4)
  - Various mergers       (-91)
  Total: -130 tools

Maintenance benefits:
  - Adding a new tech layer = update 1 enum, not write new tool
  - Adding a new phase type = update 1 enum
  - Tools share input validation (Pydantic models)
  - Single source of truth per family
```

---

## 7. Recommendation

**Implement with consolidated count (~155 tools)** — but document each parametric tool with full enum coverage in docstring so the agent knows what's possible.

Trade-offs:
- ✅ Less code to write/test/maintain
- ✅ Fewer tool descriptions for the LLM to scan (less context bloat)
- ✅ Adding new categories doesn't require new tool registration
- ⚠ Parametric tools have larger docstrings (LLM reads more per call)
- ⚠ Bug in 1 parametric tool affects multiple use cases (add good tests)

**Net: PROCEED with consolidation.** Implementation effort drops from ~50d to ~28d for tool layer.

---

## 8. Sprint impact

Updated effort estimate:

| Sprint | Original | After consolidation |
|--------|---------:|--------------------:|
| S0 Foundation | 3d | 3d |
| S0.5 Pre-processing | 10.5d | 8d (-2.5d) |
| S1 Configs | done | done |
| S2-S4 WBS | 14d | 9d (-5d) |
| S5 BRD | 4d | 10d (+6d, BA-enhanced) |
| S6 Orchestrator | 4d | 4d |
| S7 Test | 3d | 3d |
| S8 Proposal | 7d | 5d (-2d) |
| **Total** | **46d** | **42d** |

Slight net reduction overall — BRD got more complex but everything else shrunk.

---

## 9. Open questions

1. **Use enum or string for parametric tools?** Recommendation: **enum** (better LLM autocomplete + Pydantic validation).
2. **One docstring with all enum values, or split per value?** Recommendation: **one comprehensive docstring** with examples per enum value.
3. **Should `read_file(path, format)` auto-detect format from extension?** Recommendation: **yes**, with explicit `format` arg as override.
4. **Where do `mcp_drawio_create_*_diagram(template_type)` templates live?** Recommendation: `tools/diagram_templates/{bpmn,use_case,sequence,dfd,state,risk}.py` — each returns drawio XML.
