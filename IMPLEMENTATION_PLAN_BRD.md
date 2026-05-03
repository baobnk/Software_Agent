# BRD Workflow — Implementation Plan

> 9 phases × 70 atomic tools, BA-enhanced (SWOT, BPMN, RACI, personas, traceability), with MCP drawio diagram generation (XML → PNG → embed in .docx).
> See [architecture.drawio](architecture.drawio) Page 7 for visual flow.

---

## Why BA-enhanced

Standard BRD generation is template-fill. **BA-enhanced** means agent applies senior business analyst skills:
- SMART objectives (not vague goals)
- Stakeholder analysis with RACI matrix
- AS-IS / TO-BE process modeling (BPMN)
- Personas + journey mapping
- User stories (As-X-I-want-So-that) + use cases (actors+flows) + acceptance criteria (Given-When-Then BDD)
- Risk register with probability × impact matrix
- SWOT analysis
- 100% requirements traceability matrix (FR ↔ BR ↔ AC ↔ Test)

**Reference:** [VoltAgent business-analyst.md](https://github.com/VoltAgent/awesome-claude-code-subagents/blob/main/categories/08-business-product/business-analyst.md)

## Why MCP drawio integration

BRDs need diagrams (BPMN process, sequence, use case, DFD, state). Agent draws these as XML via MCP drawio, exports to PNG, embeds in .docx via docxtpl `{{ image() }}` syntax.

User can:
- See diagrams during chat
- Edit diagrams via chat ("đổi swimlane Customer thành User")
- Edit diagrams manually in browser → agent syncs to BRD

---

## 9-Phase Pipeline

```
Foundation banner: read requirement_analysis.json + solution.json + diagrams/
    ↓
B1 FOUNDATION LOAD          (5 tools)
    ↓
B2 EXEC & STRATEGIC         (6 tools)  ★ BA: business case
    ↓
B3 STAKEHOLDER ANALYSIS     (5 tools)  ★ BA: RACI, personas, journey
    ↓
B4 SCOPE & PROCESS          (10 tools) ★ BA + drawio: BPMN AS-IS/TO-BE, value stream
    ↓
B5 USER NEEDS & RULES       (4 tools)  ★ BA: elicitation, business rules
    ↓
B6 FUNCTIONAL REQUIREMENTS  (9 tools)  ★ BA: user stories + AC + drawio: use case + sequence
    ↓
[HITL Gate: review FRs before NFR]
    ↓
B7 INTERFACES + NFR + FEATURES (14 tools) ★ drawio: DFD, state diagram
    ↓
B8 RISK & APPENDIX          (6 tools)  ★ BA: SWOT, risk matrix
    ↓
B9 CRITIC + REFINER + RENDER (11 tools)
    ↓ if FAIL: loop back to B5/B6/B7 (max 3 retries)
    ↓ PASS
✅ DELIVERABLE: OUTPUT_DIR/{project}/BRD/{name}_BRD_v0_1_0.docx
```

---

## Phase B1 — Foundation Load (5 tools)

| # | Tool | Purpose |
|---|------|---------|
| 1.1 | `load_requirement_analysis()` | reads workspace/requirement_analysis.json |
| 1.2 | `load_solution()` | reads workspace/solution.json + lists diagram refs |
| 1.3 | `load_brd_template_structure()` | reads BnK_BRD_Template_v1.0.docx outline |
| 1.4 | `detect_language()` | vi or en (mirror user's input language) |
| 1.5 | `init_brd(name, code, author, version, language)` | creates brd_state.json with metadata |

---

## Phase B2 — Executive & Strategic (6 tools, BA-enhanced)

| # | Tool | Purpose |
|---|------|---------|
| 2.1 | `set_executive_summary()` | 1-page summary for sponsors |
| 2.2 | `set_brd_purpose(background, problem)` | 1. Bối cảnh + problem statement |
| 2.3 | `set_brd_objectives_smart(objectives[])` | SMART goals (Specific/Measurable/Achievable/Relevant/Time-bound) |
| 2.4 | `set_brd_success_metrics(kpis[])` | KPI framework: target + baseline + measurement method |
| 2.5 | `set_brd_business_case(roi, cost_benefit)` | ROI estimation, cost-benefit analysis |
| 2.6 | `set_brd_intended_use(use_summary)` | how the BRD will be used downstream |

**Example output (SMART objective):**
```
NOT: "Tăng hiệu quả xử lý hồ sơ"
YES: "Giảm thời gian xử lý hồ sơ từ 30 phút xuống ≤ 5 phút (Specific) cho 100% claim_type=MEDICAL_CARE (Measurable),
     bằng cách tự động phân loại + kiểm tra đầy đủ chứng từ (Achievable),
     đáp ứng SLA của MBAL khách hàng VIP (Relevant),
     hoàn thành trong Phase 1 (Time-bound: trước 30/9/2026)."
```

---

## Phase B3 — Stakeholder Analysis (5 tools, BA Discovery)

| # | Tool | Purpose |
|---|------|---------|
| 3.1 | `set_brd_intended_audience(audience_table)` | audience + representative table |
| 3.2 | `set_brd_stakeholder_matrix(stakeholders, raci, grid)` | RACI matrix + influence × interest grid |
| 3.3 | `set_brd_user_personas(personas[])` | persona cards: name, role, goals, pain_points, frequency, tech_level |
| 3.4 | `set_brd_user_journey(persona, journey_steps)` | journey map per primary persona |
| 3.5 | `set_brd_communication_plan(stakeholder, channel, frequency)` | who needs what info when |

**RACI matrix example:**
```
Activity         | Sponsor | PM    | BA  | Dev | QC   | User
Approve BRD      | A       | R     | C   | I   | I    | C
Write FRs        | I       | C     | R   | C   | I    | C
UAT execution    | I       | C     | C   | C   | R    | A
Sign-off go-live | A       | R     | I   | I   | C    | C
(R=Responsible, A=Accountable, C=Consulted, I=Informed)
```

---

## Phase B4 — Scope & Process Analysis (10 tools, BA + MCP drawio)

| # | Tool | Purpose |
|---|------|---------|
| 4.1 | `set_brd_scope_inscope(items[])` | what IS in this delivery |
| 4.2 | `set_brd_scope_outofscope(items[])` | what is explicitly NOT |
| 4.3 | `set_brd_delivery_phases(phases[])` | Phase 1, 1.5, 2 ... (MBAL pattern) |
| 4.4 | `mcp_drawio_create_bpmn_as_is(swimlanes, activities)` | Current state BPMN diagram |
| 4.5 | `mcp_drawio_create_bpmn_to_be(swimlanes, activities)` | Future state BPMN diagram |
| 4.6 | `mcp_drawio_create_value_stream(steps, metrics)` | Value stream map (waste, bottlenecks) |
| 4.7 | `mcp_drawio_export_to_png(diagram_path)` | export XML → PNG for embedding |
| 4.8 | `set_brd_gap_analysis(as_is_ref, to_be_ref, deltas)` | AS-IS vs TO-BE delta table |
| 4.9 | `embed_diagram_ref(brd_section, png_path, caption)` | link PNG into brd_state.json |
| 4.10 | `set_brd_value_stream_summary(text)` | text companion to value stream diagram |

---

## Phase B5 — User Needs & Business Rules (4 tools)

| # | Tool | Purpose |
|---|------|---------|
| 5.1 | `set_brd_user_needs(needs[])` | Primary/Secondary/Tertiary user needs |
| 5.2 | `set_brd_assumptions(assumptions[])` | each: assumption + dependency + mitigation |
| 5.3 | `set_brd_business_rules(rules[])` | BR01..BRn — categories: Validation/Calculation/Workflow/Authorization/Data |
| 5.4 | `set_brd_constraints(tech, budget, regulatory, organizational)` | hard constraints |

**Business rule format:**
```yaml
- id: BR01
  category: Validation
  description: "Hồ sơ bồi thường phải có đầy đủ 5 chứng từ bắt buộc theo claim_type"
  source: "MBAL BRD section 4.3.2"
  priority: High
- id: BR02
  category: Workflow
  description: "Khi chứng từ thiếu, IDP trả về cảnh báo MISSING_DOC, không reject"
  source: "MBAL workshop ngày 15/8"
  priority: Critical
```

---

## Phase B6 — Functional Requirements + Diagrams (9 tools, BA-enhanced)

**Called per FR (10-30 FRs typical).** Each FR is incremental — uses `section_id` UUID.

### Core FR tools (5)

| # | Tool | Purpose |
|---|------|---------|
| 6.1 | `upsert_fr(fr_id, section_id, ...)` | idempotent FR upsert with all fields |
| 6.2 | `add_user_story(fr_id, story)` | "As <persona>, I want <goal>, so that <benefit>" |
| 6.3 | `add_use_case(fr_id, uc)` | actor, trigger, main_flow, alt_flows, exception_flows, pre/post |
| 6.4 | `add_acceptance_criteria(fr_id, ac)` | BDD: Given-When-Then |
| 6.5 | `link_fr_to_business_rule(fr_id, rule_id)` | traceability matrix entry |

### Diagram tools per FR (4 — MCP drawio)

| # | Tool | When to use |
|---|------|-------------|
| 6.6 | `mcp_drawio_create_use_case_diagram(group, actors, ucs)` | per FR group (5-10 FRs) |
| 6.7 | `mcp_drawio_create_sequence_diagram(flow, parts, msgs)` | per key user flow (1-3 per FR) |
| 6.8 | `mcp_drawio_export_to_png(diagram_path)` | export each diagram |
| 6.9 | `embed_diagram_in_fr(fr_id, png_path, caption)` | link PNG to FR section |

**FR with all BA-enhancements example (Vietnamese):**
```yaml
id: FR3
section_id: a1b2c3d4-...  # UUID for incremental edits
name: "Phân loại tự động bộ chứng từ"
priority: Critical
raised_by: "MBAL Claims Team"
short_description: "IDP nhận tài liệu, phân loại theo claim_type"
description: |
  Hệ thống IDP nhận bộ chứng từ từ DP qua REST API.
  Sử dụng OCR + LLM classifier để phân loại từng chứng từ.
  Trả kết quả về DP với document_type + confidence score.
  Edge cases: chứng từ không xác định → return UNKNOWN với confidence < 0.5.

interface_notes: |
  POST /api/v1/idp/classify
  Body: { documents: [base64], claim_type: "MEDICAL_CARE" }
  Response: { results: [{doc_id, type, confidence}], warnings: [] }

data_fields:
  - {name: doc_id, type: Varchar, char: 36, required: true, note: "UUID"}
  - {name: claim_type, type: Dropdown, required: true, note: "Enum"}
  - {name: confidence, type: Decimal, required: true, note: "0.0-1.0"}

source_req_ids: ["MBAL-REQ-12", "MBAL-REQ-15"]

# BA-enhancements
user_story:
  as: "Claims Officer"
  i_want: "tự động phân loại chứng từ"
  so_that: "tiết kiệm 25 phút thao tác thủ công mỗi hồ sơ"

use_case:
  actor: "Claims Officer"
  trigger: "Officer upload bộ chứng từ vào DP"
  main_flow:
    - "DP gửi documents qua REST API tới IDP"
    - "IDP OCR + classify từng tài liệu"
    - "IDP trả response với document_type + confidence"
    - "DP hiển thị kết quả + cho phép manual override"
  alternate_flows:
    - "Confidence < 0.5 → DP tô vàng + yêu cầu Officer xác nhận"
  exception_flows:
    - "IDP timeout → DP fallback sang manual classification"
  preconditions: ["User đã đăng nhập", "claim_type đã chọn"]
  postconditions: ["Mỗi document có classification + confidence"]

acceptance_criteria:
  - id: AC-FR3-1
    given: "Bộ chứng từ MEDICAL_CARE có 5 documents valid"
    when: "Officer click 'Classify' button"
    then: "100% documents được classify với confidence ≥ 0.5 trong ≤ 30s"
  - id: AC-FR3-2
    given: "Document scan mờ"
    when: "IDP process"
    then: "Confidence < 0.5 và DP show warning UNCLEAR_SCAN"

linked_business_rules: ["BR01", "BR02"]

diagrams:
  - {type: use_case, path: "diagrams/brd/uc_FR3.png"}
  - {type: sequence, path: "diagrams/brd/seq_FR3_classify_flow.png"}
```

---

## Phase B7 — Interfaces + NFR + System Features (14 tools)

| # | Tool | Purpose |
|---|------|---------|
| 7.1 | `set_brd_ui_notes(wireframe_refs)` | UI/UX guidelines, links to wireframes |
| 7.2 | `set_brd_hardware(specs)` | for IoT/edge projects |
| 7.3 | `set_brd_software_description(arch_summary)` | reads solution.json |
| 7.4 | `set_brd_tech_stack(by_layer)` | reads solution.json tech_stack |
| 7.5 | `set_brd_communication(integration_summary)` | reads solution.json integrations |
| 7.6 | `set_brd_system_features(features_by_category)` | high-level system features |
| 7.7 | `update_nfr_category("performance", rows)` | response time, throughput, ... |
| 7.8 | `update_nfr_category("safety", rows)` | for safety-critical systems |
| 7.9 | `update_nfr_category("security", rows)` | auth, encryption, audit |
| 7.10 | `update_nfr_category("quality", rows)` | code coverage, uptime, MTTR |
| 7.11 | `validate_nfr_targets()` | ensure every NFR row has measurable unit |
| 7.12 | `mcp_drawio_create_dfd(level, entities, processes, stores)` | data flow diagram L0/L1 |
| 7.13 | `mcp_drawio_create_state_diagram(entity, transitions)` | for stateful entities (Order, Claim, ...) |
| 7.14 | `update_nfr_with_units(category, row_id, target_with_unit)` | enforce unit on NFR target |

**NFR target rules (every row MUST):**
- ✓ Have measurable unit (ms, %, MB, fps, req/s, h, ...)
- ✓ Have priority (Must / Should / Could)
- ✓ Have measurement method (load test, code coverage tool, ...)

```yaml
performance:
  - aspect: "API Response Time"
    requirement: "All API calls complete within threshold"
    target: "p95 ≤ 500ms (read), p95 ≤ 2000ms (write)"   # ← unit + percentile
    priority: Must
    measurement: "Load test with k6, 1000 concurrent users"

  - aspect: "Document Classification Throughput"
    requirement: "IDP can classify N documents per minute"
    target: "≥ 100 docs/min single instance, scales linearly"
    priority: Should
    measurement: "Stress test with synthetic documents"

security:
  - aspect: "Data at rest encryption"
    requirement: "All sensitive data encrypted in DB"
    target: "AES-256 (FIPS 140-2 Level 3)"
    priority: Must
    measurement: "Pen test + DB inspection"
```

---

## Phase B8 — Risk & Appendix (6 tools, BA Risk Management)

| # | Tool | Purpose |
|---|------|---------|
| 8.1 | `set_brd_risk_register(risks[])` | risk matrix: probability × impact + mitigation + owner |
| 8.2 | `set_brd_swot_analysis(strengths, weaknesses, opportunities, threats)` | SWOT |
| 8.3 | `mcp_drawio_create_risk_matrix(risks)` | visual risk heat map (5×5 matrix) |
| 8.4 | `add_analysis_model_ref(name, drawio_path)` | links to upstream solution diagrams (REUSED) |
| 8.5 | `add_known_issue(id, description, status)` | open items, blockers |
| 8.6 | `finalize_version_history(versions[])` | document version log |

**Risk register format:**
```yaml
- id: R01
  category: Technical
  description: "OCR accuracy thấp với chứng từ scan chất lượng kém"
  probability: Medium
  impact: High                       # → "Significant" zone in heat map
  mitigation: "Train OCR model với 1000+ ảnh chất lượng đa dạng"
  owner: "AI Engineer"
  status: Open

- id: R02
  category: Resource
  description: "Team BE thiếu kinh nghiệm với LLM tuning"
  probability: High
  impact: Medium
  mitigation: "1-week training session + pair programming với senior"
  owner: "Tech Lead"
  status: Mitigating
```

---

## Phase B9 — Critic + Refiner + Render (11 tools)

### Critic (deterministic Python checks, 3 tools)

| # | Tool | Codes |
|---|------|-------|
| 9.1 | `validate_brd()` | FR_DUPLICATE_ID, NFR_NO_TARGET, BRD_MISSING_PURPOSE, FR_EMPTY_DESCRIPTION |
| 9.2 | `validate_traceability_matrix()` | TRACE_FR_NO_BR, TRACE_FR_NO_AC, TRACE_AC_NO_TEST |
| 9.3 | `validate_acceptance_criteria()` | AC_MISSING, AC_NOT_TESTABLE, AC_NO_GIVEN_WHEN_THEN |

### Refiner (final polish, 4 tools)

| # | Tool | Check |
|---|------|-------|
| 9.4 | `check_language_consistency()` | no random English in VI text |
| 9.5 | `check_fr_numbering_continuity()` | FR1, FR2, ... contiguous |
| 9.6 | `check_terminology_consistency()` | same term used consistently |
| 9.7 | `check_business_rule_coverage()` | every BR referenced by ≥1 FR |

### Render (4 tools)

| # | Tool | Purpose |
|---|------|---------|
| 9.8 | `render_brd_to_docx(workspace_path)` | subprocess: docxtpl with embedded PNGs |
| 9.9 | `verify_embedded_diagrams()` | sanity check: all PNG paths exist + embedded |
| 9.10 | `save_to_output_dir()` | OUTPUT_DIR/{project}/BRD/{name}_BRD_v0_1_0.docx |
| 9.11 | `upload_to_s3()` | optional, if ENABLE_S3_UPLOAD=true |

### Critic loop logic

```python
revision_count = 0
while True:
    issues = validate_brd() + validate_traceability_matrix() + validate_acceptance_criteria()
    if not issues:
        break
    revision_count += 1
    if revision_count > 3:
        emit_event("ESCALATE_USER", issues)
        break
    # Route back to relevant phase based on issue codes
    if any(i.code.startswith("FR_") for i in issues): goto_phase = "B6"
    elif any(i.code.startswith("NFR_") for i in issues): goto_phase = "B7"
    elif any(i.code.startswith("BRD_") for i in issues): goto_phase = "B2"
    elif any(i.code.startswith("TRACE_") for i in issues): goto_phase = "B5_or_B6"
    yield goto_phase
```

---

## MCP drawio Diagram Generation

### XML → PNG → embed in .docx flow

```python
# 1. Agent constructs drawio XML
xml = render_bpmn_xml(swimlanes=[...], activities=[...])

# 2. Call MCP drawio
mcp__drawio__create_new_diagram(xml=xml)

# 3. Export to PNG
mcp__drawio__export_diagram(path="workspace/diagrams/brd/bpmn_to_be.png")

# 4. Embed in BRD via docxtpl
# In template:  {{ image('diagrams/brd/bpmn_to_be.png', width=Mm(160)) }}
# Renderer expands this during render_brd_to_docx
```

### Diagram types per phase

| Phase | Diagram Type | Quantity | Purpose |
|-------|-------------|---------:|---------|
| B4 | BPMN AS-IS | 1 | Current manual workflow |
| B4 | BPMN TO-BE | 1 | Future automated workflow |
| B4 | Value stream map | 1 | Waste + bottleneck identification |
| B6 | Use case (UML) | 1 per FR group | Actors + use cases |
| B6 | Sequence (UML) | 1-3 per FR | Time-ordered messages |
| B7 | DFD L0 | 1 | System context (data sources/sinks) |
| B7 | DFD L1 | 1 | System detail |
| B7 | State diagram (UML) | 1 per stateful entity | Transitions |
| B8 | Risk heat map | 1 | Probability × impact matrix |

**Total diagrams per BRD:** ~10-20 (depending on FR count + entities)

### Reused from upstream Solution Agent

These are NOT redrawn — linked via `add_analysis_model_ref`:
- `system_context.drawio` (from S8)
- `component.drawio` (from S8)
- `deployment.drawio` (from S8)

---

## Open Questions for User

1. **Diagram fallback strategy** — if MCP drawio unavailable, use Mermaid markdown (puppeteer-rendered) or skip diagrams + warn?
2. **Diagram size limits** — max nodes per diagram before splitting? Recommend 50.
3. **PNG resolution** — 1920×1080 (high quality, big .docx) or 1280×720 (lighter)? Recommend 1920 with PNG compression.
4. **Diagram editing UX** — user can edit diagrams via chat ("đổi swimlane Customer thành User") OR manually in browser? Recommend both: chat command for simple, browser for complex.
5. **HITL gates count** — currently 1 gate (after B6). Add another after B4 (process diagrams)? Tradeoff: more user control vs more interruptions.

---

## Implementation Tasks

| # | Task | Files | Effort |
|---|------|-------|--------|
| 1 | `state/brd.py` — BRDState extends MainState | state/brd.py | 0.5d |
| 2 | `tools/brd_ops.py` — 30 BRD section tools | tools/brd_ops.py | 2d |
| 3 | `tools/brd_diagram_ops.py` — 13 MCP drawio diagram tools | tools/brd_diagram_ops.py | 2d |
| 4 | `tools/brd_validators.py` — 7 critic + refiner tools | tools/brd_validators.py | 1d |
| 5 | `tools/brd_renderer.py` — docxtpl with PNG embedding | tools/brd_renderer.py | 1d |
| 6 | `agents/brd/*.py` — 9 phase subagents | agents/brd/ | 1.5d |
| 7 | `workflows/brd.py` — workflow factory + StateGraph | workflows/brd.py | 1d |
| 8 | E2E test: requirement+solution → BRD with diagrams | tests/test_e2e_brd.py | 1d |
| **Total** | | | **10d (~2 weeks for 1 engineer)** |

---

## Why this design is BA-grade

| Standard BRD agent | This BRD agent |
|-------------------|---------------|
| Templated FR list | Stakeholder analysis + RACI + personas + journey |
| Generic objectives | SMART objectives + KPI framework + ROI |
| Scope as bullets | Scope + AS-IS/TO-BE BPMN + gap analysis + value stream |
| FR description only | FR + user story + use case + acceptance criteria + diagrams |
| NFR as text | NFR with quantified targets + units + measurement method |
| No traceability | 100% FR↔BR↔AC traceability matrix |
| No risk section | Risk register + SWOT + risk heat map |
| Generic critic | Validates traceability + AC completeness + numbering |

This produces a BRD that passes review by a senior BA at a Big-4 consulting firm — not just "looks like a BRD" but actually IS a BRD.
