# BnK DeepAgent — Master Reference Document

> **Single source of truth** for the BnK DeepAgent project — consolidates all design decisions, agents, tools, state schemas, domain rules, benchmarks, implementation plans, and patterns adopted.
>
> **Version:** v3 (2026-04-26)
> **Status:** Planning complete — awaiting user approval before code
> **Path:** `/mnt/f/code/agent/WBS_Agent/bnk-deepagent/`

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture (6-page drawio)](#2-architecture-6-page-drawio)
3. [End-to-End Pipeline](#3-end-to-end-pipeline)
4. [Agents Detail (5 specialists)](#4-agents-detail-5-specialists)
5. [Tools Catalog (~205 tools)](#5-tools-catalog-205-tools)
6. [State Schemas (inheritance chain)](#6-state-schemas-inheritance-chain)
7. [Domain Rules (26 industries)](#7-domain-rules-26-industries)
8. [Effort Benchmarks (from real BnK WBS)](#8-effort-benchmarks-from-real-bnk-wbs)
9. [BnK WBS Template Fill (Phase 10)](#9-bnk-wbs-template-fill-phase-10)
10. [Chat Feedback Loop + MCP Drawio](#10-chat-feedback-loop--mcp-drawio)
11. [Implementation Plan (sprint roadmap)](#11-implementation-plan-sprint-roadmap)
12. [API Contracts](#12-api-contracts)
13. [Folder Control (3 layers)](#13-folder-control-3-layers)
14. [Production Patterns Adopted](#14-production-patterns-adopted)
15. [File Structure / Project Layout](#15-file-structure--project-layout)
16. [Open Design Decisions](#16-open-design-decisions)
17. [Quick Start](#17-quick-start)
18. [Related Files Index](#18-related-files-index)

---

## 1. Project Overview

**Goal:** Multi-agent system that transforms customer requirement files (PDF, DOCX, MD, PPTX, XLSX, images) into:
- **BRD** (.docx) — Business Requirements Document conforming to BnK Template v1.0
- **WBS** (.xlsx) — Work Breakdown Structure filled into BnK Template - WBS.xlsx (preserves formulas)
- **Proposal** (.pptx) — Sales proposal with reused architecture diagrams (Phase 2 deliverable)

**Framework:** LangChain DeepAgents (`pip install deepagents`)
**Models:** anthropic:claude-sonnet-4-6 (drafting), openai:gpt-5.4-mini (extraction/validation)
**Owner:** BnK Solution (Vietnam-based AI consulting firm)

### Two parallel implementations
- `bnk-agent/` — LangGraph supervisor pattern (older, working baseline)
- `bnk-deepagent/` — LangChain DeepAgents pattern (this project)

### Inputs (existing)
- `/mnt/f/code/agent/WBS_Agent/REQUIREMENT/` — customer requirement files
- `/mnt/f/code/agent/WBS_Agent/BRD/` — 5 sample BRDs
- `/mnt/f/code/agent/WBS_Agent/WBS/` — 18 sample WBS files (12 analyzed for benchmarks)
- `/mnt/f/code/agent/WBS_Agent/Proposal/` — sample proposals
- `/mnt/f/code/agent/WBS_Agent/bnk-agent/packages/wbs_agent_kit/` — Pydantic AST + renderers (REUSED)

### Outputs (user-controlled folder)
```
OUTPUT_DIR/{project_name}/
├── BRD/{name}_BRD_v0_1_0.docx
├── WBS/{name}_WBS_v0_1_0.xlsx
├── Proposal/{name}_Proposal_v0_1_0.pptx
└── diagrams/*.drawio + *.png + *.svg
```

---

## 2. Architecture (7-page drawio)

**File:** [architecture.drawio](architecture.drawio)
**Open with:** https://app.diagrams.net/ · VS Code drawio extension · drawio desktop

| Page | Content |
|------|---------|
| 1 | System Architecture (8 layers, end-to-end) |
| 2 | WBS Pipeline (9 phases horizontal flow) |
| 3 | State & Data Flow (inheritance + workspace + folder structure) |
| 4 | Pre-processing Flow overview (Requirement + Solution + chat loop) |
| 5 | Requirement Agent Flow detail (7 sub-phases × 22 tools) |
| 6 | Solution Agent Flow detail (11 sub-phases × 35 tools, chat loop branches) |
| 7 | BRD Workflow Flow detail (9 phases × 70 tools, BA-enhanced + MCP drawio diagrams) |

### 8 layers in System Architecture

```
① CLIENTS              CLI · Web UI · REST · LangGraph Studio · Langfuse · Schedulers
② API GATEWAY          FastAPI 8 endpoints (sessions, files, analyze, chat, run, approve, ...)
③ ORCHESTRATION        Session Mgr · Workflow Registry · LLM Factory · HITL · Workspace · Checkpointer
④ PRE-PROCESSING       Requirement Agent + Solution Proposal Agent (chat feedback loop)
⑤ WORKFLOW LAYER       BRD / WBS / Proposal (3 independent DeepAgents)
⑥ TOOLS LAYER          ~205 atomic tools (Pydantic-validated, idempotent, section_id-keyed)
⑦ INFRASTRUCTURE       Subprocess Pool · MCP Host · Vector Store · Config Loader
⑧ STORAGE              Postgres · Redis · S3/MinIO · Filesystem · External LLM
```

---

## 3. End-to-End Pipeline

```
[1] User uploads files via Web UI / API
    ↓
[2] POST /sessions → creates session_id + workspace
    ↓
[3] POST /sessions/{id}/files → uploads files
    ↓
[4] POST /sessions/{id}/analyze → triggers pre-processing
        ↓
        [Requirement Agent] reads files → extracts → analyzes
            • R1 Input Triage
            • R2 Multi-format Extraction (parallel)
            • R3 Structure Extraction (7 tools)
            • R4 Domain Classification
            • R5 Gap Analysis
            • R6 HITL Clarification (max 5 Qs, max 2 rounds)
            • R7 Re-extraction
            • R8 Validation & Save
        Output: requirement_analysis.json
        ↓
        [Solution Proposal Agent] designs + draws + iterates
            PART A: Initial Proposal (S1-S9, single-pass deterministic)
                • S1 Foundation Load
                • S2 Architecture Type (mono/micro/serverless/hybrid)
                • S3 Tech Stack per layer (9 sub-tools)
                • S4 Deployment topology
                • S5 Integration design
                • S6 Security architecture (domain-aware)
                • S7 Module decomposition
                • S8 Diagram generation (MCP drawio: system_context, component, sequence, deployment)
                • S9 Initial Presentation (SSE stream)
            PART B: Chat Feedback Loop (S10, iterative, max 15)
                • S10.1 Receive message
                • S10.2 Intent classification (REFINE/QUESTION/ROLLBACK/APPROVE)
                • S10.3 REFINE branch (atomic patch + edit_diagram)
                • S10.4 Stream response
                • S10.5 QUESTION branch (no state change)
                • S10.6 ROLLBACK branch (restore snapshot)
                • S10.7 USER MANUAL DRAWIO EDIT (sync from browser)
            PART C: Approval & Save (S11)
                • detect_approval (keyword + LLM classifier)
                • save_solution / save_chat_history / export final diagrams
        Output: solution.json + diagrams/*.drawio + chat_history.json
        ↓ FOUNDATION READY (unlock downstream)
[5] User triggers downstream workflows (any order, can skip):
    POST /sessions/{id}/run {workflow: "brd"}
        ↓
        [BRD Workflow] 4 phases
            • P1 section_drafter (reads requirement+solution)
            • P2 critic_agent (deterministic validation)
            • P3 refiner (tone, numbering)
            • P4 exporter (subprocess: docxtpl)
        Output: BRD/{name}.docx

    POST /sessions/{id}/run {workflow: "wbs"}
        ↓
        [WBS Workflow] 9 phases × 75 tools
            • P1 module_decomposer (5 tools)
            • P2 task_breakdown (22 tools)
            • P3 effort_estimator (16 tools, with multipliers + benchmarks)
            • P4 phase_planner (10 tools)
            • P5 timeline_planner (8 tools)
            • P6 cost_calculator (10 tools)
            • P7 wbs_validator (10 tools)
            • [HITL gate]
            • P8 template_filler (12 tools, openpyxl preserve formulas)
            • P9 finalizer (5 tools)
        Output: WBS/{name}.xlsx

    POST /sessions/{id}/run {workflow: "proposal"}
        ↓
        [Proposal Workflow]
            • executive_summary
            • solution_pitcher (uses upstream diagrams)
            • case_study_agent (RAG over BnK history)
            • pricing_agent (reads cost.json)
            • slide_layouter + exporter (subprocess: python-pptx)
        Output: Proposal/{name}.pptx
```

---

## 4. Agents Detail (5 specialists)

### Agent 1: Requirement Agent (NEW pre-processing)

| Field | Value |
|-------|-------|
| Phases | 7 (R1-R8) |
| Tools | 22 |
| Model | claude-sonnet-4-6 · temp=0.0 |
| State | RequirementState |
| Output | requirement_analysis.json |
| HITL | Clarifying questions (max 5, max 2 rounds) |

**System prompt key directives:**
- Read raw files exhaustively
- Extract structured information (Pydantic-validated)
- Ask user if missing critical info (domain, team, deadline, deploy_env, compliance)
- Vietnamese in → Vietnamese preserved

### Agent 2: Solution Proposal Agent (NEW pre-processing)

| Field | Value |
|-------|-------|
| Phases | 11 (S1-S11) |
| Tools | 35 |
| Model | claude-sonnet-4-6 · temp=0.3 |
| State | SolutionState |
| Output | solution.json + diagrams/*.drawio |
| HITL | Iterative chat feedback loop (max 15 iterations) |
| Special | MCP drawio integration |

**System prompt key directives:**
- Always present 2-3 architecture alternatives with trade-offs
- Draw diagrams with MCP drawio
- Iterate via chat — apply atomic patches, never regenerate
- Stop when user approves

### Agent 3: BRD Workflow (BA-enhanced, 9 phases)

| Field | Value |
|-------|-------|
| Phases | 9 (B1 Foundation → B2 Exec → B3 Stakeholder → B4 Process → B5 Rules → B6 FRs → B7 NFR → B8 Risk → B9 Critic+Render) |
| Tools | 70 |
| Model | claude-sonnet-4-6 · temp=0.3 |
| State | BRDState |
| Output | OUTPUT_DIR/{project}/BRD/{name}.docx + diagrams/brd/*.png |
| Special | MCP drawio integration · BA methodologies (SWOT, BPMN, RACI, traceability) |

**Reads upstream:** requirement_analysis.json + solution.json + diagrams/

**BA methodologies integrated** (from VoltAgent business-analyst.md):
- B2: SMART objectives + KPI framework + ROI
- B3: RACI matrix + influence×interest grid + personas + journey mapping
- B4: BPMN AS-IS / BPMN TO-BE + gap analysis + value stream
- B5: Business rules (BR01..) categorized
- B6: User stories (As-X-I-want-So-that) + use cases (actor+flows+exceptions) + AC (Given-When-Then BDD)
- B7: NFR with measurable units + measurement method
- B8: Risk register (probability × impact) + SWOT + risk heat map
- B9: 100% requirements traceability matrix (FR ↔ BR ↔ AC ↔ Test)

**Diagrams generated via MCP drawio (XML → PNG → embed in .docx):**
- B4: bpmn_as_is, bpmn_to_be, value_stream
- B6: use_case_*, sequence_*  (per FR group / per flow)
- B7: dfd_L0, dfd_L1, state_*  (per stateful entity)
- B8: risk_matrix
- Reused (linked from solution agent): system_context, component, deployment

**Total diagrams per BRD:** ~10-20

**Detailed plan:** [IMPLEMENTATION_PLAN_BRD.md](IMPLEMENTATION_PLAN_BRD.md)

### Agent 4: WBS Workflow

| Field | Value |
|-------|-------|
| Phases | 9 (P1 module_decomp → ... → P9 finalize) |
| Tools | 75 |
| Model | gpt-5.4-mini for most (cheap), claude for complex |
| State | WBSState |
| Output | OUTPUT_DIR/{project}/WBS/{name}.xlsx |

**Reads upstream:** requirement_analysis.json + solution.json + brd_state.json (if exists)

### Agent 5: Proposal Workflow (Phase 2 deliverable)

| Field | Value |
|-------|-------|
| Subagents | executive_summary · solution_pitcher · case_study · pricing · slide_layouter · exporter |
| Tools | ~40 |
| Model | claude-sonnet-4-6 |
| State | ProposalState |
| Output | OUTPUT_DIR/{project}/Proposal/{name}.pptx |

**Reads upstream:** requirement_analysis.json + solution.json + cost.json + diagrams/ (REUSED, not redrawn)

---

## 5. Tools Catalog (~285 raw → 155 consolidated → 70 LLM-callable + 85 Graph-node)

> See [TOOLS_INVENTORY.md](TOOLS_INVENTORY.md) for full audit + consolidation plan.
> See [TOOLS_CLASSIFICATION.md](TOOLS_CLASSIFICATION.md) for LLM vs Graph split.
>
> Key principle: **"LLM as decision-maker, Graph as executor."**
> Per agent invocation: LLM sees only 5-15 scoped tools (not all 155) → 80% token savings.
> Reduction summary: 285 raw → 155 unique → 70 LLM-callable per phase.

### Skills loaded conditionally (5 SKILL.md files in `skills/`)

| Skill | When loaded | Purpose |
|-------|------------|---------|
| `requirement_analysis/SKILL.md` | Requirement Agent | BA discovery: extraction templates + clarifying Q patterns |
| `solution_design/SKILL.md` | Solution Proposal Agent | Architecture + tech stack + domain defaults + chat refinement |
| `brd_writing/SKILL.md` | BRD Workflow B2-B8 | BA-grade BRD section templates (SMART, RACI, user stories, AC, NFR with units) |
| `wbs_estimation/SKILL.md` | WBS Workflow P3-P5 | Effort estimation: benchmark lookup + multipliers + envelopes + sanity checks |
| `diagram_drawing/SKILL.md` | Solution + BRD agents | XML→PNG via MCP drawio: 11 diagram types + layout best practices + incremental edits |

Skills are **conditionally loaded** — only when relevant phase runs, saving prompt tokens.

### Pre-processing tools (57)

| Module | Count | Tools |
|--------|------:|-------|
| `requirement_ops.py` | 22 | list_input_files, classify_files, prioritize_files, read_pdf, read_docx, read_pptx, read_xlsx, read_md, read_image, consolidate, extract_business_context, extract_objectives, extract_stakeholders, extract_raw_frs, extract_raw_nfrs, extract_constraints, extract_integrations, identify_domain, lookup_domain_profile, detect_compliance_signals, check_critical_fields, prepare_clarifying_questions, ask_clarifying_questions, parse_clarification_response, validate_completeness, save_requirement_analysis |
| `solution_ops.py` | 7 | propose_architecture_type, propose_*_stack (9 layers), propose_deployment, define_integration_pattern, design_security_architecture, decompose_into_modules, evaluate_alternatives |
| `mcp_drawio_ops.py` | 5 | mcp_drawio_start_session, mcp_drawio_create_new_diagram, mcp_drawio_edit_diagram, mcp_drawio_get_diagram, mcp_drawio_export_diagram |
| `feedback_ops.py` | 8 | receive_message, classify_intent, identify_change_target, save_diff_snapshot, apply_atomic_patch, re_validate, explain_decision, restore_snapshot |
| `approval_ops.py` | 4 | detect_approval, save_solution, save_chat_history, emit_completion_event |
| Solution rest | 11 | propose_be/fe/db/cache/queue/search/ai/infra_stack, validate_against_must_use, select_deployment_env, propose_sizing/ha/dr |

### WBS tools (75)

See [IMPLEMENTATION_PLAN_FULL.md](IMPLEMENTATION_PLAN_FULL.md) phases for full list.

| Phase | Module | Count |
|-------|--------|------:|
| P1 | `module_ops.py` | 5 |
| P2 | `task_ops.py` | 22 |
| P3 | `effort_ops.py` | 16 |
| P4 | `phase_ops.py` | 10 |
| P5 | `timeline_ops.py` | 8 |
| P6 | `cost_ops.py` | 10 |
| P7 | `wbs_validators.py` | 10 |
| P8 | `template_filler.py` | 12 |
| P9 | `wbs_finalizer.py` | 5 |

### BRD tools (70 — BA-enhanced)

| Module | Count | Key tools |
|--------|------:|-----------|
| `brd_ops.py` | 30 | init_brd, set_executive_summary, set_brd_purpose, set_brd_objectives_smart, set_brd_success_metrics, set_brd_business_case, set_brd_intended_audience, set_brd_stakeholder_matrix, set_brd_user_personas, set_brd_user_journey, set_brd_communication_plan, set_brd_scope_inscope/outofscope, set_brd_delivery_phases, set_brd_gap_analysis, set_brd_user_needs, set_brd_assumptions, set_brd_business_rules, set_brd_constraints, upsert_fr, add_user_story, add_use_case, add_acceptance_criteria, link_fr_to_business_rule, set_brd_ui_notes/hardware/software_description/tech_stack/communication, set_brd_system_features, update_nfr_category × 4, set_brd_risk_register, set_brd_swot_analysis, append_abbreviation |
| `brd_diagram_ops.py` | 13 | mcp_drawio_create_bpmn_as_is, _bpmn_to_be, _value_stream, _use_case_diagram, _sequence_diagram, _dfd, _state_diagram, _risk_matrix, mcp_drawio_export_to_png, embed_diagram_in_brd, embed_diagram_in_fr, embed_diagram_ref, mcp_drawio_get_diagram |
| `brd_validators.py` | 7 | validate_brd, validate_traceability_matrix, validate_acceptance_criteria, check_language_consistency, check_fr_numbering_continuity, check_terminology_consistency, check_business_rule_coverage |
| `brd_renderer.py` | 4 | render_brd_to_docx (subprocess: docxtpl with PNG embedding), verify_embedded_diagrams, save_to_output_dir, upload_to_s3 |

### Proposal tools (~40)

| Module | Tools |
|--------|-------|
| `proposal_ops.py` | generate_executive_summary, pitch_solution, list_pricing_tiers, add_case_study |
| `slide_ops.py` | add_slide, set_slide_layout, embed_diagram, add_chart |
| `pptx_renderer.py` | render_proposal (subprocess) |
| `rag_ops.py` | rag_similar_projects, rag_case_studies |

### Shared tools (~20)

| Module | Tools |
|--------|-------|
| `workspace.py` | get_workspace, set_workspace, read/write_json, read/write_model |
| `folder_manager.py` | create_project_folder, get_output_paths, list_project_outputs, set_output_dir, upload_to_s3 |
| `file_reader.py` | (shared with Requirement Agent) |
| `websearch_ops.py` | tavily_search |
| `hitl_ops.py` | ask_user, request_approval |

---

## 6. State Schemas (inheritance chain)

Adopted from Paper2Any pattern:

```python
@dataclass
class MainRequest:                     # config root
    chat_api_url: str = os.getenv("DF_API_URL", "...")
    api_key: str = os.getenv("DF_API_KEY", "...")
    model: str = "claude-sonnet-4-6"
    language: str = "vi"

class MainState(TypedDict):            # state root (all workflows extend)
    session_id: str
    tenant_id: str
    project_context: ProjectContext
    output_dir: str                    # user-controlled
    workspace_dir: str
    messages: Annotated[list[BaseMessage], add_messages]
    llm_config: LLMConfig              # lazy LLM client config
    temp_data: dict

class RequirementState(MainState):     # Requirement Agent
    raw_files: list[FileRef]
    business_context: str
    objectives: list[str]
    stakeholders: list[Stakeholder]
    raw_frs: list[RawFR]
    raw_nfrs: dict[str, list[NFRStatement]]
    constraints: Constraints           # budget, timeline, tech, compliance
    integrations: list[Integration]
    domain: str                        # one of 26
    industry: str
    clarifications: list[QnA]
    analysis_complete: bool

class SolutionState(MainState):        # Solution Agent
    requirement_ref: str               # path to requirement_analysis.json
    architecture_type: str             # mono/micro/serverless/hybrid
    architecture_rationale: str
    alternatives_considered: list[Alternative]
    tech_stack: dict[str, list[Tech]]
    deployment: Deployment
    integrations_design: list[IntegrationDesign]
    modules: list[ModuleSpec]
    security_arch: SecurityArch
    diagrams: list[DiagramRef]         # paths to .drawio files
    chat_iterations: int
    chat_diff_history: list[Diff]      # rollback support
    solution_approved: bool

class BRDState(MainState):             # BRD Workflow
    requirement_ref: str
    solution_ref: str
    brd_doc: BRDDocument               # Pydantic AST
    issues: list[Issue]
    revision_count: int
    rendered_path: str | None

class WBSState(MainState):             # WBS Workflow
    requirement_ref: str
    solution_ref: str
    wbs_doc: WBSDocument
    modules: list[Module]
    effort_model: EffortModel          # active multipliers
    timeline: Timeline                 # sprints + milestones
    cost: CostBreakdown
    domain_profile: DomainProfile      # from 26 industry rules
    revision_count: int

class ProposalState(MainState):        # Proposal Workflow
    requirement_ref: str
    solution_ref: str
    wbs_ref: str                       # cost.json reference
    diagrams: list[DiagramRef]         # REUSED from solution
    slides: list[SlideSpec]
    case_studies: list[CaseStudy]
    pricing_tiers: list[PricingTier]
    template_path: str
```

---

## 7. Domain Rules (26 industries)

**File:** [config/domain_rules.yaml](config/domain_rules.yaml)
**Editable** without touching Python.

### Schema per domain

```yaml
domain_name:
  multipliers: {be_multiplier, fe_multiplier, ai_multiplier}
  ratios: {qc_pct, ba_pct, pm_pct}
  durations: {uat_weeks, deploy_days_per_env, hypercare_weeks}
  buffers: {base_buffer_pct, integration_overhead_md}
  mandatory_tasks: [{id, category, md, role}]
  default_deployment_env: cloud | on_premise | hybrid
  default_compliance: [PCI-DSS, HIPAA, ...]
  default_archs_recommended: [microservices, ...]
  default_archs_avoided: [serverless, ...]
  notes: human-readable
```

### Quick reference table

| Domain | BE × | QC % | BA % | UAT | Buffer | Mandatory tasks |
|--------|-----:|-----:|-----:|----:|-------:|-----------------|
| **defense** | 1.40 | 45% | 25% | 6w | 30% | air_gapped_test, classified_review, tempest |
| **banking** | 1.30 | 40% | 20% | 4w | 20% | pen_test, cab_approval, sast/dast, dr_test |
| **blockchain** | 1.30 | 40% | 18% | 4w | 25% | smart_contract_audit, formal_verification |
| **telecom** | 1.30 | 38% | 18% | 4w | 20% | tmf_compliance, ha_failover, oss_bss |
| **energy** | 1.30 | 38% | 18% | 4w | 22% | scada_security, hazop, hse_review |
| **insurance** | 1.25 | 40% | 20% | 3w | 18% | regulatory_audit, business_rule_validation |
| **fintech** | 1.20 | 35% | 15% | 3w | 18% | pen_test, kyc_compliance |
| **manufacturing** | 1.20 | 32% | 14% | 3w | 18% | edge_calibration, ot_security, plc_integration |
| **healthcare** | 1.20 | 35% | 18% | 3w | 18% | hipaa_audit, anonymization, clinical_uat |
| **transportation** | 1.20 | 32% | 14% | 2w | 18% | safety_audit, gps_certification, latency_test |
| **government** | 1.15 | 35% | 25% | 4w | 25% | security_clearance, srs_signoff, vapt |
| **gaming** | 1.15 | 35% | 10% | 2w | 18% | latency_test, anti_cheat_audit |
| **legal_tech** | 1.15 | 30% | 18% | 3w | 16% | legal_review, doc_anonymization |
| **media** | 1.15 | 30% | 12% | 2w | 14% | drm_audit, cdn_test |
| **logistics** | 1.15 | 30% | 14% | 2w | 15% | realtime_test, multi_carrier_audit |
| **hr_tech** | 1.15 | 30% | 16% | 3w | 16% | payroll_audit, tax_compliance |
| **ai_ml_platform** | 1.10 | 30% | 15% | 2w | 20% | model_validation, drift_monitoring |
| **agriculture** | 1.10 | 28% | 14% | 2w | 14% | sensor_field_test, offline_sync |
| **education** | 1.10 | 28% | 13% | 2w | 12% | accessibility_audit, parental_consent |
| **ecommerce** | 1.10 | 28% | 12% | 2w | 12% | payment_security_audit, load_test |
| **retail** | 1.10 | 28% | 13% | 2w | 12% | offline_mode_test, pos_certification |
| **fnb** | 1.10 | 28% | 12% | 2w | 12% | offline_pos_test, multi_outlet_test |
| **real_estate** | 1.10 | 28% | 13% | 2w | 12% | listing_validation, escrow_audit |
| **ngo** | 1.0 | 25% | 12% | 2w | 10% | donor_audit |
| **research** | 1.0 | 20% | 10% | 1w | 10% | open_data_compliance, reproducibility |
| **standard** | 1.0 | 25% | 12% | 2w | 10% | (none) |

---

## 8. Effort Benchmarks (from real BnK WBS)

**File:** [config/effort_benchmarks.json](config/effort_benchmarks.json)
**Source:** 12 real BnK WBS files, >650 leaf tasks
**Use median, not avg** (avg skewed by mega-tasks like HLAS Predictive Risk = 118 MD)

### Project size envelopes

| Project type | Min MD | Median MD | Max MD | Leaf count |
|--------------|-------:|----------:|-------:|-----------:|
| Small PoC | 20 | 30 | 50 | 15-25 |
| Lending baseline | 130 | 150 | 200 | 30-50 |
| AI/CV per feature | 200 | 280 | 350 | 30-40 |
| IoT mid-size | 150 | 180 | 250 | 40-60 |
| Insurance system | 1500 | 2000 | 2600 | 100-130 |
| AI platform internal | 3000 | 3500 | 4000 | 100-150 |

### Phase distribution (default split)

- **Setup:** 8% (range 4-24%)
- **Development:** 80% (range 70-85%)
- **Testing/Deploy:** 12% (range 10-17%)

### Quick lookup table (median MD)

| Task category | Median |
|---------------|-------:|
| Database/Schema design | 5.5 |
| HLD / System architecture | 7.7 |
| API design | 3 |
| UI/UX design (per module) | 3.3 |
| Code base setup | 2.2 |
| **CRUD list/view page** | **15.8** |
| **CRUD form/upload** | **24.6** |
| Search/filter | 17.6 |
| Auth/login (FE) | 1.5 |
| Role/permission UI | 12.3 |
| Audit log | 12.3 |
| Workflow/business rules | 4.0 |
| Notification/email/SMS | 8.8 |
| Renewal/SLA flow | 17.6 |
| Report/dashboard | 12.3 |
| Export PDF/Excel | 3.5 |
| **3rd party integration** | **13.2** |
| AI — data collect/label | 11.0 |
| AI — data prep | 17.0 |
| **AI — train model** | **19.0** |
| AI — inference API | 6.6 |
| AI — benchmark | 3.3 |
| LLM tuning | 10 |
| OCR training | 20 |
| SIT (small project) | 7.7 |
| **SIT (large insurance)** | **105** |
| UAT support per cycle | 6.3 |
| Bug fix bucket | 10 |
| Deployment per env | 6.6 |
| Production deploy | 2 |
| Hypercare | 11 |
| Documentation | 3 |
| Training (1 cohort) | 4.2 |
| Edge/IoT calibration | 5.5 |

### AI lifecycle bundle (per ML model)

```
data_collect:    10 MD
data_label:      11
data_prep:       17
train_model:     19
tune_model:      10
benchmark:        3
inference_api:    7
integration:     10
─────────────────────
TOTAL:           87 MD
```

### Role ratios per domain (% of total)

| Domain | BE | FE | AI | BA | QC | PM |
|--------|---:|---:|---:|---:|---:|---:|
| Insurance | 44% | 15% | 0 | 11% | 21% | 9% |
| AI/CV | 31% | 9% | 27% | 9% | 14% | 9% |
| Manufacturing edge AI | 26% | 3% | 33% | 9% | 21% | 9% |
| Lending (web) | 49% | 26% | 0 | 5% | 15% | 5% |
| NLP PoC | 2% | 22% | 30% | 16% | 22% | 9% |

### Master Data defaults (BnK standard)

```yaml
PM:        0.05  # in total dev+ba+qc; banking/insurance bumps to 0.10
BA:        0.10  # of dev; insurance bumps to 0.20
QC:        0.30  # of dev; insurance bumps to 0.40
Currency:  2,500,000 VND/MD = 24,500 VND/USD × 100 USD/MD baseline
Default rates (USD/MD): PM 500, BA 400, Dev 450, QC 350
```

---

## 9. BnK WBS Template Fill (Phase 10)

**Critical task — full spec in [IMPLEMENTATION_PLAN_TEMPLATE_FILL.md](IMPLEMENTATION_PLAN_TEMPLATE_FILL.md)**

### Template path
`/mnt/f/code/agent/WBS_Agent/WBS/[BnK] Template - WBS.xlsx`
(Override via `BNK_TEMPLATE_PATH` env var)

### Template sheets

| Sheet | Role | Editable cells |
|-------|------|---------------|
| `0. How to use` | docs | – |
| `1. Effort` | auto-summary (VLOOKUP from sheet 2) | – |
| **`2. WBS`** | **main fill target** | B/D/E/G/H/L of L4 rows |
| `3. Delivery Plan (By Month)` | sprint allocation | D/E + sprint cells |
| `3. Delivery Plan` | weekly | same |
| **`4. Master Data`** | rates + percentages | C3-C6, C10-C13 |

### Critical fill rules

```python
wb = openpyxl.load_workbook(path, data_only=False, keep_vba=False)
# data_only=False PRESERVES formulas (VLOOKUP, SUM, CONCATENATE)
# data_only=True would replace formulas with last cached values (BAD)

# Fill ONLY these columns of L4 rows:
EDITABLE_COLS_L4 = ["B", "D", "E", "G", "H", "L"]
# B=task num, D=feature, E=description, G=BE_md, H=FE_md, L=remark

# DO NOT TOUCH formula columns:
FORMULA_COLS = ["C", "F", "I", "J", "K"]
# C=ref code (CONCATENATE), F=Total (SUM), I/J/K=BA/QC/PM (computed × Master Data)
```

### 12 fill tools

```python
load_wbs_template(template_path, output_path, project_code)  # copy + set D2
set_wbs_project_metadata(workbook_path, name, code, currency_rate)
clear_template_placeholder_rows(workbook_path)               # rows 6-76
add_wbs_phase_l1_row(phase_id="I"|"II"|"III", name)
add_wbs_subphase_l2_row(parent_phase, letter="A"|"B", name)
add_wbs_module_l3_row(parent_l2, num, name)
add_wbs_task_l4_row(parent, num, feature, desc, md_be, md_fe, remark, source_fr_id)
set_master_data(pm_pct, ba_pct, qc_pct, rates_dict, currency)
fill_delivery_plan_modules(modules_with_dates)
fill_delivery_plan_resources(role_allocation_per_sprint)
fill_effort_summary_sheet(workbook_path)                     # verify formulas
verify_template_integrity(workbook_path)                     # sanity check
```

---

## 10. Chat Feedback Loop + MCP Drawio

**The differentiator** — see Page 6 of architecture.drawio for full detail.

### Flow

```
Solution Agent proposes initial solution + draws 4 diagrams via MCP drawio
    ↓
Stream summary + diagram previews to user via SSE
    ↓
User sends message via /chat (e.g., "Đổi PostgreSQL sang MongoDB")
    ↓
classify_intent() → REFINE | QUESTION | ROLLBACK | APPROVE
    ↓
[REFINE branch]
    save_diff_snapshot(current_state)
    apply_atomic_patch(field, new_value)        # solution.json
    mcp__drawio__edit_diagram(operations)       # update diagram cells
    mcp__drawio__export_diagram(.png)           # re-render
    re_validate_against_constraints()
    Stream tool_call + diagram + token events
    ↓
Loop back (max 15 iterations)
    ↓
[APPROVE branch]
    detect_approval(message)                    # keyword + LLM classifier
    if confidence ≥ 0.85: save_solution()
    else: ask confirmation
    ↓
emit_completion_event() → unlock BRD/WBS/Proposal
```

### MCP drawio tools used

```python
mcp__drawio__start_session()                        # opens browser preview
mcp__drawio__create_new_diagram(xml)                # initial diagram
mcp__drawio__edit_diagram(operations=[             # subsequent edits
    {operation: "update", cell_id: "...", new_xml: "..."},
    {operation: "add", cell_id: "...", new_xml: "..."},
    {operation: "delete", cell_id: "..."},
])
mcp__drawio__get_diagram()                          # fetch latest (incl. user edits)
mcp__drawio__export_diagram(path, format)           # png/svg/drawio
```

### Diagrams produced (per session)

1. `system_context.drawio` — external systems + this system
2. `component.drawio` — internal modules + dependencies
3. `sequence_*.drawio` — 1-3 key user flows
4. `deployment.drawio` — infra topology

### Approval detection (hybrid)

```python
APPROVAL_PHRASES = [
    "ok", "approve", "approved", "đồng ý", "ok đi", "duyệt",
    "ok approve", "final", "ok rồi", "ok then", "lgtm", "ship it"
]

def detect_approval(message: str) -> ApprovalDetection:
    msg = message.lower().strip()
    # Fast path
    if any(phrase in msg for phrase in APPROVAL_PHRASES):
        return ApprovalDetection(intent="approve", confidence=0.95)
    # LLM classifier fallback
    return llm.invoke(...).structured_response
```

### SSE events streamed

```
event: token        data: {"content": "..."}
event: tool_call    data: {"tool": "edit_diagram", "args": {...}}
event: diagram      data: {"path": "...png", "version": 3}
event: hitl         data: {"reason": "...", "questions": [...]}
event: approval     data: {"detected": true, "confidence": 0.92}
event: done         data: {"foundation_ready": true}
```

---

## 11. Implementation Plan (sprint roadmap)

| Sprint | Goal | Effort | Files |
|--------|------|-------:|-------|
| **S0** | Foundation (registry, state base, subprocess pool, LLM factory) | 3d | workflows/registry.py, state/base.py, infra/subprocess_pool.py, llm/factory.py |
| **S0.5** | Pre-processing stage (Requirement + Solution agents) | 10.5d | tools/requirement_ops.py, tools/solution_ops.py, tools/mcp_drawio_ops.py, tools/feedback_ops.py, agents/requirement.py, agents/solution_proposal.py, infra/mcp_host.py |
| **S1** | Domain rules YAML + benchmarks JSON (DONE) | done | config/domain_rules.yaml, config/effort_benchmarks.json |
| **S2** | WBS workflow P1-P3 (module decomp + task breakdown + effort) | 5d | tools/module_ops.py, tools/task_ops.py, tools/effort_ops.py, agents/* |
| **S3** | WBS P4-P6 (phase + timeline + cost) | 4d | tools/phase_ops.py, tools/timeline_ops.py, tools/cost_ops.py, agents/* |
| **S4** | WBS P7-P9 (validator + template_filler + finalizer) | 5d | tools/wbs_validators.py, tools/template_filler.py, agents/* |
| **S5** | BRD workflow (4 phases) | 4d | tools/brd_ops.py, agents/brd_*.py |
| **S6** | Orchestrator integration + API endpoints + SSE | 4d | orchestrator.py, api/main.py |
| **S7** | E2E test on GEHP, MBAL fixtures | 3d | tests/test_e2e_*.py |
| **S8** | Proposal workflow (Phase 2 deliverable) | 7d | tools/proposal_ops.py, tools/slide_ops.py, agents/proposal_*.py |
| **Total** | | **~46d (~9 weeks for 1 engineer)** | |

### Critical implementation rules

1. **Tool atomicity** — every tool does ONE thing
2. **Idempotent** — calling twice with same args = same state
3. **Section IDs everywhere (UUID)** — for incremental patches, no regeneration
4. **Pydantic at every boundary** — validate args + returns
5. **Template formulas PRESERVED** — `data_only=False`, never overwrite formula cells
6. **Domain rules from YAML** — `config/domain_rules.yaml` is primary, Python fallback only
7. **`lookup_benchmark_effort(category, complexity)`** — primary effort source, NOT LLM imagination
8. **HITL gates: 2** — after Discovery (Requirement Agent) + before Template Fill (Phase 8)
9. **Incremental update** — user says "đổi effort task X thành 3d" → call only relevant tools
10. **Folder control: 3 layers** — env var + CLI flag + API endpoint
11. **Multi-tenant via lazy LLM client** — API key from session state, not env
12. **Subprocess pool for renderers** — openpyxl/docxtpl/python-pptx not thread-safe

---

## 12. API Contracts

### Sessions

```http
POST /sessions
Body: {
  "project_name": "MBAL_IDP_Phase2",
  "input_dir": "/path/to/input",       # optional, default ATTACHMENTS_DIR
  "output_dir": "/path/to/output",     # optional, default OUTPUT_DIR
  "model": "anthropic:claude-sonnet-4-6",  # optional
  "language": "vi"
}
Response: {
  "session_id": "uuid",
  "input_dir": "/...",
  "output_dir": "/...",
  "workspace_dir": "/..."
}
```

### File upload

```http
POST /sessions/{id}/files
Content-Type: multipart/form-data
Body: files[]
Response: {"uploaded": ["/path/to/file1", ...]}
```

### Pre-processing

```http
POST /sessions/{id}/analyze
Body: {}
Response (SSE):
  event: progress  data: {"step": "intake", "files": 3}
  event: token     data: {"content": "Đang đọc file 1..."}
  event: hitl      data: {"questions": ["Domain?", "Team?"]}
  event: done      data: {"foundation_ready": false, "needs_clarification": true}
```

### Chat (feedback loop)

```http
POST /sessions/{id}/chat
Body: {"message": "đổi PostgreSQL sang MongoDB"}
Response (SSE):
  event: token       data: {"content": "Đã đổi sang MongoDB..."}
  event: tool_call   data: {"tool": "mcp_drawio_edit_diagram"}
  event: diagram     data: {"path": "...", "version": 3}
  event: token       data: {"content": "...transactions yếu hơn..."}
```

### Run downstream workflow

```http
POST /sessions/{id}/run
Body: {"workflow": "brd" | "wbs" | "proposal"}
Response (SSE): stream of workflow execution
```

### HITL approval

```http
POST /sessions/{id}/approve
Body: {
  "tool_name": "render_wbs",
  "decision": "approve" | "reject" | "edit",
  "edited_args": {...}      # if decision == "edit"
}
Response: {"status": "resumed", "message": "..."}
```

### Folder control runtime

```http
POST /sessions/{id}/output-dir
Body: {"output_dir": "/new/path"}
Response: {"output_dir": "/new/path", "message": "..."}
```

### State + outputs

```http
GET /sessions/{id}/state
Response: {
  "session_id": "uuid",
  "project_name": "...",
  "requirement_analysis": {...},
  "solution": {...},
  "brd": {...},                # null if BRD workflow not run yet
  "wbs": {...},
  "issues": [...]
}

GET /sessions/{id}/outputs
Response: {
  "artifacts": [
    {"path": "/...", "name": "MBAL_BRD_v0_1_0.docx", "type": "docx", "size_kb": 156},
    ...
  ]
}

GET /sessions/{id}/diagram?type=system_context&format=png
Response: image/png

GET /sessions/{id}/foundation
Response: {
  "status": "approved",
  "requirement_analysis": {...},
  "solution": {...},
  "diagrams": [...],
  "chat_iterations": 5,
  "approved_at": "2026-04-26T..."
}
```

---

## 13. Folder Control (3 layers)

User controls output folder at **3 priority levels** (highest first):

### 1. API runtime (per-session)

```bash
curl -X POST http://localhost:8000/sessions/{id}/output-dir \
  -d '{"output_dir": "/my/path"}'
```

### 2. CLI flag

```bash
python main.py --input ./req --output /my/path --project "MBAL"
```

### 3. Env var (default)

```bash
export OUTPUT_DIR=/my/path
python main.py
```

### Output structure (always)

```
{OUTPUT_DIR}/
└── {project_name}/                    # e.g. MBAL_IDP_Phase2
    ├── BRD/{project_name}_BRD_v0_1_0.docx
    ├── WBS/{project_name}_WBS_v0_1_0.xlsx
    ├── Proposal/{project_name}_Proposal_v0_1_0.pptx
    └── diagrams/
        ├── system_context.drawio + .png + .svg
        ├── component.drawio + .png + .svg
        ├── sequence_*.drawio + .png + .svg
        └── deployment.drawio + .png + .svg
```

---

## 14. Production Patterns Adopted

### From LangChain Multi-Agent docs

1. **Subagents pattern** — multi-domain delegation via `@tool` wrapping
2. **Custom workflow** — deterministic StateGraph for phase orchestration
3. **Skills** — domain-specific knowledge in `skills/{domain}/SKILL.md`
4. **Handoff pattern** — limited use, only for Critic ↔ Drafter loop
5. **`@wrap_model_call` middleware** — dynamic config per state

### From Paper2Any (similar problem domain)

1. **State inheritance chain** — MainState → 5 specialized states
2. **Workflow decorator registry** — `@register("brd")` def build_brd_graph()
3. **Subprocess pool for heavy I/O** — JSON file I/O between processes (no Celery/Redis needed)
4. **Lazy LLM client** — provider/key from session state, not hardcoded env
5. **NOT adopted:** hand-rolled BaseAgent (DeepAgents covers it), pre/post tool hooks (subagent dict enough), multi-process for LLM calls (only for rendering)

### Key DeepAgents features used

```python
from deepagents import create_deep_agent
from deepagents.backends import (
    FilesystemBackend, CompositeBackend, StoreBackend
)

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",
    tools=[...],
    system_prompt="...",
    subagents=[
        {"name": "...", "description": "...", "system_prompt": "...", "tools": [...]},
    ],
    backend=CompositeBackend(
        default=FilesystemBackend(root_dir=workspace_dir),
        routes={
            "/input/": FilesystemBackend(root_dir=input_dir),
            "/output/": FilesystemBackend(root_dir=output_dir),
        },
    ),
    memory=["/AGENTS.md"],
    skills=["/skills/banking/", "/skills/insurance/"],
    interrupt_on={"render_brd": True, "render_wbs": True, "render_proposal": True},
    checkpointer=AsyncPostgresSaver.from_conn_string(db_url),
    response_format=FoundationOutput,  # Pydantic structured output
)
```

---

## 15. File Structure / Project Layout

```
bnk-deepagent/
├── MASTER_REFERENCE.md                          ← THIS FILE
├── README.md
├── architecture.drawio                          ← 6-page visual architecture
├── requirements.txt
├── .env.example
│
├── IMPLEMENTATION_PLAN_FULL.md                  ← Full 11-phase WBS plan (now 9)
├── IMPLEMENTATION_PLAN_PREPROCESSING.md         ← Requirement + Solution agents
├── IMPLEMENTATION_PLAN_TEMPLATE_FILL.md         ← Phase 8 (was 10) openpyxl detail
├── REVIEW_NOTES_LANGCHAIN_PAPER2ANY.md          ← Comparison + recommendations
│
├── main.py                                      ← CLI entry point
├── orchestrator.py                              ← Main workflow registry
│
├── agents/
│   ├── __init__.py
│   ├── requirement.py                           ← Pre-processing agent 1
│   ├── solution_proposal.py                     ← Pre-processing agent 2
│   ├── brd/                                     ← BRD workflow subagents
│   ├── wbs/                                     ← WBS workflow subagents (9 phases)
│   └── proposal/                                ← Proposal workflow subagents
│
├── tools/
│   ├── __init__.py
│   ├── workspace.py                             ← Session state mgmt
│   ├── file_reader.py                           ← Multi-format reading
│   ├── requirement_ops.py                       ← 22 tools
│   ├── solution_ops.py                          ← 7 + 11 tools
│   ├── mcp_drawio_ops.py                        ← 5 MCP wrappers
│   ├── feedback_ops.py                          ← Chat loop tools
│   ├── approval_ops.py                          ← Approval detection
│   ├── module_ops.py                            ← P1 (5 tools)
│   ├── task_ops.py                              ← P2 (22 tools)
│   ├── effort_ops.py                            ← P3 (16 tools)
│   ├── phase_ops.py                             ← P4 (10 tools)
│   ├── timeline_ops.py                          ← P5 (8 tools)
│   ├── cost_ops.py                              ← P6 (10 tools)
│   ├── wbs_validators.py                        ← P7 (10 tools)
│   ├── template_filler.py                       ← P8 (12 tools) ★
│   ├── wbs_finalizer.py                         ← P9 (5 tools)
│   ├── brd_ops.py                               ← BRD section tools
│   ├── brd_validators.py
│   ├── proposal_ops.py
│   ├── slide_ops.py
│   ├── folder_manager.py                        ← OUTPUT_DIR control
│   ├── renderer.py                              ← Subprocess wrappers
│   ├── websearch_ops.py                         ← Tavily + RAG
│   └── hitl_ops.py
│
├── state/
│   ├── __init__.py
│   ├── base.py                                  ← MainState + LLMConfig
│   ├── requirement.py                           ← RequirementState
│   ├── solution.py                              ← SolutionState
│   ├── brd.py                                   ← BRDState
│   ├── wbs.py                                   ← WBSState
│   └── proposal.py                              ← ProposalState
│
├── workflows/
│   ├── __init__.py
│   ├── registry.py                              ← @register decorator
│   ├── pre_processing.py                        ← Requirement → Solution
│   ├── brd.py                                   ← BRD workflow factory
│   ├── wbs.py                                   ← WBS workflow factory
│   └── proposal.py                              ← Proposal workflow factory
│
├── llm/
│   ├── __init__.py
│   └── factory.py                               ← Lazy LLM client (per-session)
│
├── infra/
│   ├── subprocess_pool.py                       ← Renderer isolation
│   ├── mcp_host.py                              ← MCP drawio session mgmt
│   ├── Dockerfile
│   └── docker-compose.yml
│
├── api/
│   └── main.py                                  ← FastAPI: sessions/chat/run/approve
│
├── config/
│   ├── domain_rules.yaml                        ← 26 industries (DONE)
│   ├── effort_benchmarks.json                   ← Median MD per task (DONE)
│   ├── agent_models.yaml                        ← Model per agent
│   └── output.yaml                              ← Default folder paths
│
├── skills/
│   ├── brd/SKILL.md
│   ├── wbs/SKILL.md
│   ├── banking/SKILL.md
│   ├── insurance/SKILL.md
│   └── ...
│
├── memory/
│   └── AGENTS.md                                ← Per-session template
│
├── packages/
│   └── wbs_agent_kit/                           ← Symlink/copy from bnk-agent/
│       ├── src/types.py                         ← Pydantic AST (DON'T MODIFY)
│       ├── src/render_brd.py
│       ├── src/render_wbs.py
│       └── templates/*.docx, *.xlsx
│
├── evals/
│   └── golden/
│       ├── gehp/                                ← GE Hydraulic Press fixture
│       └── mbal/                                ← MBAL IDP fixture
│
└── tests/
    ├── test_requirement_agent.py
    ├── test_solution_agent.py
    ├── test_e2e_brd.py
    ├── test_e2e_wbs.py
    └── test_template_filler.py
```

---

## 16. Open Design Decisions

### Confirmed (no change expected)

✅ DeepAgents framework (not LangGraph supervisor)
✅ 3 INDEPENDENT downstream workflows (not 1 monolithic orchestrator)
✅ State inheritance chain (Paper2Any pattern)
✅ Workflow decorator registry
✅ Subprocess pool for renderers (openpyxl/docxtpl/python-pptx)
✅ Lazy LLM client per session (multi-tenant)
✅ File-based state (JSON in workspace) — not shared TypedDict memory
✅ Pre-processing stage (Requirement + Solution agents) BEFORE 3 workflows
✅ Chat feedback loop with MCP drawio for solution refinement
✅ 26 domain rules in YAML (editable without Python)
✅ Effort benchmarks from real BnK files (median, not avg)
✅ Folder control 3 layers (env / CLI / API)
✅ HITL gates: 2 (after Discovery, before Template Fill)
✅ Critic loop max 3 retries → escalate to user
✅ Atomic incremental patches (section_id UUIDs)

### Pending user decision

| # | Question | Recommendation |
|---|----------|---------------|
| 1 | Approval detection: keyword vs LLM classifier? | **Hybrid** (keyword fast-path + LLM fallback for ambiguous) |
| 2 | MCP drawio session lifetime: per-session or global? | **Per-session** (isolation, slightly more resource) |
| 3 | Diagram preview format: PNG or SVG? | **PNG for preview + SVG + .drawio for download** |
| 4 | Max chat iterations before forced review? | **15** then escalate to engineer |
| 5 | Rollback granularity: per-iteration or per-tool-call? | **Per-iteration** (cleaner UX) |
| 6 | Multi-tenant from day 1 or refactor later? | **From day 1** (cheaper if SaaS planned) |
| 7 | Subprocess pool: only rendering or also heavy LLM? | **Only rendering** (LLM async is fine) |
| 8 | Cross-workflow data: file-based or session state? | **File-based** (workflows independent + reusable) |

---

## 17. Quick Start

### Local CLI

```bash
cd bnk-deepagent
cp .env.example .env
# Edit .env with OPENAI_API_KEY or ANTHROPIC_API_KEY

pip install -r requirements.txt

# Interactive
python main.py --input ./input --output ./outputs

# One-shot
python main.py --input /path/to/req --output /path/to/out --project "MBAL"

# API server
python main.py --serve  # → http://localhost:8000/docs
```

### Docker

```bash
cp .env.example .env
HOST_OUTPUT_DIR=/your/output \
HOST_INPUT_DIR=/your/input \
docker compose -f infra/docker-compose.yml up -d --build

# → API:           http://localhost:8000/docs
# → MinIO:         http://localhost:9001 (bnkadmin / bnkadmin123)
# → Langfuse:      http://localhost:3001
```

### API workflow

```bash
# 1. Create session
SESSION=$(curl -sX POST localhost:8000/sessions \
  -d '{"project_name": "MBAL", "output_dir": "/my/out"}' | jq -r .session_id)

# 2. Upload files
curl -X POST localhost:8000/sessions/$SESSION/files \
  -F "files=@requirement.pdf" -F "files=@spec.docx"

# 3. Trigger pre-processing
curl -X POST localhost:8000/sessions/$SESSION/analyze

# 4. Chat refinement (SSE stream)
curl -X POST localhost:8000/sessions/$SESSION/chat \
  -d '{"message": "Đổi PostgreSQL sang MongoDB"}'

# 5. Approve solution
curl -X POST localhost:8000/sessions/$SESSION/chat \
  -d '{"message": "OK approve"}'

# 6. Run downstream workflows
curl -X POST localhost:8000/sessions/$SESSION/run -d '{"workflow": "brd"}'
curl -X POST localhost:8000/sessions/$SESSION/run -d '{"workflow": "wbs"}'

# 7. Download artifacts
curl localhost:8000/sessions/$SESSION/outputs
```

---

## 18. Related Files Index

### In this project (bnk-deepagent/)

| File | Purpose |
|------|---------|
| `MASTER_REFERENCE.md` | THIS FILE — single source of truth |
| `README.md` | Quick overview + architecture diagram (text version) |
| `architecture.drawio` | 6-page visual architecture (open in drawio) |
| `IMPLEMENTATION_PLAN_FULL.md` | Full 11-phase WBS plan |
| `IMPLEMENTATION_PLAN_PREPROCESSING.md` | Pre-processing stage detail |
| `IMPLEMENTATION_PLAN_TEMPLATE_FILL.md` | Phase 10 (template filler) detail |
| `REVIEW_NOTES_LANGCHAIN_PAPER2ANY.md` | Pattern comparison + recommendations |
| `config/domain_rules.yaml` | 26 industries with multipliers + mandatory tasks |
| `config/effort_benchmarks.json` | Median effort per task category |
| `requirements.txt` | Python dependencies |
| `.env.example` | All env vars documented |

### External references

| Resource | URL |
|----------|-----|
| LangChain DeepAgents docs | https://docs.langchain.com/oss/python/deepagents/ |
| LangChain DeepAgents customization | https://docs.langchain.com/oss/python/deepagents/customization |
| LangChain multi-agent overview | https://docs.langchain.com/oss/python/langchain/multi-agent |
| LangChain Subagents pattern | https://docs.langchain.com/oss/python/langchain/multi-agent/subagents |
| LangChain Handoffs pattern | https://docs.langchain.com/oss/python/langchain/multi-agent/handoffs |
| Paper2Any reference codebase | `/mnt/f/code/agent/WBS_Agent/Paper2Any/` |

### Reused from sibling project (bnk-agent/)

| File | Purpose |
|------|---------|
| `bnk-agent/packages/wbs_agent_kit/src/types.py` | BRDDocument + WBSDocument Pydantic AST |
| `bnk-agent/packages/wbs_agent_kit/src/render_brd.py` | docxtpl renderer |
| `bnk-agent/packages/wbs_agent_kit/src/render_wbs.py` | openpyxl renderer |
| `bnk-agent/packages/wbs_agent_kit/templates/BnK_BRD_Template_v1.0.docx` | BRD template |
| `bnk-agent/packages/wbs_agent_kit/templates/BnK_WBS_Template_v1.0.xlsx` | WBS template |

### Source data references

| Path | Purpose |
|------|---------|
| `/mnt/f/code/agent/WBS_Agent/REQUIREMENT/` | Customer requirement files (input) |
| `/mnt/f/code/agent/WBS_Agent/BRD/` | 5 sample BRDs (RAG corpus) |
| `/mnt/f/code/agent/WBS_Agent/WBS/` | 18 sample WBS files (12 analyzed for benchmarks) |
| `/mnt/f/code/agent/WBS_Agent/WBS/[BnK] Template - WBS.xlsx` | Standard WBS template (filled by P10) |
| `/mnt/f/code/agent/WBS_Agent/Proposal/` | Sample proposals (RAG corpus + future templates) |

---

## Changelog

| Version | Date | Change |
|---------|------|--------|
| v1 | Day 1 | Initial 5-agent design (intake/brd/wbs/critic/exporter) |
| v2 | Day 2 | Added 11 phases × 85 tools for WBS, 26 domain rules, benchmarks from 12 real WBS |
| v3 | 2026-04-26 | Added Pre-processing stage (Requirement + Solution agents) with chat feedback loop + MCP drawio. WBS reduced to 9 phases × 75 tools. State inheritance chain. Subprocess pool. Lazy LLM client. |

---

**End of MASTER_REFERENCE.md.** This file is the single entry point — start here when revisiting the project.
