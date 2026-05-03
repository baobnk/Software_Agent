# BnK DeepAgent — BRD + WBS Document Generator

Multi-agent system built with **LangChain DeepAgents** that transforms customer
requirement files (PDF, DOCX, TXT, MD, PPTX, XLSX, images) into production-ready
**BRD (.docx)** and **WBS (.xlsx)** using BnK Solution's templates.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER (chat / API / CLI)                       │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  ORCHESTRATOR (DeepAgent)                        │
│  Model: anthropic:claude-sonnet-4-6                              │
│  Backend: CompositeFilesystemBackend                             │
│    /input/    → ATTACHMENTS_DIR (user-controlled)               │
│    /output/   → OUTPUT_DIR (user-controlled) ◄── FOLDER CONTROL │
│    /          → WORKSPACE_BASE_DIR (session scratch)            │
│  Memory: /AGENTS.md  (persists across context compression)      │
│  HITL: interrupt before render_brd / render_wbs                  │
└──┬──────────┬──────────┬──────────┬──────────┬─────────────────┘
   │          │          │          │          │
   ▼          ▼          ▼          ▼          ▼
┌──────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│Intake│ │  BRD   │ │  WBS   │ │Critic  │ │Exporter│
│Agent │ │Drafter │ │Estimat.│ │Agent   │ │Agent   │
└──────┘ └────────┘ └────────┘ └────────┘ └────────┘
   │          │          │          │          │
Tools:     Tools:     Tools:     Tools:     Tools:
list_files init_brd   init_wbs   validate_  render_brd
read_pdf   upsert_fr  upsert_    brd        render_wbs
read_docx  set_nfr    task       validate_  get_output_
read_pptx  set_meta   set_master wbs        paths
...        ...        ...        validate_  upload_s3
                                 traceabil. ...
```

### Pipeline (happy path)

```
User uploads files
      ↓
  intake_agent  ─── reads all input files ──► raw_features.md
      ↓
brd_drafter_agent ─ generates BRD AST ──────► brd_state.json
      ↓
  critic_agent  ─── validates BRD ───────────► issues.json
      │ FAIL (≤3)       │ PASS
      ↑─────────────────┘
      ↓ PASS
wbs_estimator_agent ─ decomposes into tasks ► wbs_state.json
      ↓
  critic_agent  ─── validates WBS + trace ──► issues.json
      │ FAIL (≤3)       │ PASS
      ↑─────────────────┘
      ↓ PASS
  [HITL gate]   ─── user confirms export
      ↓ approved
 exporter_agent ─── renders + saves ────────► OUTPUT_DIR/{project}/
                                              ├── BRD/{name}_BRD_v0.1.docx
                                              └── WBS/{name}_WBS_v0.1.xlsx
```

---

## Folder Control

User controls the output folder at **three levels** (in priority order):

1. **Per-session API call**: `POST /sessions/{id}/output-dir {"output_dir": "/my/path"}`
2. **Env var**: `OUTPUT_DIR=/my/path`
3. **Config default**: `config/output.yaml → output_dir`

Output structure is always:
```
{OUTPUT_DIR}/
└── {project_name}/
    ├── BRD/
    │   └── {project_name}_BRD_v0_1_0.docx
    └── WBS/
        └── {project_name}_WBS_v0_1_0.xlsx
```

---

## Project Structure

```
bnk-deepagent/
├── main.py                     # CLI: interactive chat or one-shot
├── orchestrator.py             # create_deep_agent() — main entry point
├── agents/
│   ├── intake.py               # Subagent: parse input files
│   ├── brd_drafter.py          # Subagent: generate BRD AST
│   ├── wbs_estimator.py        # Subagent: decompose into WBS tasks
│   ├── critic.py               # Subagent: deterministic validation
│   └── exporter.py             # Subagent: render + save files
├── tools/
│   ├── workspace.py            # Session state (JSON files in /workspace/)
│   ├── file_reader.py          # read_pdf, read_docx, read_pptx, ...
│   ├── brd_ops.py              # init_brd, upsert_fr, set_nfr, ...
│   ├── wbs_ops.py              # init_wbs, upsert_task, ...
│   ├── validators.py           # validate_brd, validate_wbs, traceability
│   ├── renderer.py             # render_brd → .docx, render_wbs → .xlsx
│   └── folder_manager.py       # create_project_folder, get_output_paths, ...
├── skills/
│   ├── brd/SKILL.md            # BRD writing standards loaded as skill
│   └── wbs/SKILL.md            # WBS estimation heuristics loaded as skill
├── memory/
│   └── AGENTS.md               # Persistent session memory template
├── config/
│   ├── agent_models.yaml       # Model + provider per agent (swap without code change)
│   └── output.yaml             # Folder defaults
├── api/
│   └── main.py                 # FastAPI: /sessions, /chat (SSE), /approve (HITL)
├── infra/
│   ├── Dockerfile
│   └── docker-compose.yml      # API + MinIO + Langfuse
├── packages/                   # symlink or copy of wbs_agent_kit
├── .env.example
└── requirements.txt
```

---

## Quick Start

### Option A: CLI

```bash
cp .env.example .env
# Fill in OPENAI_API_KEY or ANTHROPIC_API_KEY

pip install -r requirements.txt

# Interactive mode
python main.py --input ./input --output ./outputs

# One-shot mode
python main.py \
  --input  /path/to/requirements \
  --output /path/to/save \
  --project "My Project Name"
```

### Option B: Docker

```bash
cp .env.example .env
# Edit .env with your API keys

# Mount YOUR local output folder:
HOST_OUTPUT_DIR=/your/local/output/folder \
HOST_INPUT_DIR=/your/local/input/folder \
docker compose -f infra/docker-compose.yml up -d --build

# → API:           http://localhost:8000/docs
# → MinIO console: http://localhost:9001  (bnkadmin / bnkadmin123)
# → Langfuse:      http://localhost:3001
```

### Option C: API

```bash
# 1. Start server
python main.py --serve

# 2. Create session with custom output folder
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"project_name": "GEHP", "output_dir": "/my/output/folder"}'
# → {"session_id": "abc-123", ...}

# 3. Upload requirement files
curl -X POST http://localhost:8000/sessions/abc-123/files \
  -F "files=@requirement.pdf"

# 4. Chat (SSE stream)
curl -X POST http://localhost:8000/sessions/abc-123/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Tạo BRD và WBS cho project này nhé"}'

# 5. Change output folder at any time
curl -X POST http://localhost:8000/sessions/abc-123/output-dir \
  -H "Content-Type: application/json" \
  -d '{"output_dir": "/another/folder"}'

# 6. List generated files
curl http://localhost:8000/sessions/abc-123/outputs
```

---

## Model Configuration

Edit `config/agent_models.yaml` to change models **without touching Python**:

```yaml
# Use Claude for drafting (best quality)
brd_drafter_agent:
  model: anthropic:claude-sonnet-4-6

# Use GPT for cost-sensitive agents
critic_agent:
  model: openai:gpt-5.4-mini

# Use Gemini as alternative
# brd_drafter_agent:
#   model: google_genai:gemini-2.5-pro-preview-05-06
```

Or override per-session via env vars:
```bash
MODEL_BRD_DRAFTER=openai:gpt-4.1 python main.py
```

---

## Input Formats

| Format            | Tool           | Notes                              |
|-------------------|----------------|------------------------------------|
| `.pdf`            | `read_pdf`     | pypdf; text extraction             |
| `.docx`           | `read_docx`    | python-docx; preserves headings    |
| `.txt`, `.md`     | `read_txt`     | plain text                         |
| `.pptx`           | `read_pptx`    | titles + body + speaker notes      |
| `.xlsx`, `.xls`   | `read_xlsx`    | first 200 rows per sheet           |
| `.png`, `.jpg`…   | `describe_image` | vision LLM OCR + description    |

---

## Validation Error Codes

| Code                  | Description                                        |
|-----------------------|----------------------------------------------------|
| `FR_DUPLICATE_ID`     | Two FRs share the same id                          |
| `FR_EMPTY_DESCRIPTION`| FR description is empty                            |
| `FR_NUMBERING_GAP`    | FR ids are not contiguous (FR1, FR3 — missing FR2) |
| `NFR_NO_TARGET`       | NFR row has no measurable unit in target           |
| `BRD_MISSING_PURPOSE` | BRD purpose field is empty                         |
| `WBS_MISSING_PHASE`   | Setup/Development/Deploy phase missing             |
| `TASK_ZERO_EFFORT`    | L4 task has 0 BE and 0 FE man-days                 |
| `TRACE_UNCOVERED_FR`  | FR has no WBS task referencing it                  |
| `TRACE_ORPHAN_TASK`   | WBS task references non-existent FR id             |

---

## vs. bnk-agent (LangGraph version)

| Feature             | bnk-agent (LangGraph)         | bnk-deepagent (DeepAgents)     |
|---------------------|-------------------------------|--------------------------------|
| Framework           | LangGraph supervisor          | LangChain DeepAgents           |
| State               | TypedDict (MessagesState)     | Files on FilesystemBackend     |
| Routing             | `create_supervisor()`         | Orchestrator as DeepAgent      |
| Checkpointing       | AsyncPostgresSaver            | MemorySaver (+ optional PG)    |
| Persistence         | Postgres                      | FilesystemBackend + AGENTS.md  |
| Folder control      | OUTPUT_DIR env var            | Env var + API endpoint + CLI   |
| Sandbox support     | ✗                             | Modal, Runloop, Daytona        |
| Skills              | ✗                             | SKILL.md files                 |
| Memory              | scope_note in state           | AGENTS.md via MemoryMiddleware |
