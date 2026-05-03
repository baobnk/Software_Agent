# Tools Classification — LLM-callable vs Graph-node

> **Principle:** "LLM as decision-maker, Graph as executor."
> Only expose tools to the LLM where **judgment** is required. Everything deterministic goes into LangGraph nodes (no tokens, no errors, fully testable).
>
> **Result:** From 155 consolidated tools → only **~70 LLM-callable** + 85 graph-node functions.
> Per-agent invocation: LLM sees 5-15 tools (was 42 for BRD agent) → **80% token reduction per call**.

---

## 1. Decision Criteria

### When to make a tool LLM-callable

✅ Output requires **judgment**, **creativity**, or **domain interpretation**
✅ Input is **natural language** that needs LLM parsing
✅ Multiple valid choices exist; LLM picks based on context
✅ Tool description itself helps the LLM decide flow

**Examples:**
- `propose_architecture_type` — needs to weigh trade-offs
- `extract_business_context` — needs LLM reading
- `set_brd_purpose` — needs writing narrative prose
- `classify_intent` — needs to read user message

### When to make a tool a Graph node

✅ Output is **deterministic** (math, algorithm, lookup)
✅ Always called at fixed point in pipeline
✅ Input is **structured** (JSON, file path)
✅ Failure mode is **discrete** (PASS/FAIL), not nuanced

**Examples:**
- `load_requirement_analysis` — read file, no judgment
- `validate_brd` — Python rule check
- `render_brd_to_docx` — subprocess call
- `apply_domain_multiplier` — lookup table × number

---

## 2. The Pattern (code)

```python
from langgraph.graph import StateGraph
from langchain.agents import create_agent

def build_brd_workflow():
    g = StateGraph(BRDState)

    # ── GRAPH NODES (deterministic, no LLM) ──
    g.add_node("load_foundation", load_foundation_node)
    g.add_node("init_brd", init_brd_node)

    # ── AGENT NODE (LLM-callable, scoped tools) ──
    g.add_node("draft_executive_section", create_agent(
        model="claude-sonnet-4-6",
        tools=[                                     # Only 6 tools, not 42
            set_executive_summary,
            set_brd_purpose,
            set_brd_objectives_smart,
            set_brd_success_metrics,
            set_brd_business_case,
            set_brd_intended_use,
        ],
        prompt="Draft the executive summary and objectives section..."
    ))

    # ── GRAPH NODE (deterministic) ──
    g.add_node("validate_executive", validate_section_node("executive"))

    # ── AGENT NODE (next phase, different scoped tools) ──
    g.add_node("draft_stakeholder_section", create_agent(
        model="claude-sonnet-4-6",
        tools=[                                     # 5 tools for this phase
            set_brd_intended_audience,
            set_brd_stakeholder_matrix,
            set_brd_user_personas,
            set_brd_user_journey,
            set_brd_communication_plan,
        ],
        prompt="Analyze stakeholders using RACI + personas + journey..."
    ))

    g.add_node("validate_stakeholder", validate_section_node("stakeholder"))
    # ... etc

    g.add_node("critic", critic_node)              # deterministic
    g.add_node("render_brd", render_brd_node)      # subprocess call

    # ── EDGES (deterministic flow) ──
    g.add_edge(START, "load_foundation")
    g.add_edge("load_foundation", "init_brd")
    g.add_edge("init_brd", "draft_executive_section")
    g.add_edge("draft_executive_section", "validate_executive")
    g.add_conditional_edges("validate_executive", route_after_validate)  # LLM-free routing
    # ...

    return g.compile()
```

### Why this is better than "give 42 tools to one BRD agent"

| Aspect | All 42 tools to LLM | Scoped per phase |
|--------|--------------------:|-----------------:|
| Tool descriptions in prompt | ~6,300 tokens (42 × 150) | ~900 tokens (6 × 150) |
| LLM decision space | 42 choices/turn | 6 choices/turn |
| Wrong-tool risk | High | Low |
| Debug clarity | "Why did it call X?" | "Phase 2 only has these tools" |
| Cost per phase | High | 80% lower |
| Determinism | Variable | Tight |

---

## 3. Full Classification Table

### 3.1 Requirement Agent (22 tools → 14 LLM + 8 Graph)

| Tool | Type | Reason |
|------|------|--------|
| `read_file(path, format)` | 🤖 LLM | LLM picks which file based on content |
| `list_input_files(dir)` | 🤖 LLM | (called in agent context to plan) |
| `classify_files(file_list)` | 🤖 LLM | needs LLM judgment |
| `extract_business_context()` | 🤖 LLM | LLM extraction |
| `extract_objectives()` | 🤖 LLM | LLM extraction |
| `extract_stakeholders()` | 🤖 LLM | LLM extraction |
| `extract_raw_frs()` | 🤖 LLM | LLM extraction |
| `extract_raw_nfrs()` | 🤖 LLM | LLM extraction |
| `extract_constraints()` | 🤖 LLM | LLM extraction |
| `extract_integrations()` | 🤖 LLM | LLM extraction |
| `identify_domain()` | 🤖 LLM | LLM judgment with confidence |
| `detect_compliance_signals(text)` | 🤖 LLM | LLM keyword + reasoning |
| `ask_clarifying_questions(qs[])` | 🤖 LLM | HITL trigger |
| `parse_clarification_response()` | 🤖 LLM | LLM parses user reply |
| `prioritize_files(classified)` | ⚙ Graph | sort by heuristic priority |
| `consolidate_to_md(files)` | ⚙ Graph | mechanical merge |
| `lookup_domain_profile(domain)` | ⚙ Graph | YAML lookup |
| `check_critical_fields_present()` | ⚙ Graph | dict check |
| `validate_completeness()` | ⚙ Graph | Python rules |
| `save_requirement_analysis()` | ⚙ Graph | JSON write |
| `get/set_workspace()` | ⚙ Graph | path management |

### 3.2 Solution Proposal Agent (33 → 25 LLM + 8 Graph)

| Tool | Type | Reason |
|------|------|--------|
| `evaluate_architecture_options()` | 🤖 LLM | LLM weighs alternatives |
| `propose_architecture_type()` | 🤖 LLM | judgment + rationale |
| `list_alternatives_with_tradeoffs()` | 🤖 LLM | analytical |
| `propose_tech_stack(layer, ...)` | 🤖 LLM | per-layer selection |
| `select_deployment_env()` | 🤖 LLM | influenced by domain + constraints |
| `propose_infrastructure()` | 🤖 LLM | sizing decisions |
| `propose_sizing()` | 🤖 LLM | based on traffic estimates |
| `propose_ha_strategy()` | 🤖 LLM | RTO/RPO trade-off |
| `propose_dr_strategy()` | 🤖 LLM | judgment |
| `define_integration_pattern()` | 🤖 LLM | per-system reasoning |
| `define_api_gateway_strategy()` | 🤖 LLM | architectural choice |
| `define_event_bus()` | 🤖 LLM | conditional on async needs |
| `design_authentication()` | 🤖 LLM | OIDC vs SAML vs JWT vs MFA |
| `design_authorization()` | 🤖 LLM | RBAC vs ABAC |
| `design_encryption()` | 🤖 LLM | algorithm selection |
| `design_secrets_mgmt()` | 🤖 LLM | tool selection |
| `design_audit_logging()` | 🤖 LLM | tool selection |
| `group_frs_into_modules()` | 🤖 LLM | clustering decision |
| `define_module_responsibilities()` | 🤖 LLM | breakdown |
| `define_module_dependencies()` | 🤖 LLM | analysis |
| `mcp_drawio_create_new_diagram(xml)` | 🤖 LLM | LLM constructs XML |
| `mcp_drawio_edit_diagram(operations)` | 🤖 LLM | LLM picks operations |
| `explain_decision()` | 🤖 LLM | natural language |
| `classify_intent(message)` | 🤖 LLM | NL classification |
| `identify_change_target(message)` | 🤖 LLM | NL → field path |
| `load_requirement_analysis()` | ⚙ Graph | JSON read |
| `load_domain_profile()` | ⚙ Graph | YAML lookup |
| `inject_domain_security()` | ⚙ Graph | merge from profile |
| `mcp_drawio_export_diagram(path)` | ⚙ Graph | mechanical export |
| `validate_against_must_use()` | ⚙ Graph | set check |
| `apply_atomic_patch(field, val)` | ⚙ Graph | dict update |
| `save_diff_snapshot()` | ⚙ Graph | JSON write |
| `restore_snapshot()` | ⚙ Graph | JSON read |
| `re_validate()` | ⚙ Graph | Python checks |
| `detect_approval(msg)` | ⚙ Graph | keyword fast-path + LLM fallback (hybrid) |
| `save_solution()` | ⚙ Graph | JSON write |
| `save_chat_history()` | ⚙ Graph | append log |
| `emit_completion_event()` | ⚙ Graph | event emit |

### 3.3 BRD Workflow (42 → 28 LLM + 14 Graph)

#### LLM-callable (28) — scoped per phase

**B2 Exec & Strategic (6):** set_executive_summary, set_brd_purpose, set_brd_objectives_smart, set_brd_success_metrics, set_brd_business_case, set_brd_intended_use

**B3 Stakeholder (5):** set_brd_intended_audience, set_brd_stakeholder_matrix, set_brd_user_personas, set_brd_user_journey, set_brd_communication_plan

**B4 Scope & Process (4):** set_brd_scope_inscope, set_brd_scope_outofscope, set_brd_delivery_phases, mcp_drawio_create_bpmn_*

**B5 User Needs & Rules (4):** set_brd_user_needs, set_brd_assumptions, set_brd_business_rules, set_brd_constraints

**B6 FRs (5):** upsert_fr, add_user_story, add_use_case, add_acceptance_criteria, link_fr_to_business_rule, mcp_drawio_create_use_case_diagram, mcp_drawio_create_sequence_diagram

**B7 Interfaces + NFR (3):** set_brd_ui_notes, set_brd_software_description, update_nfr_category, mcp_drawio_create_dfd, mcp_drawio_create_state_diagram

**B8 Risk (2):** set_brd_risk_register, set_brd_swot_analysis, mcp_drawio_create_risk_matrix

#### Graph-node (14) — deterministic, no LLM

```
load_requirement_analysis        # JSON read
load_solution                    # JSON read
load_brd_template_structure      # template parser
detect_language                  # langdetect lib
init_brd                         # creates brd_state.json
set_brd_tech_stack(by_layer)     # COPY from solution.json (no LLM needed!)
set_brd_communication            # COPY from solution.json
set_brd_gap_analysis             # COMPUTE from AS-IS/TO-BE
validate_nfr_targets             # regex check for units
validate_brd                     # Python rules
validate_traceability_matrix     # set operations
validate_acceptance_criteria     # format check
check_language_consistency       # langdetect on each section
check_fr_numbering_continuity    # arithmetic
check_terminology_consistency    # corpus consistency
check_business_rule_coverage     # graph reachability
mcp_drawio_export_to_png         # mechanical export
verify_embedded_diagrams         # file existence check
render_brd_to_docx               # subprocess: docxtpl
save_to_output_dir               # file copy
upload_to_s3                     # boto3 call
```

### 3.4 WBS Workflow (60 → 38 LLM + 22 Graph)

#### LLM-callable (38) — scoped per phase

**P1 Module Decomp (4):** define_module, link_fr_to_module, define_module_dependency, set_module_complexity

**P2 Task Breakdown (8 parametric):** add_setup_task, add_module_task, add_qa_task, add_devops_task, add_uat_support_task, add_deployment_task, add_documentation_task, add_ai_ml_lifecycle_task, add_training_task, add_hypercare_task

**P3 Effort (4):** set_task_baseline_effort, score_task_complexity, mark_task_dependencies, apply_overhead (LLM picks override)

**P4 Phase Planner (1):** assemble_phase (LLM groups tasks per phase_type)

**P5 Timeline (3):** assign_task_to_sprint, define_milestone, set_sprint_config

**P6 Cost (3):** set_role_rates (LLM may adjust per project), apply_margin (LLM decides %), add_optional_service

**HITL trigger (1):** request_user_approval

#### Graph-node (22) — deterministic

```
identify_shared_components       # algorithm
load_requirement_analysis        # JSON read
load_solution                    # JSON read
load_modules                     # JSON read
lookup_domain_profile            # YAML lookup
lookup_benchmark_effort          # JSON lookup
apply_domain_multiplier          # MATH (be_md *= multiplier)
apply_seniority_factor           # MATH
apply_integration_overhead       # MATH (count * 0.3)
apply_compliance_overhead        # MATH (lookup + +)
apply_learning_curve_buffer      # MATH
apply_risk_buffer                # MATH (% of total)
finalize_task_efforts            # batch math
compute_qc_effort                # MATH (dev * pct)
compute_ba_effort                # MATH
compute_pm_effort                # MATH
compute_devops_effort            # MATH
compute_security_extra_effort    # MATH
compute_sprint_capacity_check    # arithmetic
compute_critical_path            # algorithm (Hamilton)
compute_calendar_timeline        # business-days math
validate_timeline_vs_deadline    # date compare
generate_resource_allocation_plan # batch sum
compute_module_cost              # MATH
compute_phase_cost               # MATH
compute_total_cost               # MATH
apply_currency_conversion        # MATH
add_post_golive_support          # MATH (% calc)
compute_proposal_pricing         # MATH

# All 10 P7 validators              # Python rules
validate_fr_coverage
validate_phase_coverage
validate_module_completeness
validate_effort_distribution
validate_qc_ratio
validate_timeline_feasibility
validate_cost_vs_budget
validate_team_capacity
validate_domain_mandatory_tasks
generate_validation_report

# All 8 P8 template fill            # mechanical openpyxl
load_wbs_template
set_wbs_project_metadata
clear_template_placeholder_rows
add_wbs_phase_l1_row              # ← parametric → 1 tool actually
add_wbs_subphase_l2_row           #   collapses with above
add_wbs_module_l3_row             #   collapses with above
add_wbs_task_l4_row               #   collapses with above (level enum)
set_master_data
fill_delivery_plan_modules
fill_delivery_plan_resources
fill_effort_summary_sheet
verify_template_integrity

# P9 Finalizer
generate_wbs_summary_report
apply_user_revisions
save_wbs_to_output
upload_to_s3
```

### 3.5 Proposal Workflow (28 → 18 LLM + 10 Graph)

(Detail when implementing Sprint 8)

---

## 4. Final Tool Counts

| Agent | Total | LLM-callable | Graph-node | LLM scoped per phase |
|-------|------:|-------------:|-----------:|--------------------:|
| Requirement | 22 | 14 | 8 | 14 (single agent) |
| Solution Proposal | 33 | 25 | 8 | varies S1-S11 |
| BRD Workflow | 42 | 28 | 14 | 5-8 per phase |
| WBS Workflow | 60 | 38 | 22 | 4-8 per phase |
| Proposal Workflow | 28 | 18 | 10 | 5-8 per phase |
| Shared utilities | 28 | 4 | 24 | (cross-cutting) |
| **TOTAL** | **155** | **~70** | **~85** | **5-15 per agent invocation** |

---

## 5. Token economics

### Without classification (give all 42 tools to BRD agent)

```
Per BRD agent call:
  System prompt:        2,000 tokens
  Tool descriptions:    42 × 150 = 6,300 tokens
  State context:        2,000 tokens
  ────────────────────
  Per-call overhead:    10,300 tokens
  
For 9 phases × ~3 LLM calls each = 27 calls:
  Total overhead:       ~278,000 tokens just for tool descriptions
  Cost (Sonnet):        ~$0.83 per BRD just for tool listing
```

### With classification (5-8 LLM tools per phase)

```
Per phase agent call:
  System prompt:        500 tokens (focused)
  Tool descriptions:    7 × 150 = 1,050 tokens
  State context:        2,000 tokens
  ────────────────────
  Per-call overhead:    3,550 tokens
  
For 9 phases × ~3 LLM calls each = 27 calls:
  Total overhead:       ~96,000 tokens
  Cost:                 ~$0.29 per BRD
  
Savings: $0.54 per BRD = 65% reduction
For 1000 BRDs/month: $540/month savings
```

---

## 6. Implementation pattern (per phase)

```python
# tools/brd/phase_b3_stakeholder.py

from langchain.tools import tool
from pydantic import BaseModel
from state.brd import BRDState


# ── LLM-callable tools (scoped to B3) ──

@tool
def set_brd_intended_audience(audience_table: list[dict]) -> str:
    """Add audience table. Each row: {audience, representative}.
    Example: [{"audience": "Project Sponsor", "representative": "VP Operations"}]"""
    # ... pydantic validate, write to brd_state.json
    return f"Added {len(audience_table)} audience rows"

@tool
def set_brd_stakeholder_matrix(raci: list[dict], grid: dict) -> str:
    """RACI matrix + influence × interest grid. ..."""
    ...

@tool
def set_brd_user_personas(personas: list[dict]) -> str: ...

@tool
def set_brd_user_journey(persona: str, steps: list[dict]) -> str: ...

@tool
def set_brd_communication_plan(stakeholder: str, channel: str, frequency: str) -> str: ...


# Export for graph
B3_LLM_TOOLS = [
    set_brd_intended_audience,
    set_brd_stakeholder_matrix,
    set_brd_user_personas,
    set_brd_user_journey,
    set_brd_communication_plan,
]
```

```python
# workflows/brd.py

from langchain.agents import create_agent
from langgraph.graph import StateGraph, START, END

from tools.brd.phase_b1 import load_foundation_node, init_brd_node
from tools.brd.phase_b2 import B2_LLM_TOOLS
from tools.brd.phase_b3 import B3_LLM_TOOLS
from tools.brd.phase_b9 import critic_node, render_brd_node
# ... etc


def build_brd_workflow():
    g = StateGraph(BRDState)

    # Phase B1 — Graph node only
    g.add_node("b1_foundation", load_foundation_node)

    # Phase B2 — Agent with 6 scoped tools
    g.add_node("b2_executive", create_agent(
        model=os.environ["MODEL_BRD_DRAFTER"],
        tools=B2_LLM_TOOLS,                 # only 6 tools visible to LLM
        prompt=B2_PROMPT,
        state_schema=BRDState,
    ))

    # Phase B3 — Agent with 5 scoped tools
    g.add_node("b3_stakeholder", create_agent(
        model=os.environ["MODEL_BRD_DRAFTER"],
        tools=B3_LLM_TOOLS,                 # only 5 tools
        prompt=B3_PROMPT,
        state_schema=BRDState,
    ))

    # ... B4, B5, B6, B7, B8 each with own scoped tools

    # Phase B9 — Graph nodes only (critic + render)
    g.add_node("b9_critic", critic_node)
    g.add_node("b9_render", render_brd_node)

    # Wire deterministically
    g.add_edge(START, "b1_foundation")
    g.add_edge("b1_foundation", "b2_executive")
    g.add_edge("b2_executive", "b3_stakeholder")
    g.add_edge("b3_stakeholder", "b4_scope")
    # ...
    g.add_conditional_edges(
        "b9_critic",
        lambda s: "loop_back" if s["issues"] else "render",
        {"loop_back": "b6_frs", "render": "b9_render"},
    )
    g.add_edge("b9_render", END)

    return g.compile()
```

---

## 7. Decision rules summary

```
                           ┌─────────────────────────┐
                           │  Tool needs judgment?   │
                           └────────┬────────────────┘
                          YES  ↙        ↘  NO
                              │            │
                  ┌───────────┴───┐    ┌───┴────────────┐
                  │  LLM-callable │    │  Graph node    │
                  │  @tool        │    │  Plain func    │
                  └───────────────┘    └────────────────┘

Examples:                            Examples:
- propose_architecture_type          - load_*
- extract_business_context           - validate_*
- set_brd_purpose                    - render_*
- ask_clarifying_questions           - apply_*_multiplier (math)
- mcp_drawio_create_diagram          - compute_*
- classify_intent                    - lookup_*
                                     - save_*
                                     - emit_*
```

### Heuristic check for each tool

Ask 3 questions:
1. **Is the output formula/algorithm/lookup?** → Graph
2. **Is the input structured (path/dict/enum)?** → Graph (likely)
3. **Could 2 valid LLMs disagree on the answer?** → LLM

If 2/3 say "Graph" → graph node. Otherwise LLM.

---

## 8. Migration from current design

Current implementation plan files list tools as if all are LLM-callable. **Action items:**

1. **In `tools/` module**, mark each tool with comment:
   ```python
   # ⚙ GRAPH NODE — deterministic, called by node function, not LLM
   def load_requirement_analysis(workspace_path: str) -> dict: ...
   
   # 🤖 LLM TOOL — exposed to agent
   @tool
   def set_brd_purpose(background: str, problem: str) -> str: ...
   ```

2. **In `workflows/*.py`**, build StateGraph with mix of node functions + agent nodes

3. **In `agents/brd/*.py`**, define small scoped agents (5-8 tools each)

4. **In `MASTER_REFERENCE.md` Section 5**, update tool counts to show LLM vs Graph split.

---

## 9. Open questions

1. **For HITL tools (ask_clarifying_questions, request_user_approval)** — LLM-callable (so LLM decides when to ask) or graph trigger (deterministic at fixed points)?
   - Recommendation: **LLM-callable** so agent can detect mid-task that it needs clarification. But add max_questions_per_phase=5 guard.

2. **For `mcp_drawio_create_*_diagram`** templates — let LLM construct XML or pre-write XML templates that LLM only fills in slots?
   - Recommendation: **template + slots** for common cases (BPMN, sequence). LLM constructs custom XML for novel diagrams. Saves 80% of LLM tokens for diagrams.

3. **Validators in agent loop** — should LLM see validator output (and self-correct) or just route via graph?
   - Recommendation: **graph routes** based on validator output. Don't waste tokens having LLM read full validation report.

4. **Streaming intermediate results** — every graph node emits SSE event, every LLM tool call emits SSE event?
   - Recommendation: **yes, both** — UX needs visibility.
