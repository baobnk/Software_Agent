# SKILL: Technical Design Diagram Generation

> **When to load:** Solution design phase — after `save_technical_design_md` succeeds.
> **Loaded via:** `skills=["/skills/diagram_drawing/"]`

---

## Purpose

Generate 3 architecture diagrams from `technical_design.md` using `generate_technical_design_diagram`. Each diagram is saved as **two files**:
- `workspace/diagrams/{type}.drawio` — editable source
- `workspace/diagrams/{type}.png` — export for preview and download

**Do NOT embed diagram XML or image references inside `technical_design.md`.** Diagrams are standalone deliverables.

---

## When to Generate

After `save_technical_design_md(project_name=...)` returns successfully, call `confirm_diagram_generation()` then generate the approved types:

```
save_technical_design_md(project_name="PROJECT_NAME")
    ↓
confirm_diagram_generation()    ← HITL: user selects which diagrams to generate
    ↓ returns list of approved types
generate_technical_design_diagram(diagram_type="system_architecture", project_name="PROJECT_NAME")
    ↓
generate_technical_design_diagram(diagram_type="component",           project_name="PROJECT_NAME")
    ↓
generate_technical_design_diagram(diagram_type="deployment",          project_name="PROJECT_NAME")
    ↓
Report all output paths to user
```

---

## Diagram Types

| Type | Sections used | What it shows |
|------|--------------|---------------|
| `system_architecture` | §3 System Architecture, §4 Modules, §6 Integration | C4 L1: top-level components + data flow + external systems |
| `component` | §4 Module Decomposition, §3 Architecture | C4 L2: internal modules per tier + dependencies |
| `deployment` | §5 Tech Stack, §6 Integration, §3 Architecture | Infrastructure tiers: frontend / backend / AI / data / integration |

---

## Tool Call

```python
result = generate_technical_design_diagram(
    diagram_type = "system_architecture",   # or "component" or "deployment"
    project_name = "IDP POC",               # short project name for diagram title
)
# Returns:
# "Diagram generated:
#   .drawio → /tmp/bnk-workspace/{session}/diagrams/system_architecture.drawio  (N bytes)
#   .png    → /tmp/bnk-workspace/{session}/diagrams/system_architecture.png     (N bytes)
#   Preview: GET /api/threads/{thread_id}/workspace/diagrams/system_architecture.png
#   Type: system_architecture | Model: openai:gpt-5.4-mini"
```

---

## Visual Style Specification (for XML prompt context)

The tool instructs the LLM to produce **production-quality dark-header swimlane diagrams**:

### Canvas
- Background: `#F8FAFC` (off-white)
- Page: 1654 × 1169 (A3 landscape)
- Shadow enabled on nodes

### Swimlane Headers (dark band, white text)
| Lane | Header color |
|------|-------------|
| INPUT / Intake | `#0F172A` (near-black navy) |
| INTELLIGENCE / AI | `#1E3A5F` (dark blue) |
| APPLICATION / Frontend | `#064E3B` (dark green) |
| DATA / Storage | `#78350F` (dark amber) |
| INTEGRATION / External | `#3B0764` (dark purple) |

### Node Types (5 semantic categories)
| Type | Fill | Border | Use for |
|------|------|--------|---------|
| INPUT | `#FFF7ED` | `#EA580C` orange | Email, file intake, triggers |
| PROCESSING | `#EFF6FF` | `#2563EB` blue | AI engines, backends, workers |
| FRONTEND | `#F0FDF4` | `#059669` green | Web UI, portals, review apps |
| STORAGE | `#FFFBEB` | `#D97706` amber | Databases, object stores (cylinder3) |
| EXTERNAL | `#FAF5FF` | `#7C3AED` purple dashed | External APIs, future integrations |

### Edges
- Color: `#64748B` (slate)
- Style: `orthogonalEdgeStyle` with explicit exit/entry points
- Every edge has a short label (≤ 4 words)

---

## Incremental Edit (when user requests changes)

When the user asks to modify a diagram:
1. Update the relevant section in `technical_design.md` using `patch_solution_section(step, content)`.
2. Regenerate the affected diagram: `generate_technical_design_diagram(diagram_type="...", project_name="...")`.
3. The tool saves both `.drawio` and `.png` automatically — no manual XML editing required.

Do NOT read `.drawio` files or pass XML content to any tool. The XML is handled entirely by `generate_technical_design_diagram`.

---

## API Endpoints (for frontend preview)

After generation, the files are accessible via:

| Purpose | Endpoint |
|---------|---------|
| Preview PNG (inline) | `GET /api/threads/{id}/workspace/diagrams/system_architecture.png` |
| Download .drawio | `GET /api/threads/{id}/workspace/diagrams/system_architecture.drawio` |
| List all diagrams | `GET /api/threads/{id}/diagrams` |

---

## Reporting to User

After all diagrams are generated, tell the user:

```
Đã tạo xong diagram kiến trúc:

**System Architecture** (C4 L1)
  Preview: GET /api/threads/{id}/workspace/diagrams/system_architecture.png
  Edit: /diagrams/system_architecture.drawio

**Component Diagram** (C4 L2)
  Preview: GET /api/threads/{id}/workspace/diagrams/component.png
  Edit: /diagrams/component.drawio

**Deployment Diagram**
  Preview: GET /api/threads/{id}/workspace/diagrams/deployment.png
  Edit: /diagrams/deployment.drawio

Bạn có muốn chỉnh sửa diagram nào không?
```

---

## Quality Checklist

Before reporting diagram complete:
- [ ] `.drawio` file exists and is non-empty
- [ ] `.png` file exists and is > 10 KB (non-empty)
- [ ] Title cell present in diagram with project name
- [ ] All 5 swimlane types populated with relevant components from `technical_design.md`
- [ ] At least 8 edges present (connected architecture, not isolated nodes)
- [ ] All nodes have descriptive labels matching `technical_design.md` terminology

---

## Common Mistakes

| ❌ Wrong | ✅ Right |
|----------|---------|
| Embed diagram XML in technical_design.md | Diagrams are separate files only |
| Read .drawio files or pass XML to any tool | Use `generate_technical_design_diagram` only |
| Generate only 1 diagram type | Generate all approved types from confirm_diagram_generation |
| Use generic node labels ("Service A") | Use exact names from technical_design.md |
| Skip `project_name` arg | Always pass project name for title |
| Ignore edge labels | Every edge needs a short label |
