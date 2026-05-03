# Pre-processing Stage — Implementation Plan (v2 Architecture)

> NEW: 2 agents that run BEFORE the 3 downstream workflows (BRD/WBS/Proposal).
> Adds chat feedback loop and MCP drawio integration.
> See [architecture.drawio](architecture.drawio) Page 4 for visual flow.

---

## Why this stage

**Problem with v1**: WBS workflow had P1 Discovery + P2 Solution Architecture phases. BRD workflow had similar discovery work. Each workflow re-did the same analysis → wasted tokens, inconsistent across docs.

**v2 solution**: Move discovery + solution proposal UPSTREAM into 2 dedicated agents that run ONCE. All 3 workflows consume their output (DRY).

**Plus the user-requested feature**: Solution Agent has chat feedback loop with MCP drawio — user can iteratively refine architecture diagrams via natural language.

---

## Stage architecture

```
Input files
    ↓
[Requirement Agent] ─── extracts + analyzes ─── HITL clarifying Qs
    ↓ requirement_analysis.json
[Solution Proposal Agent] ─── proposes + draws diagrams (MCP drawio)
    ↑↓ chat feedback loop with user (iterate until "OK approve")
    ↓ solution.json + diagrams/*.drawio
    ↓
[3 downstream workflows] (BRD / WBS / Proposal — independent, parallel-capable)
```

---

## Agent 1: Requirement Agent

### Role
Extract structured information from raw requirement files. Ask user for missing critical info.

### Model
`anthropic:claude-sonnet-4-6` · temp=0.0 (deterministic extraction)

### State (`RequirementState`)
```python
class RequirementState(MainState):
    raw_files: list[FileRef]                     # uploaded inputs
    business_context: str                        # background, problem statement
    objectives: list[str]
    stakeholders: list[Stakeholder]              # {name, role, organization}
    raw_frs: list[RawFR]                         # un-structured FR statements
    raw_nfrs: dict[str, list[NFRStatement]]
    constraints: Constraints                     # budget, timeline, tech, compliance
    integrations: list[Integration]
    domain: str                                  # banking | insurance | ...
    industry: str                                # sub-industry detail
    clarifications: list[QnA]                   # HITL Q&A history
    analysis_complete: bool
```

### Tools (15)

```python
# File reading
read_pdf(path)
read_docx(path)
read_pptx(path)
read_xlsx(path)
read_md(path)
read_image(path)        # vision LLM for diagrams in images

# Extraction (Pydantic-validated outputs)
extract_business_context()        # → background, objectives
extract_stakeholders()            # → list[Stakeholder]
extract_raw_frs()                 # → list[RawFR]
extract_raw_nfrs()                # → dict by category
extract_constraints()             # → Constraints
extract_integrations()            # → list[Integration]
identify_domain()                 # → maps to one of 26 profiles

# HITL
ask_clarifying_questions(questions: list[str])  # max 5, batched
                                  # streams to user, awaits answers
                                  # writes to clarifications[]

# Persistence
save_requirement_analysis()       # → requirement_analysis.json
```

### Workflow
1. List input files
2. Read each file (parallel where possible)
3. Extract business context, stakeholders, raw FRs, NFRs, constraints, integrations
4. Identify domain (lookup in 26 profiles)
5. Check for gaps:
   - No domain → ask
   - No team size → ask
   - No deadline → ask
   - No budget signal → ask
   - No deploy env → ask
6. If gaps: HITL via `ask_clarifying_questions` (max 5 questions, batched)
7. After answers: re-extract / fill gaps
8. Save `requirement_analysis.json`

### HITL example (Vietnamese)
```
Agent: "Để tôi clarify một số điểm trước khi propose solution:
1. Khách hàng thuộc ngành gì? (banking / insurance / e-commerce / ...)
2. Team composition (BE / FE / QC / BA / PM)?
3. Target delivery date?
4. Có yêu cầu compliance đặc biệt? (PCI-DSS / HIPAA / ISO 27001 / ...)
5. Deploy environment? (cloud / on-prem / hybrid)"
```

---

## Agent 2: Solution Proposal Agent

### Role
Propose technical solution with diagrams. Iterate with user via chat until approved.

### Model
`anthropic:claude-sonnet-4-6` · temp=0.3 (some creativity for alternatives)

### State (`SolutionState`)
```python
class SolutionState(MainState):
    requirement_ref: str                          # path to requirement_analysis.json
    architecture_type: str                        # mono | micro | serverless | hybrid
    architecture_rationale: str
    alternatives_considered: list[Alternative]
    tech_stack: dict[str, list[Tech]]             # layer → technologies
    deployment: Deployment                        # cloud/on-prem/hybrid + sizing + HA
    integrations_design: list[IntegrationDesign]
    modules: list[ModuleSpec]                     # high-level decomposition
    security_arch: SecurityArch
    diagrams: list[DiagramRef]                    # paths to .drawio files
    chat_iterations: int                          # feedback loop counter
    chat_diff_history: list[Diff]                 # rollback support
    solution_approved: bool                       # set when user says "OK"
```

### Tools (20)

```python
# Solution proposal
propose_architecture_type(rationale, alternatives)   # mono/micro/serverless/hybrid
propose_tech_stack(layer, techs, version, why)       # per layer
propose_deployment(env, provider, sizing, ha, dr)
define_integration_pattern(system, pattern, protocol)
design_security_architecture(auth, encryption, secrets, audit)
                                                      # uses domain rules
decompose_into_modules(modules: list)                # high-level modules
evaluate_alternatives(option_a, option_b, option_c)  # 2-3 alternatives + recommend

# Diagram drawing (via MCP drawio host)
mcp_drawio_create_new_diagram(xml)        # initial diagram
mcp_drawio_edit_diagram(operations)       # add/update/delete cells
mcp_drawio_get_diagram()                  # fetch current (incl. user edits)
mcp_drawio_export_diagram(path, format)   # png/svg/drawio

# Feedback loop
ask_user_feedback(diagram_path, summary)  # streams diagram preview + asks
apply_user_revision(field, new_value)     # atomic patch to solution.json
                                           # also updates diagram via MCP
detect_approval(user_message)             # detects "OK", "approve", "đồng ý"
                                           # returns bool
save_diff_snapshot()                      # for rollback support

# Persistence
save_solution()                            # → solution.json (only when approved)
save_chat_history()                        # → chat_history.json
```

### Workflow
1. Read `requirement_analysis.json`
2. **Initial proposal**:
   a. Propose architecture type + 2-3 alternatives + rationale
   b. Propose tech stack (per layer)
   c. Design deployment + security
   d. Draw `system_context.drawio` via MCP
   e. Draw `component.drawio` via MCP
   f. Draw `deployment.drawio` via MCP
   g. Send diagrams + summary to user via chat (SSE)
3. **Feedback loop** (until approved):
   a. Receive user message via /chat
   b. Detect intent: refine / question / approve
   c. If refine: apply atomic patch to solution.json + edit diagram via MCP
   d. If question: explain trade-off
   e. If approve: break loop
   f. Increment `chat_iterations`, save diff snapshot
4. Save final `solution.json` + diagrams
5. Unlock downstream workflows (set flag in session)

### Chat feedback loop example (Vietnamese)
```
Iteration 1:
  Agent: "Proposed: Microservices + K8s + PostgreSQL + Redis + Kafka.
          Rationale: scale horizontally, fault isolation. Trade-off: ops complexity ↑.
          [system_context.drawio rendered]
          [component.drawio rendered showing 5 services]
          Bạn review và cho feedback nhé."
  User:  "Đổi PostgreSQL sang MongoDB, hệ thống chính là content-heavy"

Iteration 2:
  Agent: [edit_diagram: replace PostgreSQL with MongoDB]
         [solution.json: tech_stack.db = "MongoDB"]
         "Đã đổi. Lưu ý: write throughput +30%, nhưng transactions yếu hơn.
          Cho các operations cần ACID, có thể dùng event sourcing với Kafka.
          OK với approach này không?"
  User:  "OK approve"

  [detect_approval = TRUE]
  [save_solution(), save_chat_history()]
  [unlock BRD, WBS, Proposal workflows]
```

### MCP drawio integration

**Setup**: Solution Agent has access to MCP drawio session via the `mcp_host` infrastructure component. Each session reuses the same drawio MCP session.

**Workflow**:
1. Agent calls `mcp_drawio_create_new_diagram(xml)` for initial system context
2. Subsequent calls `mcp_drawio_edit_diagram(operations)` for refinements
3. After each edit, call `mcp_drawio_export_diagram(path)` to save .png + .drawio
4. Stream the .png to UI via SSE for live preview

**Permissions**:
- Solution Agent CAN: create / edit / export diagrams
- Solution Agent CANNOT: delete other sessions' diagrams (path-scoped)

**Diagram types produced**:
- `system_context.drawio` — high-level: external systems + this system
- `component.drawio` — internal modules + dependencies
- `sequence_*.drawio` — key user flows (1-3 sequences)
- `deployment.drawio` — infra topology

---

## Cross-cutting: HITL Manager + Chat Manager

### State changes propagated via SSE
```
event: token        data: {"content": "..."}
event: diagram      data: {"path": ".../system_context.png", "version": 3}
event: tool_call    data: {"tool": "mcp_drawio_edit_diagram", "args": {...}}
event: hitl         data: {"reason": "clarifying_questions", "questions": [...]}
event: approval     data: {"detected": true}
event: done         data: {"foundation_ready": true}
```

### Approval detection logic
```python
APPROVAL_PHRASES = [
    "ok", "approve", "approved", "đồng ý", "ok đi", "duyệt",
    "ok approve", "final", "ok rồi", "ok then", "lgtm", "ship it"
]

def detect_approval(message: str) -> bool:
    msg = message.lower().strip()
    if any(phrase in msg for phrase in APPROVAL_PHRASES):
        # Confirm with structured output
        return True
    return False
```

But better: use LLM-as-judge with a small classifier (can be the same agent with structured output schema):
```python
class ApprovalDetection(BaseModel):
    intent: Literal["approve", "refine", "question", "rollback"]
    confidence: float
    reasoning: str
```

---

## Implementation tasks (Sprint S0.5 — before downstream sprints)

| # | Task | Effort |
|---|------|--------|
| 1 | `state/requirement.py` — RequirementState schema | 0.5d |
| 2 | `state/solution.py` — SolutionState schema | 0.5d |
| 3 | `tools/requirement_ops.py` — 15 extraction tools | 1.5d |
| 4 | `tools/solution_ops.py` — 7 proposal tools | 1.5d |
| 5 | `tools/mcp_drawio_ops.py` — wrap 4 MCP drawio tools | 1d |
| 6 | `tools/feedback_ops.py` — chat loop tools (ask, apply, detect, save) | 1d |
| 7 | `agents/requirement.py` — Requirement Agent | 0.5d |
| 8 | `agents/solution_proposal.py` — Solution Agent | 1d |
| 9 | `infra/mcp_host.py` — MCP drawio session manager | 1d |
| 10 | `api/sse.py` — SSE streaming with diagram events | 1d |
| 11 | E2E test: upload PDF → analyze → chat refine → approve | 1d |
| **Total** | | **10.5d (~2 weeks for 1 engineer)** |

---

## API contract

### POST /sessions/{id}/analyze
Trigger pre-processing. Async, streams progress via SSE.
```json
Request: {}
Response (SSE):
  event: progress  data: {"step": "intake", "files": 3}
  event: token     data: {"content": "Đang đọc file 1..."}
  event: hitl      data: {"questions": ["Domain?", "Team size?"]}
```

### POST /sessions/{id}/chat
Send user message during refinement loop.
```json
Request: {"message": "đổi PostgreSQL sang MongoDB"}
Response (SSE):
  event: token       data: {"content": "Đã đổi sang MongoDB..."}
  event: tool_call   data: {"tool": "mcp_drawio_edit_diagram"}
  event: diagram     data: {"path": "...", "version": 3}
  event: token       data: {"content": "...transactions yếu hơn..."}
```

### GET /sessions/{id}/diagram
Stream current diagram (long-poll or websocket).
```
GET /sessions/{id}/diagram?type=system_context&format=png
→ image/png
```

### GET /sessions/{id}/foundation
Get the approved foundation (after pre-processing complete).
```json
Response: {
  "status": "approved",
  "requirement_analysis": {...},
  "solution": {...},
  "diagrams": [
    {"name": "system_context", "drawio": "...", "png": "..."},
    ...
  ],
  "chat_iterations": 5,
  "approved_at": "2026-04-26T..."
}
```

### POST /sessions/{id}/run (after foundation approved)
Trigger downstream workflow.
```json
Request: {"workflow": "wbs"}
Response (SSE): stream of WBS workflow execution
```

---

## Why this is better than v1

| Concern | v1 (per-workflow discovery) | v2 (shared pre-processing) |
|---------|----------------------------|---------------------------|
| Discovery work | Repeated 3× (BRD/WBS/Proposal) | Done ONCE upstream |
| Token cost | High (3× redundancy) | Low (shared output) |
| Inconsistency | Risk: BRD says X, WBS says Y | Single source of truth |
| User refinement | Mixed in each workflow | Concentrated in Solution Agent |
| Diagrams | Each workflow draws own | Drawn ONCE, REUSED in Proposal |
| Skip ability | Hard (workflows interlinked) | User can skip BRD/WBS/Proposal individually |
| Iteration UX | Confusing (which workflow's discovery?) | Clear: refine in chat, then run workflows |

---

## Open design questions

1. **Approval detection**: keyword vs LLM classifier? Recommendation: hybrid (keyword fast-path + LLM fallback for ambiguous cases).
2. **Rollback granularity**: per-iteration or per-tool-call? Recommendation: per-iteration (cleaner UX).
3. **MCP drawio session lifetime**: per-session or global? Recommendation: per-session (isolation, but higher resource).
4. **Diagram preview format**: PNG (universal) or SVG (editable)? Recommendation: PNG for preview + SVG + .drawio for download.
5. **Maximum iterations before forced approval**: 10? 20? Recommendation: 15, then escalate to engineer review.

---

## Updates to other plans

- [IMPLEMENTATION_PLAN_FULL.md](IMPLEMENTATION_PLAN_FULL.md) — WBS workflow now starts at P1 Module Decomp (was P3). 9 phases, not 11. Same total tools.
- [REVIEW_NOTES_LANGCHAIN_PAPER2ANY.md](REVIEW_NOTES_LANGCHAIN_PAPER2ANY.md) — confirms 3 INDEPENDENT workflows decision. Pre-processing fits perfectly with this model.
