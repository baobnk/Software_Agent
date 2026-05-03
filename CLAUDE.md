# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

`bnk-deepagent` is a multi-agent document generation service for BnK Solution. It transforms customer requirement files (PDF / DOCX / TXT / MD / PPTX / XLSX / images) into a **BRD (`.docx`)** and **WBS (`.xlsx`)** rendered against BnK's standard Word/Excel templates.

It is built on **LangChain DeepAgents** (`create_deep_agent`) — a supervisor with specialist subagents — running on top of LangGraph (checkpointer + interrupts). The reference design is in [`MASTER_REFERENCE.md`](MASTER_REFERENCE.md); this file is the operational contract for anyone (human or agent) editing the code.

> If this file and `MASTER_REFERENCE.md` disagree, **this file wins**. `MASTER_REFERENCE.md` describes the long-term design (v2 / 5-workflow split). The code is still v1 (single graph, 7 subagents). Don't pretend otherwise.

---

## Common Commands

```bash
# ── Setup ────────────────────────────────────────────────────────────────────
conda activate agent                          # Python 3.12 env with deps
cp .env.example .env                          # then fill in ANTHROPIC/OPENAI key
pip install -r requirements.txt               # if env not yet provisioned

# ── Run: CLI (interactive chat) ──────────────────────────────────────────────
python main.py --input ./input --output ./outputs

# ── Run: CLI (one-shot, no HITL) ─────────────────────────────────────────────
python main.py \
  --input  /abs/path/to/requirements \
  --output /abs/path/to/outputs \
  --project "GEHP" \
  --lang vi

# ── Run: API server ──────────────────────────────────────────────────────────
python main.py --serve                        # uvicorn on :8000, --reload on
# OpenAPI:    http://localhost:8000/docs
# Health:     http://localhost:8000/health

# ── Run: Docker (API + MinIO + Langfuse) ─────────────────────────────────────
HOST_INPUT_DIR=/abs/path/inputs \
HOST_OUTPUT_DIR=/abs/path/outputs \
docker compose -f infra/docker-compose.yml up -d --build

# ── Smoke tests (ad-hoc, not pytest) ─────────────────────────────────────────
python test_step1.py --no-hitl --input ./input --model openai:gpt-4.1-mini
python test_step2.py
python test_full.py                           # E2E pipeline against ./input
```

---

## Debugging

```bash
# 1) Verbose graph trace — print every node transition + tool call
DEBUG=true python main.py --input ./input --output ./outputs

# 2) Enable Langfuse tracing (if running docker compose stack)
export LANGFUSE_PUBLIC_KEY=pk-...
export LANGFUSE_SECRET_KEY=sk-...
export LANGFUSE_HOST=http://localhost:3001
python main.py --serve
#   → traces appear in http://localhost:3001 (project: bnk-deepagent)

# 3) Inspect session workspace (state files)
ls -la $WORKSPACE_BASE_DIR/<session_id>/
#   raw_features.md       — output of intake_agent
#   technical_design.md   — output of solution_finder_agent
#   technical_design.drawio
#   brd/                  — BRDDocument sharded by section (Rule §18)
#     _index.json         — page index
#     00_metadata.json … 08_appendix.json
#     05_2_fr/<FR_ID>.json — one file per FR
#   wbs_state.json        — WBSDocument Pydantic AST
#   issues.json           — latest critic validation result
#   AGENTS.md             — persistent memory (DeepAgents)

# 4) Resume HITL interrupt manually (LangGraph)
#   POST /sessions/{id}/approve  with {"tool_name": "render_brd", "decision": "approve"}
#   See known issue under "Production Risks" — verify Command(resume=...) wiring before trusting.

# 5) Replay a specific subagent on existing state (no orchestrator)
python -c "
from agents.critic import create_critic_subagent
from langgraph.prebuilt import create_react_agent
spec = create_critic_subagent()
agent = create_react_agent(model=spec['model'], tools=spec['tools'], prompt=spec['system_prompt'])
print(agent.invoke({'messages': [{'role': 'user', 'content': 'validate brd'}]}))
"

# 6) Dump the resolved model per agent
python -c "from packages.config import get_agent_model; \
  [print(a, '→', get_agent_model(a)) for a in ['orchestrator','intake_agent','brd_drafter_agent','wbs_estimator_agent','critic_agent','exporter_agent']]"

# 7) Validate config files
python -c "import yaml; yaml.safe_load(open('config/agent_models.yaml'))"
python -c "import yaml; yaml.safe_load(open('config/domain_rules.yaml'))"

# 8) Watch SSE stream
curl -N -X POST http://localhost:8000/sessions/<id>/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "hello"}'
```

---

## Architecture Overview

### Topology — Supervisor + Subagents (DeepAgents)

```
         ┌──────────────────────────────────────────────┐
         │  Orchestrator  (create_deep_agent — top)     │
         │  - prompt-driven routing                     │
         │  - tools: set_output_dir, get_output_paths,  │
         │           list_project_outputs               │
         │  - interrupt_on: render_brd, render_wbs      │
         │  - memory:      /AGENTS.md                   │
         │  - backend:     CompositeBackend             │
         └──┬──────────┬──────────┬──────────┬──────────┘
            │          │          │          │
            ▼          ▼          ▼          ▼
        intake →  solution → brd_drafter → critic → wbs_estimator → critic → exporter
        (each = a `dict` returned by create_<agent>_subagent factory)
```

| File | Owns |
|---|---|
| [`orchestrator.py`](orchestrator.py) | `create_orchestrator()` factory; assembles `create_deep_agent` with backend, subagents, memory, interrupts, checkpointer |
| [`agents/`](agents/) | One file per subagent. Each exports `create_<name>_subagent() -> dict` |
| [`tools/`](tools/) | Capability tools — file IO, validators, renderers, state ops |
| [`packages/config.py`](packages/config.py) | `get_agent_model(name)` resolves env → YAML → default |
| [`api/main.py`](api/main.py) | FastAPI: `/sessions`, `/chat` (SSE), `/approve` (HITL), `/state`, `/outputs`, `/output-dir` |
| [`infra/`](infra/) | Dockerfile + docker-compose (API + MinIO + Langfuse) |
| [`config/`](config/) | YAML/JSON: model assignment, domain rules, effort benchmarks, output defaults |
| [`skills/`](skills/) | SKILL.md files — **conditionally loaded** (see Rule §4) |
| [`workspace/`](workspace/) | Session scratch (per-session JSON + markdown state) |
| [`packages/brd/`](packages/brd/) | BRD package: `schema.py` (Pydantic + section sub-models), `operations.py` (per-section CRUD), `store.py` (`BRDStore`), `renderer.py` |
| [`packages/wbs/`](packages/wbs/) | WBS package: `schema.py`, `store.py` (`WBSStore`); render delegates to legacy `wbs_agent_kit` |
| [`prompts/`](prompts/) | All system prompts (deer-flow style) — `orchestrator.py`, `wbs_workflow.py`, `brd_workflow.py`. See Rule §21. |
| [`templates/brd/`](templates/brd/) | docxtpl templates per language: `BnK_BRD_Template_v2.0_{en,vi,ja,zh}.docx` |
| [`assets/`](assets/) | Static assets baked into templates (`bnk_logo.png`, etc.) |
| [`scripts/`](scripts/) | One-shot utilities: `build_brd_template.py`, `smoke_brd_pipeline.py`, etc. |

### State & Communication

Subagents do **not** message-pass. They communicate through a **shared blackboard** — JSON / Markdown files in the session workspace, accessed via `tools/workspace.py` helpers and exposed through `CompositeBackend`:

```
/          → WORKSPACE_BASE_DIR/{session_id}/   (default backend; scratch state)
/input/    → ATTACHMENTS_DIR                    (read-only requirement files)
/output/   → OUTPUT_DIR/{project_name}/         (final BRD/WBS artefacts)
```

State files in workspace (the canonical contract):
| File / dir | Producer | Consumer |
|---|---|---|
| `raw_features.md` | `intake_agent` | `solution_finder`, `brd_drafter`, `wbs_estimator` |
| `technical_design.md` | `solution_finder` | `brd_drafter`, `wbs_estimator` |
| `technical_design.drawio` | `solution_finder` | downstream / Proposal (future) |
| **`project.json`** | **`wbs_estimator` (WBS-first)** | **`brd_drafter` inherits — see Rule §19** |
| `wbs/` *(directory)* | `wbs_estimator` (per-section sharding via `WBSStore` — Rule §18) | `critic`, `exporter`, `brd_drafter` (FR ids) |
| `brd/` *(directory)* | `brd_drafter` (per-section sharding via `BRDStore` — Rule §18) | `critic`, `exporter` |
| `issues.json` | `critic` | orchestrator routing |
| `AGENTS.md` | DeepAgents memory | Orchestrator (always) |

---

## Design Rules

These rules apply to **every change** in this repo. Violations need an explicit override note in the PR description.

### §1. The pattern is locked: Supervisor + DeepAgent subagents

Do **not** introduce hand-written `StateGraph` nodes or LangGraph supervisors alongside DeepAgents. The orchestrator IS the graph. Subagents are dicts:

```python
def create_<name>_subagent() -> dict:
    return {
        "name": "<name>_agent",          # snake_case, ends in _agent
        "description": "<one sentence — used by orchestrator routing>",
        "system_prompt": <NAME>_PROMPT,  # ALL CAPS module-level string
        "model": get_agent_model("<name>_agent"),
        "tools": [...],                  # ≤ 8 per subagent
        # optional:
        "permissions": [...],            # e.g. FilesystemPermission deny writes
    }
```

If a task can't fit this contract (e.g. it needs explicit fan-out / fan-in), **don't smuggle it into a subagent**. Open a design discussion before adding orthogonal frameworks.

### §2. Tool budget: ≤ 30 total, ≤ 8 per subagent

This is enforced by code review. Current count (Nov 2025) is ~58 — over budget. Every PR must keep the global count moving toward 30, not away from it.

**Tool ≠ procedure step.**

A **tool** is a *capability the LLM must decide whether and when to invoke*: read a PDF, render a docx, validate a doc, save state. Cost: tokens for description in every prompt.

A **procedure step** is a fixed point in a fixed workflow: "after init_brd, call set_metadata, then upsert_fr…". These do **not** belong as separate tools — they belong in a SKILL.md.

| ❌ Wrong | ✅ Right |
|---|---|
| `init_brd`, `set_metadata`, `upsert_fr`, `set_nfr`, `append_tech_stack`, `append_abbreviation`, `get_brd_summary` (7 tools) | `patch_brd(operation, payload)` + `get_brd_summary` (2 tools); schema and call order taught via `skills/brd_writing/SKILL.md` |
| 14 setters in `project_context_ops.py` | `save_project_context(json)` + `get_project_context()` |

**When in doubt, ask: "Does the LLM need to choose between this and another tool?"** If no, it's a procedure — collapse it.

### §3. Subagent tool isolation

Each subagent's `tools` list contains only what *that* agent needs. Never pass the global tool list. Use `permissions=[FilesystemPermission(...)]` to *deny* dangerous capabilities (see [`agents/wbs_estimator.py`](agents/wbs_estimator.py) for the pattern — it denies all writes because state is file-mediated).

### §4. Skills are how we avoid token bloat — load them

`skills/<name>/SKILL.md` exists as a first-class capability of `create_deep_agent`. Schemas, multi-step procedures, BA templates, and diagram conventions go in skills, not in system prompts and not as one-tool-per-step.

```python
agent = create_deep_agent(
    ...,
    skills=["./skills/"],          # MUST be passed; currently missing
    subagents=[
        {**intake_spec,         "skills": ["requirement_analysis"]},
        {**solution_spec,       "skills": ["solution_design", "diagram_drawing"]},
        {**brd_drafter_spec,    "skills": ["brd_writing", "diagram_drawing"]},
        {**wbs_estimator_spec,  "skills": ["wbs_estimation"]},
    ],
)
```

A skill description is always loaded; the body is loaded only when the relevant subagent activates. This is the project's primary tool against context bloat.

### §5. Workspace is the single source of truth, not message history

LLM message history is volatile — compaction will drop it. Anything that must survive across turns or subagent boundaries is written to a file in `WORKSPACE_BASE_DIR/{session_id}/`.

- Read state with `read_json` / `read_text` / `read_model` from [`tools/workspace.py`](tools/workspace.py).
- Write state with the matching `write_*` helpers — they are atomic (temp + rename).
- Never `print(...)` state for the LLM to read back. Save it, then re-read with a tool.

### §6. Pydantic AST is the contract between agent and renderer

`BRDDocument` ([`packages/brd/schema.py`](packages/brd/schema.py)) and `WBSDocument` ([`packages/wbs_agent_kit/`](packages/wbs_agent_kit/)) are immutable contracts. `brd_drafter` and `wbs_estimator` *fill* them; `exporter` *renders* them through `docxtpl` / `openpyxl`. Renderer code must never run inside a subagent — only in `tools/renderer.py`, only at export time.

The BRDDocument is the **assembled view**, not the persisted format. On disk, BRD state lives sharded across files under `<workspace>/brd/` per Rule §18. Section sub-models (`MetadataSection`, `IntroductionSection`, …) live alongside `BRDDocument` in `schema.py` and are the read/write unit for individual operations.

If you change a Pydantic field: update the renderer template variables, the section sub-model in `schema.py`, the per-section CRUD in `operations.py`, the dispatch tables in `tools/brd_ops.py`, the validators, and the SKILL.md schema docs — same commit.

### §7. HITL via `interrupt_on`, never via blocking input

User confirmation is an `interrupt_on={"render_brd": True, ...}` config on `create_deep_agent`. The graph pauses; the API resumes with `Command(resume=...)`. Never use `input()`, `getpass()`, or a synchronous block in a tool — the graph cannot be checkpointed mid-tool.

### §8. Folder control is layered: env < CLI < API

| Layer | Source | Wins over |
|---|---|---|
| Default | `config/output.yaml` | — |
| Env | `OUTPUT_DIR` | default |
| CLI | `--output` | env |
| API | `POST /sessions/{id}/output-dir` | everything (per-session) |

Never set `os.environ["OUTPUT_DIR"]` from inside a session-scoped code path — it mutates global state and races other sessions. Pass values through `create_orchestrator(output_dir=...)` / per-session backend.

### §9. Model selection goes through `get_agent_model`

Never hard-code `"openai:gpt-4o"` in a subagent file. Always:

```python
from packages.config import get_agent_model
"model": get_agent_model("<agent>_agent"),
```

This routes through env (`MODEL_<AGENT>`) → `config/agent_models.yaml` → default. Adding a new agent? Register its env key in [`packages/config.py`](packages/config.py) `_ENV_KEY` map.

### §10. Checkpointer: `MemorySaver` for dev, `AsyncPostgresSaver` for prod

`MemorySaver` is the default (single-process, lost on restart). For any multi-worker / production deployment use `create_postgres_checkpointer()` and pass it via `create_orchestrator(checkpointer=...)`. Don't ship a service to a customer with `MemorySaver`.

### §11. Do not regenerate full documents — patch by section_id

This is a hard product rule. Every BRD FR / WBS task / solution step has a stable `section_id` (UUID). Updates from the user (e.g. *"đổi FR3 sang High priority"*) must be applied as an atomic patch to that section_id. Full re-draft of a document is never the right answer once the user has reviewed it once.

### §12. Vietnamese-first, mirror user language

The product is sold in Vietnam. All user-facing strings (subagent prompts, error messages, SSE event payloads) must be language-aware: mirror what the user wrote. Code comments, docstrings, log messages: English.

### §13. Ad-hoc test scripts go to `tests/`, not the repo root

`test_step1.py`, `test_step2.py`, `test_full.py` at the repo root are legacy. New tests go to `tests/` as `pytest`-compatible files. We will migrate existing scripts during the next refactor.

---

## Memory Architecture (3 tiers)

LangGraph gives us two memory primitives — **checkpointer** (short-term, per-thread) and **store** (long-term, cross-thread). DeepAgents adds a third — **`AGENTS.md`** in the workspace backend (project-scoped, compaction-resilient). Use all three; do not conflate them.

```
┌─────────────────────────────────────────────────────────────────┐
│ Tier 1 — Short-term  (LangGraph Checkpointer, AsyncPostgresSaver)│
│   Scope:   thread_id (1 session)                                 │
│   Holds:   graph state, messages, todos, tool_calls, interrupts  │
│   Writes:  AUTOMATIC — never write directly                      │
│   Reads:   AUTOMATIC — graph resumes from latest checkpoint      │
├─────────────────────────────────────────────────────────────────┤
│ Tier 2 — Project memory  (DeepAgents /AGENTS.md on the backend)  │
│   Scope:   session workspace                                     │
│   Holds:   project context surviving compaction (decisions,      │
│            user-confirmed scope, in-flight todos)                │
│   Writes:  Agent edits via MemoryMiddleware (DeepAgents native)  │
│   Reads:   Auto-injected into every model call                   │
├─────────────────────────────────────────────────────────────────┤
│ Tier 3 — Long-term  (LangGraph Store, AsyncPostgresStore)        │
│   Scope:   namespace tuple (e.g. user_id, project_id)            │
│   Holds:   user prefs, project facts, glossary, decisions log    │
│   Writes:  Agent calls a memory tool with explicit schema        │
│   Reads:   Agent calls a memory tool, OR injected via middleware │
└─────────────────────────────────────────────────────────────────┘
```

### §14. Persistence is Postgres in production, in-memory only in dev

Both checkpointer and store live on **one** Postgres instance, sharing **one** `AsyncConnectionPool` ([`infra/persistence.py`](infra/persistence.py)). When `DATABASE_URL` is unset the module falls back to `MemorySaver + InMemoryStore` with a loud warning — that fallback is dev-only.

```python
# Bootstrap once per process (FastAPI lifespan or CLI main):
from infra.persistence import init_persistence, get_checkpointer, get_store

await init_persistence()        # idempotent; reads DATABASE_URL

agent = create_deep_agent(
    ...,
    checkpointer=get_checkpointer(),
    store=get_store(),
)
```

Never instantiate `MemorySaver()` or `AsyncPostgresSaver()` directly in `orchestrator.py` or anywhere downstream — always go through `infra/persistence`. This keeps pool ownership in one place.

### §15. Store namespace convention (≤ 4 elements, leftmost = tenancy)

These are the **only** approved namespace shapes. Add new ones in this file before using them in code.

| Namespace | Holds | Lifetime |
|---|---|---|
| `("users", user_id, "preferences")` | language, default OUTPUT_DIR, preferred model, timezone | until user changes |
| `("users", user_id, "projects", project_id)` | per-user-per-project facts (decisions, custom glossary entries) | with project |
| `("projects", project_id, "glossary")` | shared project terminology (DMS, ECO, …) | with project |
| `("projects", project_id, "decisions")` | architecture decisions logged from `solution_finder` | with project |
| `("global", "domain_rules")` | org-wide reference data (read-mostly) | manual |

Hard rules:
- **Leftmost element scopes tenancy.** `user_id` first for per-user data, `project_id` first for shared data, `global` first for read-mostly org-wide data.
- **Tuple length ≤ 4.** Postgres index degrades beyond that.
- **Value blob ≤ 10 KB.** If it's bigger, write to workspace and store the path.
- **No raw `store.put` from agent code.** Always wrap in a typed tool (e.g. `save_user_preference`) so values have a known schema.

### §16. What goes in which tier (and what does NOT)

| Data | Correct tier | Why |
|---|---|---|
| Chat messages of current session | Checkpointer | Auto-managed; resume needs them |
| Pending HITL interrupt | Checkpointer | Part of graph state |
| `BRDDocument`, `WBSDocument` AST | **Workspace file** | Big, binary-ish, has its own renderer |
| `raw_features.md`, `technical_design.md` | **Workspace file** | Big, agent re-reads via tool |
| User confirmed scope / decision in this session | `/AGENTS.md` (Tier 2) | Must survive compaction |
| Todo list during planning | `/AGENTS.md` | DeepAgents handles it |
| User language preference (vi/en) | Store: `("users", uid, "preferences")` | Crosses sessions |
| Project glossary that should follow project to next session | Store: `("projects", pid, "glossary")` | Crosses sessions, multi-user |
| API key, secret, credential | **Neither — environment / vault** | Never log, never persist |

Common mistakes to avoid:
- ❌ Stuffing the BRD JSON into Store. Use the workspace.
- ❌ Stuffing message history into Store. That's the checkpointer.
- ❌ Reading Store on every turn for static config. Load YAML once at startup.
- ❌ Writing to `/AGENTS.md` from a tool. Let `MemoryMiddleware` handle it.

### §17. Memory tools have explicit schemas, not free-form puts

Every Tier 3 write goes through a tool defined in [`tools/memory.py`](tools/memory.py) with a documented schema:

```python
@tool
async def save_user_preference(user_id: str, key: str, value: str) -> str:
    """Persist a durable preference about the user across sessions."""
    store = get_store()
    await store.aput(("users", user_id, "preferences"), key, {"value": value})
    return f"Saved {key}={value}."
```

Adding a new memory tool? Update this file's namespace table (§15) **first**, then write the tool, then add it to the relevant subagent's `tools` list (counts toward the 30-tool budget — Rule §2).

### §18. Section-sharded persistence for documents

Document state (BRD, WBS) is **NOT** stored as one monolithic JSON file.
It is sharded into **one file per section**, plus a top-level `_index.json`
page index. Implemented by `BRDStore` ([`packages/brd/store.py`](packages/brd/store.py))
and `WBSStore` ([`packages/wbs/store.py`](packages/wbs/store.py)).

**BRD layout** (12 sections + per-FR sharding):
```
workspace/{session}/brd/
  _index.json                 ← page index (section_id → file, last_modified)
  00_metadata.json            ← cover, version_history
  01_introduction.json        ← purpose, intended_audience
  02_context.json             ← background, objectives, constraints, assumptions
  03_scope.json               ← scope_in, scope_out
  04_stakeholders.json
  05_2_fr/<FR_ID>.json        ← one file per Functional Requirement (volatile)
  05_3_nfr.json
  05_4_data.json
  05_5_integrations.json
  06_acceptance.json
  07_glossary.json
  08_appendix.json
```

**WBS layout** (3 sections + per-task sharding for L4):
```
workspace/{session}/wbs/
  _index.json                 ← page index + task list with effort summary
  00_metadata.json            ← project_code, project_name, MasterData (rates + %)
  10_structure.json           ← all L1/L2/L3 nodes (flat, set up once)
  20_tasks/<code>.json        ← one file per L4 leaf task (volatile — re-estimated often)
```

L1/L2/L3 are *structural* (no effort) — kept in one file because they're set
up once during decomposition. L4 are *leaf tasks* with `md_be`/`md_fe` —
sharded per-task because they get re-estimated repeatedly.

**Why:** most edits touch ONE section. Loading a 20 KB monolithic state file for every patch is wasteful. Section sharding makes each `set_brd_text` or `upsert_fr` cost ~0.1-0.5 KB read+write instead of ~20 KB. `get_brd_summary` reads ONLY `_index.json` (~500 tokens). The full document is assembled only at render and validation time via `BRDStore.assemble()`.

**Token-cost contract** — operations MUST honor these:
| Operation | Bytes touched |
|---|---:|
| `get_summary` (index-only) | ≤ 2 KB |
| `set_brd_text(field, value)` | ≤ 1 KB read + ≤ 1 KB write |
| `add_brd_list_item(list, item)` | ≤ 1 KB read + ≤ 1 KB write |
| `upsert_brd_row(table, row)` | ≤ 2 KB read + ≤ 2 KB write |
| `upsert_fr(fr)` | ≤ 1 KB read (just that FR) + ≤ 1 KB write |
| `assemble()` (render only) | ≤ 30 KB read |

**Index updates are eager.** Every `write_section` / `write_fr` updates `_index.json` atomically (temp + rename). A crashed process leaves either the old or the new state — never a half-written index.

**Rules for adding a new section to the BRD (or any sharded store):**
1. Add a section sub-model to `schema.py` (Pydantic, all fields default-valued).
2. Register it in `SECTION_REGISTRY` in `store.py` with stable `section_id` + filename.
3. Add per-section CRUD functions to `operations.py` (one block per section).
4. Add a row to the relevant dispatch table in `tools/brd_ops.py` (no new tool — reuse the 6 existing dispatchers).
5. Update the docxtpl template via `scripts/build_brd_template.py`.
6. Update this table in CLAUDE.md.

**Anti-patterns:**
- ❌ Per-row sharding (one file per NFR row, one per glossary entry). Overhead larger than savings — keep table sections in one file.
- ❌ Loading the whole document for a single-field edit. Always go through `BRDStore.read_section(...)` → mutate → `write_section(...)`.
- ❌ Bypassing the index. If you bulk-write section files, also call `_touch_section`/`_touch_fr` so the index stays in sync.
- ❌ Storing transient state (current FR being drafted, in-flight chat) in the store. Use the workspace AGENTS.md or graph state instead.

### §19. Pipeline ordering: WBS-first, BRD inherits

The canonical pipeline runs `wbs_estimator` **before** `brd_drafter`.
Rationale: WBS owns the project metadata (project_code, project_name,
language, version), and BRD inherits it from `workspace/project.json`.
Routing this way:
  • Eliminates duplicate metadata authoring (one source, one file).
  • Lets the WBS define FR ids first; BRD then formalizes the same ids.
  • Makes BRD↔WBS metadata mismatch impossible by construction.

```
intake → solution_finder
            ↓
       wbs_estimator         (init_wbs writes project.json + decomposes into tasks)
            ↓ critic loop
       brd_drafter           (init_brd inherits project.json + formalizes FRs)
            ↓ critic + traceability
       exporter
```

Routing rules:
- After `solution_finder` confirms, route to `wbs_estimator` (NOT brd_drafter).
- After `validate_wbs` PASSES, route to `brd_drafter`.
- After `validate_brd` AND `validate_traceability` PASS, ask user → exporter.
- BRD-first is permitted as a fallback (when `init_brd` is called with
  explicit `project_name`+`project_code` — bootstraps `project.json`) but
  the validators will still enforce metadata consistency.

### §20. Shared project metadata is the single source of truth

`workspace/project.json` ([`packages/project_meta.py`](packages/project_meta.py))
holds the canonical project_code, project_name, language, version, author.
Every store reads from it; only `init_wbs` (and `init_brd` as fallback) is
allowed to write.

**Validators enforce consistency:**
| Code | When |
|---|---|
| `META_MISMATCH` | BRD section `project_code`/`project_name` differs from WBS section |
| `META_DRIFT` | Either BRD or WBS section drifted from the canonical `project.json` |

These run inside `validate_traceability` so a single critic call covers
metadata + cross-doc traceability.

**Rules:**
- The agent **does not** edit `project.json` directly. Use `init_wbs` for
  initial creation; let `init_brd` inherit. Override via explicit args only
  when truly needed.
- The renderer reads `language` from each store's metadata section, but
  that is sourced from `project.json` — same value end-to-end.
- The `BRDStore.assemble()` and `WBSStore.assemble()` calls return the
  authoritative view at render time. They do NOT re-read `project.json` —
  consistency is enforced at write time, not read time.

### §21. All prompts live in the `prompts/` package (deer-flow style)

System prompts MUST NOT be inlined inside agent / orchestrator / workflow
files. They live in [`prompts/`](prompts/) as Python modules — one file
per agent / workflow:

```
prompts/
  __init__.py            ← exports all `apply_*_prompt()` helpers
  orchestrator.py        ← main DeepAgent prompt (intake + solution + delegation)
  wbs_workflow.py        ← WBS workflow prompt
  brd_workflow.py        ← BRD workflow prompt
```

Each module exports two things:
1. `<NAME>_PROMPT_TEMPLATE` — the raw template string (top-level constant).
2. `apply_<name>_prompt(**kwargs) -> str` — composer that returns the final
   string with any dynamic sections substituted in.

**Why the package vs. inline strings:**
- Prompts are large (often 2-5 KB) and dominate the file when inlined.
- Production teams need to A/B test, version, and iterate on prompts
  independently of the orchestration code.
- Multiple agents may share prompt fragments (sections, hard-rule blocks).
- Easier to lint, search, and diff prompt-only changes.

**Call site pattern** (all factories follow this):
```python
from prompts import apply_orchestrator_prompt
agent = create_deep_agent(
    ...,
    system_prompt=apply_orchestrator_prompt(),
)
```

**Adding a new agent / workflow:**
1. Create `prompts/<name>.py` with `<NAME>_PROMPT_TEMPLATE` + `apply_<name>_prompt()`.
2. Add re-exports to `prompts/__init__.py`.
3. Import `apply_<name>_prompt` in the agent file; never inline the string.

**Anti-pattern:** assigning a triple-quoted string >200 chars containing
"You are…" anywhere outside `prompts/`. The repo's smoke check greps for
this and the CLAUDE-driven workflow flags it.

## Prompt structure

Each prompt module follows the same canonical sections:

1. **Role line** — *"You are the X agent for BnK Solution."*
2. **Hard rules section** — what the agent MUST / MUST NOT do.
3. **Workflow** — numbered tool-calling sequence.
4. **Output schema** — exact format expected (table, JSON, markdown sections).
5. **Edge-case handling** — what to do when input is missing / contradictory.

Avoid embedding large schemas or template bodies inline. Move those to a SKILL.md (Rule §4).

---

## API Surface (FastAPI)

Implemented in [`api/main.py`](api/main.py):

| Method | Path | Purpose |
|---|---|---|
| POST | `/sessions` | Create a session, returns `session_id` |
| POST | `/sessions/{id}/files` | Upload requirement files |
| POST | `/sessions/{id}/chat` | Send message, returns SSE stream |
| POST | `/sessions/{id}/approve` | Resume from a HITL interrupt |
| GET  | `/sessions/{id}/state` | Read BRD/WBS/issues JSON |
| GET  | `/sessions/{id}/outputs` | List artefacts on disk |
| POST | `/sessions/{id}/output-dir` | Override output dir for this session |
| GET  | `/health` | Liveness probe |

SSE event types:
```json
{"type": "token",  "content": "..."}
{"type": "hitl",   "tool": "render_brd", "message": "..."}
{"type": "done"}
{"type": "error",  "message": "..."}
```

---

## Production Risks (read before deploying)

These are known issues we are *aware of and have not fixed yet*. Treat them as load-bearing context:

1. **In-memory session registry** — `_sessions: dict` in [`api/main.py`](api/main.py). Single process only; restart = lost sessions. → migrate to Redis-backed registry.
2. **Checkpointer / Store wiring** — [`infra/persistence.py`](infra/persistence.py) provides Postgres-backed `AsyncPostgresSaver + AsyncPostgresStore` with a memory fallback. `orchestrator.py` and `api/main.py` must call `await init_persistence()` at startup and pass `get_checkpointer()` / `get_store()` to `create_deep_agent`. Until that wiring lands, the agent runs on the in-memory fallback and **all session/store data is lost on restart**.
3. **Process-global `os.environ["OUTPUT_DIR"]` mutation** — race condition on concurrent sessions. Must be removed (Rule §8).
4. **Blocking renderer on the event loop** — `openpyxl` / `docxtpl` are synchronous and slow. Move `render_brd` / `render_wbs` to a subprocess pool (see Paper2Any pattern).
5. **HITL resume contract** — `/approve` posts `{"resume": ...}`, but LangGraph requires `Command(resume=...)`. Trace the path before relying on it.
6. **`CORS=*`, no auth, no rate limit** — fine for internal demo, not for ship.
7. **Skills not loaded** — `skills=` is not passed to `create_deep_agent`. The `skills/` directory is currently dead weight. Fix per Rule §4.
8. **`plan_exporter`, `project_context_ops`, `timeline_ops` are dead code** — registered nowhere. Remove or wire.

---

## Conventions

- **Python**: 3.12. Conda env `agent`. Type hints required on public functions. Pydantic v2.
- **Imports**: top-of-file, no inline imports except where avoiding circulars (e.g. `tools/` ↔ `agents/`).
- **Logging**: use [`tools/logger.py`](tools/logger.py); never `print()` outside of CLI entrypoints.
- **Async**: API handlers are `async def`; tools are sync (DeepAgents wraps them).
- **Config**: two layers — `.env` for credentials/URLs, `config/*.yaml|json` for behavioral knobs.
- **No SQLAlchemy / ORM** — we use the LangGraph checkpointer for state and Pydantic for ASTs. That's it.
- **Commit hygiene**: one logical change per commit. Refactors that move code go in their own commit; semantic changes follow.
- **No silent fallbacks** — if an env var or config is missing, fail loudly at startup.

---

## When extending the system

| You want to … | Do this |
|---|---|
| Add a new specialist subagent | New file in `agents/`, factory `create_<name>_subagent`, register in `agents/__init__.py` AND in `orchestrator.py` `subagents=[...]`, add prompt route in `ORCHESTRATOR_PROMPT`, add model entry in `config/agent_models.yaml` and `_ENV_KEY` |
| Add a new tool | One file in `tools/` per logical group. Pure function, type hints, returns a string the LLM can read. Then **decide if it's a tool or a procedure** (Rule §2) — most additions should be a SKILL change, not a tool. |
| Add a skill | New folder `skills/<name>/SKILL.md`. Reference it from the relevant subagent's `skills` list. |
| Add a new diagram type | Extend `skills/diagram_drawing/SKILL.md` and the `solution_finder` prompt — do **not** add per-diagram-type tools. |
| Change BRD schema (add/remove field) | Per Rule §18: update section sub-model in `packages/brd/schema.py`, register in `SECTION_REGISTRY` if new section, add CRUD in `operations.py`, add dispatch row in `tools/brd_ops.py`, update template via `scripts/build_brd_template.py`, update validators in `tools/validators.py`, update `skills/brd_writing/SKILL.md` — same commit. |
| Change WBS schema | Update Pydantic model in `packages/wbs_agent_kit/`, update template, validators, and SKILL.md — same commit. |
| Add a new input file format | Extend `tools/file_reader.py`. Keep tool count bounded — prefer one `read_file(path)` smart-dispatch over one tool per format. |
| Change output folder layout | Update `tools/folder_manager.py::get_output_paths`. Bump it as a versioned breaking change — downstream API consumers will see different paths. |

---

## References

- Long-form design: [`MASTER_REFERENCE.md`](MASTER_REFERENCE.md)
- Phase plans: [`IMPLEMENTATION_PLAN_FULL.md`](IMPLEMENTATION_PLAN_FULL.md), [`IMPLEMENTATION_PLAN_BRD.md`](IMPLEMENTATION_PLAN_BRD.md), [`IMPLEMENTATION_PLAN_PREPROCESSING.md`](IMPLEMENTATION_PLAN_PREPROCESSING.md), [`IMPLEMENTATION_PLAN_TEMPLATE_FILL.md`](IMPLEMENTATION_PLAN_TEMPLATE_FILL.md)
- Tools audit: [`TOOLS_INVENTORY.md`](TOOLS_INVENTORY.md), [`TOOLS_CLASSIFICATION.md`](TOOLS_CLASSIFICATION.md)
- DeepAgents pattern: <https://www.langchain.com/blog/building-multi-agent-applications-with-deep-agents>
- LangGraph HITL: <https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/>
- LangGraph checkpointers: <https://langchain-ai.github.io/langgraph/concepts/persistence/>
- LangGraph long-term memory (Store): <https://langchain-ai.github.io/langgraph/concepts/memory/>
