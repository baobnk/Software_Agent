---
name: brd_writing
description: BnK BRD authoring — schema, FR template, NFR units, table shapes, BA conventions. Loaded by the BRD workflow's create_react_agent.
when_to_load: agents.brd_workflow (always while drafting BRD)
---

# BRD Writing — Schema & Conventions

You are filling a `BRDDocument` (Pydantic AST) that renders into a Word file
via one of four templates: `BnK_BRD_Template_v2.0_{en,vi,ja,zh}.docx`.
Pipeline-wise, this runs **after** `run_wbs_workflow` — meaning the
project metadata (project_code, project_name, language, version) and the
FR ids are already chosen. Your job is to **formalize**, not to invent.

## Pipeline contract (WBS-first)

1. `init_brd()` is called with **NO arguments** → inherits from `workspace/project.json`.
2. WBS already linked L4 tasks to FRs via `source_feature_id="FR1"`, `"FR2"`, etc.
3. Your FR ids in §5.2 MUST match those `source_feature_id` values exactly.
4. Each FR must have `acceptance_criteria` ≥ 2 items — critic will fail otherwise.
5. NFR rows MUST have measurable units in `target` (ms, %, req/s, MB, sessions, …).

## Section → Tool map

| Section | Tool | Shape / Constraint |
|---|---|---|
| §1.1 Purpose | `set_brd_text("purpose", v)` | 2-5 sentences |
| §1.2 Intended Audience | `upsert_brd_row("intended_audience", p)` | `{"role","party","responsibility"}` — ≥ 2 rows |
| §2.1 Background | `set_brd_text("background", v)` | 1 paragraph, business context |
| §2.2 Objectives | `set_brd_text("objectives", v)` | 3-5 SMART goals |
| §2.3.1 Constraints | `add_brd_list_item("constraints", item)` | ≥ 3 hard limits |
| §2.3.2 Assumptions | `add_brd_list_item("assumptions", item)` | ≥ 3 unverified conditions |
| §3.1 Scope IN | `add_brd_list_item("scope_in", item)` | ≥ 4 capabilities/deliverables |
| §3.2 Scope OUT | `add_brd_list_item("scope_out", item)` | ≥ 3 explicit exclusions |
| §4 Stakeholders | `upsert_brd_row("stakeholders", p)` | `{"id":"S1","name","role","responsibility"}` — ≥ 3 rows |
| §5.2 FR detail | `upsert_fr(payload)` | full FR shape (see below) |
| §5.3 NFR | `upsert_brd_row("nfr_rows", p)` | `{"category","metric","target"}` — ≥ 5 rows |
| §5.4 Data | `set_brd_text("data_requirements", v)` | paragraph: data sources, volumes, retention |
| §5.5 Integrations | `upsert_brd_row("integrations", p)` | `{"system","direction","protocol","note"}` |
| §6 Acceptance | `add_brd_list_item("acceptance_criteria", item)` | ≥ 3 project-level criteria |
| §7 Glossary | `upsert_brd_row("glossary", p)` | `{"term","definition"}` — ≥ 5 domain terms |
| §7 Abbreviations | `upsert_brd_row("abbreviations", p)` | `{"term","definition"}` — ≥ 5, ALL acronyms |
| §8 Appendix intro | `set_brd_text("appendix", v)` | brief intro sentence (optional) |
| §8 Appendix items | `add_brd_list_item("appendix_items", item)` | ≥ 3 named items (see below) |

## Minimum content table (validator-enforced)

| Section | Minimum | Error code if violated |
|---|---|---|
| §1.2 Intended Audience | 2 rows | BRD_SHORT_AUDIENCE |
| §2.1 Background | non-empty | BRD_MISSING_BACKGROUND |
| §2.2 Objectives | non-empty | BRD_MISSING_OBJECTIVES |
| §2.3.1 Constraints | 3 items | BRD_NO_CONSTRAINTS / BRD_SHORT_CONSTRAINTS |
| §2.3.2 Assumptions | 3 items | BRD_NO_ASSUMPTIONS / BRD_SHORT_ASSUMPTIONS |
| §3.1 Scope In | 4 items | BRD_NO_SCOPE_IN / BRD_SHORT_SCOPE_IN |
| §3.2 Scope Out | 1+ items | BRD_NO_SCOPE_OUT |
| §4 Stakeholders | 3 rows | BRD_NO_STAKEHOLDERS / BRD_SHORT_STAKEHOLDERS |
| §5.3 NFR | 5 rows | BRD_SHORT_NFR |
| §6 Acceptance | 3 items | (checked in context) |
| §7 Glossary | 5 terms | BRD_SHORT_GLOSSARY |
| §7 Abbreviations | 5 entries | BRD_NO_ABBREVIATIONS / BRD_SHORT_ABBREVIATIONS |
| §8 Appendix items | 3 items | BRD_NO_APPENDIX |

## FR shape (most critical section)

```json
{
  "fr_id": "FR1",
  "name": "Document Upload",
  "priority": "Critical",
  "short_description": "≤ 20 words for the §5.1 overview table",
  "description": "3-6 sentences. WHAT the system does and WHY it matters.",
  "user_stories": [
    "As a <role>, I want <goal> so that <benefit>",
    "As an admin, I want bulk upload so that I can onboard quickly"
  ],
  "acceptance_criteria": [
    "Given <context>, When <action>, Then <observable result>",
    "Given a 50MB PDF, When uploaded, Then the system returns 201 with a document_id"
  ],
  "interface_notes": "POST /api/v1/documents — multipart form-data. Returns {document_id, status}."
}
```

**Priority levels:** `Critical | High | Medium | Low | Future`.

## Constraints & Assumptions — what to include

**Constraints** (hard limits, things the project CANNOT change):
- Budget limits, deadline, regulatory/legal requirements
- Mandated technology stack or architecture decisions
- Security policies (on-premise only, data residency, encryption standard)
- Change control process (all scope changes must go through formal CCB)
- Infrastructure limits (existing hardware, no public cloud)
- Compliance standards that must be met (ISO 27001, GDPR, etc.)

**Assumptions** (believed to be true, not yet confirmed):
- Third-party systems will expose required APIs/interfaces
- Infrastructure will be provisioned on time by the client
- Data quality meets minimum standards for AI training
- Business stakeholders will be available for reviews and sign-offs
- Content creators / SMEs will provide training materials on schedule
- Users will receive training before go-live

## Scope In — what to include

List each major deliverable or capability:
- Each functional module (e.g. "AI Knowledge Extraction module")
- Each integration system (e.g. "HR/EMS system integration")
- Project deliverables (BRD, Technical Design, Test Reports, User Guide)
- Training and handover sessions
- Infrastructure setup and deployment

## Scope Out — what to include

List things explicitly excluded to prevent scope creep:
- Third-party platforms not in this release
- Client-side application development (if not in scope)
- Infrastructure cost or licensing fees
- Load testing and security testing (client's responsibility)
- Data preparation and labeling beyond agreed scope

## Abbreviations — how to build the list

Scan ALL sections of the document and extract every acronym or abbreviation.
**Common ones to include regardless of domain:**
BRD, WBS, FR, NFR, API, REST, HTTP, UI, UX, DB, SQL, AI, ML, LLM

**Domain-specific examples (extract from actual document content):**
LMS (Learning Management System), RAG (Retrieval-Augmented Generation),
RBAC (Role-Based Access Control), AD (Active Directory), LDAP (Lightweight
Directory Access Protocol), HR (Human Resources), EMS (Employee Management
System), SLA (Service Level Agreement), RTO (Recovery Time Objective),
RPO (Recovery Point Objective), HITL (Human-in-the-Loop), VR (Virtual Reality)

## Appendix — how to structure it

The Appendix references supplementary documents and diagrams. Format each
item as: `"Appendix X: <Title>"` or `"Appendix X: <Title> — <brief description>"`

Typical appendix items for BnK projects:
- `"Appendix A: Use Case Diagram"` — or specify the diagram tool
- `"Appendix B: High-Level System Architecture Diagram"`
- `"Appendix C: Data Flow Diagram (DFD)"`
- `"Appendix D: Technical Design Document"`
- `"Appendix E: Integration API Specifications"`
- `"Appendix F: Project Timeline / Gantt Chart"`
- `"Appendix G: Risk Register"`

Use as many as apply to the project. Reference the actual drawio / technical
design files produced earlier in the pipeline where appropriate.

## NFR target unit table (mandatory units)

| Category | Common metrics | Unit examples |
|---|---|---|
| Performance | response time, throughput | ≤ 200 ms, ≥ 100 req/s, ≤ 3 s/page |
| Scalability | concurrent users, peak load | ≥ 1000 sessions, ≥ 50 concurrent uploads |
| Availability | uptime, MTBF, RTO, RPO | ≥ 99.5% monthly, ≤ 1 h RTO, ≤ 4 h RPO |
| Security | auth method, encryption, audit | OAuth 2.0 + RBAC, AES-256 at rest, 90-day audit logs |
| Maintainability | logs retention, deploy time | 30 days hot, ≤ 15 min deploy |
| Compliance | standards | PCI-DSS Level 1, ISO 27001 |
| Usability | page load, accessibility | ≤ 3 s initial load, WCAG 2.1 AA |

A target without a unit (e.g., `"target": "fast"`) FAILS the validator with `NFR_NO_TARGET`.

## BA conventions (BnK house style)

- **SMART objectives**: Specific, Measurable, Achievable, Relevant, Time-bound.
- **User Story Mapping**: every FR has ≥ 2 user stories; complex FRs get 3-4.
- **BDD acceptance criteria**: Given-When-Then. State observable behavior, not implementation.
- **Numbered FR ids without gaps**: FR1, FR2, FR3. Never skip.
- **Mirror the user's language**. Section labels are baked into the template per
  language; do NOT translate them yourself.

## Critic error code → fix

| Code | Fix |
|---|---|
| `BRD_MISSING_PURPOSE` | `set_brd_text("purpose", ...)` |
| `BRD_MISSING_BACKGROUND` | `set_brd_text("background", ...)` |
| `BRD_MISSING_OBJECTIVES` | `set_brd_text("objectives", ...)` |
| `BRD_NO_CONSTRAINTS` | `add_brd_list_item("constraints", ...)` × 3+ |
| `BRD_NO_ASSUMPTIONS` | `add_brd_list_item("assumptions", ...)` × 3+ |
| `BRD_NO_SCOPE_IN` | `add_brd_list_item("scope_in", ...)` × 4+ |
| `BRD_NO_SCOPE_OUT` | `add_brd_list_item("scope_out", ...)` × 1+ |
| `BRD_NO_STAKEHOLDERS` | `upsert_brd_row("stakeholders", ...)` × 3+ |
| `BRD_SHORT_NFR` | `upsert_brd_row("nfr_rows", ...)` for missing categories |
| `BRD_SHORT_GLOSSARY` | `upsert_brd_row("glossary", ...)` × 5+ |
| `BRD_NO_ABBREVIATIONS` | `upsert_brd_row("abbreviations", ...)` × 5+ |
| `BRD_NO_APPENDIX` | `add_brd_list_item("appendix_items", "Appendix A: ...")` × 3+ |
| `FR_DUPLICATE_ID` | `upsert_fr(payload)` with corrected fr_id |
| `FR_EMPTY_DESCRIPTION` | `upsert_fr` re-write with full description |
| `FR_NO_ACCEPTANCE` | `upsert_fr` with `acceptance_criteria` populated |
| `FR_NUMBERING_GAP` | `upsert_fr` to fill the missing FR id |
| `NFR_NO_TARGET` | `upsert_brd_row("nfr_rows", ...)` with measurable target |
| `META_MISMATCH` / `META_DRIFT` | Re-run `init_brd()` to re-inherit from project.json |
| `TRACE_UNCOVERED_FR` | This is WBS's job — not your problem |

## Render

After all validation checks PASS, call:
```
render_brd(output_path="<workspace>/BRD.docx")
```
The exact `<workspace>` path is what you saw in earlier tool results (the
init_brd output mentions it). Do NOT invent paths.

## Common mistakes

- ❌ Inventing a `project_code` different from what WBS already wrote.
- ❌ Using FR ids not present in WBS `source_feature_id`.
- ❌ NFR rows like `{"category": "Performance", "metric": "fast", "target": "soon"}`.
- ❌ Long descriptions (>800 chars) as a single FR — split into multiple FRs.
- ❌ Editing `workspace/project.json` directly. Override only via `init_brd` args.
- ❌ Calling `render_brd` with a made-up path like `/workspace/foo.docx`.
- ❌ Skipping §7 Abbreviations — every acronym used ANYWHERE must be listed.
- ❌ Leaving §8 Appendix empty — always reference the technical design and diagrams.
- ❌ Only 1-2 constraints or assumptions — these MUST be comprehensive.
- ❌ Empty scope_in — this is the core scope statement of the entire BRD.
