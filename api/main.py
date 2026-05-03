"""api/main.py — BnK DeepAgent FastAPI server (deer-flow production pattern).

Architecture mirrors deer-flow:
  ThreadRecord  — per-thread metadata + agent reference (in-memory, swap to Redis)
  RunRecord     — per-run lifecycle (pending→running→succeeded/failed/interrupted)
  RunManager    — atomic create_or_reject with multitask strategies
  StreamBridge  — per-run SSE queue with heartbeat + Last-Event-ID reconnection

Endpoint surface:
  POST   /api/threads                              create thread
  GET    /api/threads/{id}                         get thread state + status
  DELETE /api/threads/{id}                         delete thread
  POST   /api/threads/{id}/uploads                 upload requirement files
  POST   /api/threads/{id}/runs/stream             SSE streaming run
  POST   /api/threads/{id}/runs/resume             HITL resume (Command(resume=...))
  DELETE /api/threads/{id}/runs/{run_id}           cancel a run
  GET    /api/threads/{id}/runs                    list runs for thread
  GET    /api/threads/{id}/runs/{run_id}           get single run status
  GET    /api/threads/{id}/outputs                 list generated artifacts
  GET    /api/threads/{id}/artifacts/{path}        download artifact
  GET    /api/models                               available LLM models
  GET    /health

SSE event types (deer-flow compatible):
  event: metadata   data: {"run_id": "...", "thread_id": "..."}
  event: messages   data: {"id": "...", "role": "...", "content": "...", "delta": true}
  event: values     data: {"messages": [...], "artifacts": [...], "step": "..."}
  event: hitl       data: {"tool": "...", "question": "...", "args": {...}, "run_id": "..."}
  event: end        data: {"usage": {...}, "run_id": "..."}
  event: error      data: {"message": "..."}
"""
from __future__ import annotations

import asyncio
import contextvars
import copy
import json
import logging
import os
import traceback
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Literal, Optional

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command
from pydantic import BaseModel
from dotenv import load_dotenv

# AG-UI / CopilotKit protocol
from ag_ui.core import (
    RunAgentInput,
    RunStartedEvent, RunFinishedEvent, RunErrorEvent,
    TextMessageStartEvent, TextMessageContentEvent, TextMessageEndEvent,
    ToolCallStartEvent, ToolCallArgsEvent, ToolCallEndEvent, ToolCallResultEvent,
    CustomEvent, StateSnapshotEvent, StepStartedEvent, StepFinishedEvent, EventType,
)
from ag_ui.encoder import EventEncoder

from infra.persistence import (
    init_persistence, close_persistence,
    get_checkpointer, get_store, is_memory_fallback,
)
from api.models import (
    DisconnectMode, RunRecord, RunStatus, ThreadRecord, ThreadStatus,
)
from api.run_manager import ConflictError, RunManager
from api.stream_bridge import StreamBridge, StreamEntry, RunStream, format_sse, _END, _HEARTBEAT
from api.thread_registry import ThreadRegistry

load_dotenv()
log = logging.getLogger(__name__)


# ── App-level singletons ──────────────────────────────────────────────────────
_bridge = StreamBridge()
_run_manager = RunManager()
_registry = ThreadRegistry()  # LangGraph Store-backed; survives restarts


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_persistence()
    if is_memory_fallback():
        log.warning(
            "In-memory persistence — checkpointer/store data lost on restart. "
            "Thread registry uses file fallback (workspace/_thread.json). "
            "Set DATABASE_URL for full production persistence."
        )
    else:
        log.info("Postgres-backed persistence active.")

    # Pre-warm thread registry from _thread.json files so existing threads
    # survive server restarts even without a database.
    loaded = await _registry.warm_cache_from_disk()
    if loaded:
        log.info("Restored %d thread(s) from disk into registry cache", loaded)

    try:
        yield
    finally:
        await close_persistence()


app = FastAPI(
    title="BnK Document Agent API",
    description="Multi-agent BRD + WBS generation — production-grade deer-flow pattern",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Length"],
)

# ── Serve web UI (Vite build → web/dist/, fallback to web/index.html) ─────────
_WEB_DIR  = Path(__file__).resolve().parent.parent / "web"
_DIST_DIR = _WEB_DIR / "dist"

# Mount Vite static assets when a build exists
if (_DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(_DIST_DIR / "assets")), name="vite-assets")

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def ui_root():
    # Prefer Vite build; fall back to legacy index.html for dev
    for candidate in (_DIST_DIR / "index.html", _WEB_DIR / "index.html"):
        if candidate.exists():
            return HTMLResponse(candidate.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Run: cd web && npm run build</h1>", status_code=503)


# ── Pydantic request/response models ─────────────────────────────────────────

class CreateThreadRequest(BaseModel):
    project_name: str
    input_dir: Optional[str] = None
    output_dir: Optional[str] = None
    model: Optional[str] = None
    language: str = "vi"


class CreateThreadResponse(BaseModel):
    thread_id: str
    project_name: str
    input_dir: str
    output_dir: str
    workspace_dir: str
    created_at: str


class RunRequest(BaseModel):
    message: str
    multitask_strategy: Literal["reject", "interrupt", "rollback"] = "reject"
    on_disconnect: Literal["cancel", "continue"] = "cancel"


class ResumeRequest(BaseModel):
    """Resume a HITL-interrupted run via LangGraph Command(resume=...)."""
    decision: Literal["approve", "reject", "edit"]
    edited_args: Optional[dict] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_thread(thread_id: str) -> ThreadRecord:
    t = await _registry.get(thread_id)
    if t is None:
        raise HTTPException(404, f"Thread {thread_id!r} not found")
    return t


def _thread_config(thread_id: str) -> dict:
    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 150,
        "run_name": f"bnk-{thread_id[:8]}",
        "tags": [f"thread:{thread_id}", "bnk-deepagent"],
        "metadata": {"thread_id": thread_id, "project": "bnk-deepagent"},
    }


def _load_json_file(path: Path, default):
    """Read a JSON file safely — repair if malformed, return default on failure."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            from json_repair import repair_json
            repaired = repair_json(text, return_objects=True, ensure_ascii=False)
            if repaired is not None and repaired != "" and repaired != {}:
                return repaired
        except Exception:
            pass
        return default


async def _derive_thread_status(thread_id: str) -> ThreadStatus:
    """Derive thread status from RunManager + LangGraph checkpointer."""
    if _run_manager.has_inflight(thread_id):
        return ThreadStatus.busy

    # Primary: use RunManager's last recorded run status.
    # CheckpointTuple has no .tasks attribute so the old checkpointer check
    # always returned idle even after HITL interrupts.
    last_run = _run_manager.current_run(thread_id)
    if last_run:
        from api.models import RunStatus
        if last_run.status == RunStatus.interrupted:
            return ThreadStatus.interrupted
        if last_run.status == RunStatus.failed:
            return ThreadStatus.error

    # Secondary: checkpointer-based check (survives process restarts)
    try:
        checkpointer = get_checkpointer()
        ckpt = await checkpointer.aget_tuple(_thread_config(thread_id))
        if ckpt is not None:
            pending = getattr(ckpt, "pending_writes", None) or []
            if any(k == "__error__" for _, k, _ in pending):
                return ThreadStatus.error
    except Exception:
        pass

    return ThreadStatus.idle


# ── Thread endpoints ──────────────────────────────────────────────────────────

@app.post("/api/threads", response_model=CreateThreadResponse)
async def create_thread(req: CreateThreadRequest):
    """Create a new document generation thread."""
    from orchestrator import create_orchestrator
    from tools.workspace import new_session_workspace

    thread_id = str(uuid.uuid4())
    ws = new_session_workspace(thread_id)

    # Per-thread input dir so uploaded files are isolated and the orchestrator
    # backend is configured with the correct path from creation time.
    base_input = req.input_dir or os.environ.get("ATTACHMENTS_DIR", "/tmp/bnk-input")
    input_dir  = str(Path(base_input) / thread_id)
    output_dir = req.output_dir or os.environ.get("OUTPUT_DIR", "/tmp/bnk-outputs")
    Path(input_dir).mkdir(parents=True, exist_ok=True)

    # Register paths in module-level registry so tools can always look them up
    # even when ContextVars don't propagate through LangGraph's task dispatch.
    from tools.workspace import register_thread
    register_thread(thread_id, input_dir, str(ws))

    agent = create_orchestrator(
        input_dir=input_dir,
        output_dir=output_dir,
        workspace_dir=str(ws.parent),
        model=req.model,
        checkpointer=get_checkpointer(),
        store=get_store(),
    )

    record = ThreadRecord(
        thread_id=thread_id,
        project_name=req.project_name,
        input_dir=input_dir,
        output_dir=output_dir,
        workspace=str(ws),
        language=req.language,
        model=req.model,
        agent=agent,
    )
    await _registry.save(record)

    return CreateThreadResponse(
        thread_id=thread_id,
        project_name=req.project_name,
        input_dir=input_dir,
        output_dir=output_dir,
        workspace_dir=str(ws),
        created_at=record.created_at,
    )


@app.get("/api/threads/{thread_id}")
async def get_thread(thread_id: str):
    """Return thread metadata, status, and document indices."""
    thread = await _get_thread(thread_id)
    ws = Path(thread.workspace)
    status = await _derive_thread_status(thread_id)

    brd_index   = ws / "brd" / "_index.json"
    wbs_index   = ws / "wbs" / "_index.json"
    issues_file = ws / "issues.json"
    design_file = ws / "technical_design.md"
    agents_file = ws / "AGENTS.md"

    # Surface the most recent run for the UI
    current_run = _run_manager.current_run(thread_id)

    return {
        **thread.to_dict(),
        "status": status.value,
        "current_run": current_run.to_dict() if current_run else None,
        "brd_index": _load_json_file(brd_index,   None) if brd_index.exists()   else None,
        "wbs_index": _load_json_file(wbs_index,   None) if wbs_index.exists()   else None,
        "issues":    _load_json_file(issues_file, [])   if issues_file.exists() else [],
        "has_technical_design": design_file.exists(),
        "agents_md": agents_file.read_text(encoding="utf-8") if agents_file.exists() else None,
    }


@app.delete("/api/threads/{thread_id}", status_code=200)
async def delete_thread(thread_id: str):
    """Remove thread from registry. Cancels any running run first."""
    await _get_thread(thread_id)
    current = _run_manager.current_run(thread_id)
    if current:
        await _run_manager.cancel(current.run_id)
    await _registry.delete(thread_id)
    return {"deleted": thread_id}


# ── File uploads ──────────────────────────────────────────────────────────────

@app.post("/api/threads/{thread_id}/uploads")
async def upload_files(thread_id: str, files: list[UploadFile] = File(...)):
    """Upload requirement files to the thread's input directory."""
    thread = await _get_thread(thread_id)
    input_dir = Path(thread.input_dir)
    input_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for f in files:
        dest = input_dir / f.filename
        dest.write_bytes(await f.read())
        saved.append(str(dest))

    return {"uploaded": saved, "input_dir": str(input_dir)}


# ── SSE streaming run ─────────────────────────────────────────────────────────

@app.post("/api/threads/{thread_id}/runs/stream")
async def stream_run(thread_id: str, req: RunRequest, request: Request):
    """Create a run and stream agent events via SSE.

    Honors multitask_strategy (reject/interrupt/rollback) and on_disconnect
    (cancel/continue) exactly like deer-flow.
    """
    await _get_thread(thread_id)

    disconnect_mode = (
        DisconnectMode.cancel if req.on_disconnect == "cancel"
        else DisconnectMode.continue_
    )

    try:
        run_record = await _run_manager.create_or_reject(
            thread_id,
            on_disconnect=disconnect_mode,
            multitask_strategy=req.multitask_strategy,
        )
    except ConflictError as e:
        raise HTTPException(409, str(e))

    stream = _bridge.create(run_record.run_id)

    # Pre-populate workspace ContextVars in a copied context BEFORE create_task
    # so the task (and all LangGraph sub-tasks) inherit the correct paths.
    thread_pre = await _registry.get(thread_id)
    from tools.workspace import setup_thread_context
    _ctx = contextvars.copy_context()
    _ctx.run(setup_thread_context, thread_id, thread_pre.input_dir, thread_pre.workspace, thread_pre.output_dir)

    # Launch agent in background — returns StreamingResponse immediately
    task = asyncio.create_task(
        _run_agent(thread_id, run_record.run_id, req.message, stream),
        context=_ctx,
    )
    run_record.task = task

    last_event_id = request.headers.get("Last-Event-ID")

    async def sse_generator() -> AsyncIterator[str]:
        yield format_sse("metadata", {
            "run_id": run_record.run_id,
            "thread_id": thread_id,
        })
        try:
            async for entry in stream.subscribe(last_event_id=last_event_id):
                if entry is _HEARTBEAT:
                    yield ": heartbeat\n\n"
                    continue
                if entry is _END:
                    break
                assert isinstance(entry, StreamEntry)
                yield format_sse(entry.event, entry.data, event_id=entry.id)
        finally:
            # on_disconnect: cancel run if client disconnects before stream ends
            if await request.is_disconnected():
                if disconnect_mode == DisconnectMode.cancel:
                    await _run_manager.cancel(run_record.run_id)
            _bridge.remove(run_record.run_id)

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Location": f"/api/threads/{thread_id}/runs/{run_record.run_id}",
        },
    )


async def _run_agent(
    thread_id: str,
    run_id: str,
    message: str,
    stream: RunStream,
) -> None:
    """Background task: execute the agent and publish events to RunStream."""
    thread = await _registry.get(thread_id)
    if thread is None:
        stream.put(StreamEntry("error", {"message": f"Thread {thread_id!r} not found"}))
        stream.end()
        return

    run_record = _run_manager.get(run_id)
    agent = thread.agent
    config = _thread_config(thread_id)
    usage: dict = {}

    # Bind workspace context vars so resolve_path("/input/") works in tool fns.
    from tools.workspace import set_input_dir, set_workspace
    set_input_dir(thread.input_dir)
    set_workspace(thread.workspace)

    _run_manager.set_status(run_id, RunStatus.running)

    # Capture pre-run checkpoint for potential rollback
    pre_run_snapshot: dict = {}
    try:
        checkpointer = get_checkpointer()
        ckpt_tuple = await checkpointer.aget_tuple(config)
        if ckpt_tuple is not None:
            pre_run_snapshot = {
                "checkpoint": copy.deepcopy(getattr(ckpt_tuple, "checkpoint", {})),
                "metadata":   copy.deepcopy(getattr(ckpt_tuple, "metadata", {})),
            }
    except Exception:
        pass

    def _read_agents_md(ws) -> str:
        """Read AGENTS.md from workspace; return empty string if missing."""
        p = Path(ws) / "AGENTS.md"
        try:
            return p.read_text(encoding="utf-8") if p.exists() else ""
        except OSError:
            return ""

    try:
        msg_buffer: dict[str, dict] = {}
        _last_agents_md_hash: str = ""

        async for chunk in agent.astream(
            {"messages": [{"role": "user", "content": message}]},
            config=config,
            stream_mode=["values", "messages"],
        ):
            # Check if run was aborted externally
            if run_record and run_record.abort_event.is_set():
                if run_record.abort_action == "rollback" and pre_run_snapshot:
                    await _restore_checkpoint(config, pre_run_snapshot)
                _run_manager.set_status(run_id, RunStatus.interrupted)
                stream.put(StreamEntry("error", {"message": "Run aborted by new request"}))
                stream.end()
                return

            # chunk is (mode, data) with multiple stream_modes
            if isinstance(chunk, tuple):
                mode, data = chunk
            else:
                mode, data = "values", chunk

            if mode == "messages":
                msg_chunk, meta = data if isinstance(data, tuple) else (data, {})
                msg_id   = getattr(msg_chunk, "id", None) or str(uuid.uuid4())
                msg_type = getattr(msg_chunk, "type", "")

                # ── Tool calls (LLM deciding to call a tool) ─────────────────
                tool_calls = getattr(msg_chunk, "tool_calls", None) or []
                tool_call_chunks = getattr(msg_chunk, "tool_call_chunks", None) or []

                for tc in tool_calls:
                    stream.put(StreamEntry("tool_calls", {
                        "id": tc.get("id", str(uuid.uuid4())),
                        "name": tc.get("name", ""),
                        "args": tc.get("args", {}),
                        "status": "running",
                    }))

                for tc in tool_call_chunks:
                    if tc.get("name"):  # first chunk has the name
                        stream.put(StreamEntry("tool_calls", {
                            "id": tc.get("id", str(uuid.uuid4())),
                            "name": tc.get("name", ""),
                            "args": tc.get("args", {}),
                            "status": "running",
                        }))

                # ── Tool result (ToolMessage) ─────────────────────────────────
                if msg_type == "tool":
                    tool_call_id = getattr(msg_chunk, "tool_call_id", None)
                    result_content = getattr(msg_chunk, "content", "")
                    if isinstance(result_content, list):
                        result_content = " ".join(
                            p.get("text", "") if isinstance(p, dict) else str(p)
                            for p in result_content
                        )
                    stream.put(StreamEntry("tool_results", {
                        "id": tool_call_id or str(uuid.uuid4()),
                        "content": str(result_content)[:500],
                        "status": "done",
                    }))
                    continue

                # ── Regular text delta ────────────────────────────────────────
                content = getattr(msg_chunk, "content", "")
                if not content:
                    continue

                if msg_id not in msg_buffer:
                    msg_buffer[msg_id] = {
                        "id": msg_id,
                        "role": getattr(msg_chunk, "type", "assistant"),
                        "content": "",
                    }
                delta = content if isinstance(content, str) else ""
                msg_buffer[msg_id]["content"] += delta

                stream.put(StreamEntry("messages", {
                    "id": msg_id,
                    "role": msg_buffer[msg_id]["role"],
                    "content": delta,
                    "delta": True,
                }))

            elif mode == "values":
                if not isinstance(data, dict):
                    continue

                # ── HITL interrupt detected ───────────────────────────────────
                if "__interrupt__" in data:
                    interrupt_val = data["__interrupt__"]
                    _run_manager.set_status(run_id, RunStatus.interrupted)

                    tool_name, question, args = _parse_interrupt(interrupt_val)

                    stream.put(StreamEntry("hitl", {
                        "tool": tool_name,
                        "question": question,
                        "args": args,
                        "run_id": run_id,
                    }))
                    stream.end()
                    return

                # ── Full state snapshot ───────────────────────────────────────
                messages_out = [
                    {
                        "id": getattr(m, "id", ""),
                        "role": getattr(m, "type", "assistant"),
                        "content": c if isinstance(c := getattr(m, "content", ""), str) else str(c),
                    }
                    for m in data.get("messages", [])
                    if getattr(m, "content", "")
                ]

                # Emit AGENTS.md when it changes (todo list updates)
                agents_md = _read_agents_md(thread.workspace)
                agents_md_hash = str(hash(agents_md))
                agents_md_payload = agents_md if agents_md_hash != _last_agents_md_hash and agents_md else None
                if agents_md_payload:
                    _last_agents_md_hash = agents_md_hash

                stream.put(StreamEntry("values", {
                    "messages": messages_out,
                    "artifacts": data.get("artifacts", []),
                    "step": data.get("current_step", ""),
                    **({"agents_md": agents_md_payload} if agents_md_payload else {}),
                }))

                if "usage" in data:
                    usage = data["usage"]

        _run_manager.set_status(run_id, RunStatus.succeeded)
        stream.put(StreamEntry("end", {"usage": usage, "run_id": run_id}))

    except asyncio.CancelledError:
        _run_manager.set_status(run_id, RunStatus.interrupted)
        stream.put(StreamEntry("error", {"message": "Run cancelled"}))
    except Exception as exc:
        tb = traceback.format_exc()
        log.exception("Agent run %s failed", run_id)
        _run_manager.set_error(run_id, str(exc))
        stream.put(StreamEntry("error", {"message": f"{exc}\n---\n{tb}"}))
    finally:
        stream.end()


async def _resume_agent(
    thread_id: str,
    run_id: str,
    resume_payload: dict,
    stream: RunStream,
) -> None:
    """Resume a HITL-interrupted graph via Command(resume=...) and stream events.

    Identical event shape to _run_agent so the frontend needs no changes.
    Uses the same _thread_config (same run_name + metadata) so LangSmith
    groups the resumed execution under the same thread trace rather than
    creating a new top-level session.
    """
    thread = await _registry.get(thread_id)
    if thread is None:
        stream.put(StreamEntry("error", {"message": f"Thread {thread_id!r} not found"}))
        stream.end()
        return

    run_record = _run_manager.get(run_id)
    agent = thread.agent
    config = _thread_config(thread_id)
    usage: dict = {}

    from tools.workspace import set_input_dir, set_workspace
    set_input_dir(thread.input_dir)
    set_workspace(thread.workspace)

    _run_manager.set_status(run_id, RunStatus.running)

    # resume_payload is already in HITLResponse format: {"decisions": [...]}
    # Pass it directly — DeepAgents does interrupt(hitl_request)["decisions"]
    resume_input = Command(resume=resume_payload)

    try:
        async for chunk in agent.astream(
            resume_input,
            config=config,
            stream_mode=["values", "messages"],
        ):
            if run_record and run_record.abort_event.is_set():
                _run_manager.set_status(run_id, RunStatus.interrupted)
                stream.put(StreamEntry("error", {"message": "Run aborted"}))
                stream.end()
                return

            if isinstance(chunk, tuple):
                mode, data = chunk
            else:
                mode, data = "values", chunk

            if mode == "messages":
                msg_chunk, _ = data if isinstance(data, tuple) else (data, {})
                msg_id   = getattr(msg_chunk, "id", None) or str(uuid.uuid4())

                tool_calls = getattr(msg_chunk, "tool_calls", None) or []
                for tc in tool_calls:
                    stream.put(StreamEntry("tool_calls", {
                        "tool": tc.get("name", ""),
                        "args": tc.get("args", {}),
                    }))

                content = getattr(msg_chunk, "content", "")
                if content and getattr(msg_chunk, "type", "") == "AIMessageChunk":
                    stream.put(StreamEntry("messages", {
                        "id": msg_id,
                        "role": "assistant",
                        "content": content,
                        "delta": True,
                    }))

            elif mode == "values":
                if not isinstance(data, dict):
                    continue

                if "__interrupt__" in data:
                    interrupt_val = data["__interrupt__"]
                    _run_manager.set_status(run_id, RunStatus.interrupted)
                    tool_name, question, args = _parse_interrupt(interrupt_val)
                    stream.put(StreamEntry("hitl", {
                        "tool": tool_name,
                        "question": question,
                        "args": args,
                        "run_id": run_id,
                    }))
                    stream.end()
                    return

                if "usage" in data:
                    usage = data["usage"]

        _run_manager.set_status(run_id, RunStatus.succeeded)
        stream.put(StreamEntry("end", {"usage": usage, "run_id": run_id}))

    except asyncio.CancelledError:
        _run_manager.set_status(run_id, RunStatus.interrupted)
        stream.put(StreamEntry("error", {"message": "Run cancelled"}))
    except Exception as exc:
        tb = traceback.format_exc()
        log.exception("Resume run %s failed", run_id)
        _run_manager.set_error(run_id, str(exc))
        stream.put(StreamEntry("error", {"message": f"{exc}\n---\n{tb}"}))
    finally:
        stream.end()


_HITL_QUESTIONS: dict[str, str] = {
    # ── Solution design ────────────────────────────────────────────────────────
    "confirm_diagram_generation": (
        "All 9 solution design steps are complete and the document is saved.\n"
        "Next: generate 3 architecture diagrams (system / component / deployment).\n"
        "  • system_architecture.drawio + .png — C4 Level-1 context diagram\n"
        "  • component.drawio + .png           — C4 Level-2 module diagram\n"
        "  • deployment.drawio + .png          — infrastructure tiers diagram\n"
        "Confirm to generate diagrams?"
    ),
    # ── Workflow runners ───────────────────────────────────────────────────────
    "run_wbs_workflow": (
        "Solution design is confirmed.\n"
        "Next: run WBS Workflow — decompose work, estimate effort, build Excel spreadsheet.\n"
        "This takes 30–90 seconds.\n"
        "Confirm to start WBS generation?"
    ),
    "run_brd_workflow": (
        "WBS spreadsheet is ready.\n"
        "Next: run BRD Workflow — draft the Business Requirements Document (.docx).\n"
        "This takes 30–90 seconds.\n"
        "Confirm to start BRD generation?"
    ),
    # ── Delivery planning ──────────────────────────────────────────────────────
    "confirm_delivery_milestones": (
        "Delivery plan has been computed based on WBS effort totals.\n"
        "Next: review the proposed milestone dates and confirm or adjust them.\n"
        "Confirm to proceed with these milestones?"
    ),
    # ── Export gates (inside workflows) ────────────────────────────────────────
    "render_wbs": (
        "WBS has passed validation.\n"
        "Next: export WBS to Excel (.xlsx).\n"
        "Confirm to export?"
    ),
    "render_brd": (
        "BRD has passed validation.\n"
        "Next: export BRD to Word (.docx).\n"
        "Confirm to export?"
    ),
}


def _parse_interrupt(interrupt_val: object) -> tuple[str, str, dict]:
    """Extract (tool_name, question, args) from a LangGraph / DeepAgents interrupt.

    DeepAgents HumanInTheLoopMiddleware fires interrupt() with a HITLRequest:
      {"action_requests": [{"name": tool_name, "args": {...}, "description": "..."}],
       "review_configs": [...]}

    Other shapes we also handle:
      • dict  {"tool": "...", "args": {...}}   ← bare dict shape
      • str   "run_wbs_workflow"               ← bare tool name
      • obj   with .tool_name / .name attrs    ← custom Interrupt subclass
    """
    def _as_dict(val: object) -> dict | None:
        """Normalise val to a plain dict via duck-typing. Returns None if impossible."""
        if isinstance(val, dict):
            return val
        # Pydantic v2
        if hasattr(val, "model_dump"):
            try:
                return val.model_dump()
            except Exception:
                pass
        # Pydantic v1 / dataclasses
        if hasattr(val, "__dict__"):
            try:
                return {k: v for k, v in vars(val).items() if not k.startswith("_")}
            except Exception:
                pass
        return None

    def _tool_from(obj: object) -> str:
        """Try every known attribute/key pattern, return '' if none found."""
        # Direct attribute on the Interrupt object itself
        for attr in ("tool_name", "name"):
            v = getattr(obj, attr, None)
            if v and isinstance(v, str):
                return v

        # .value field — the payload passed to interrupt()
        val = getattr(obj, "value", obj)   # fall back to obj itself if no .value
        if isinstance(val, str) and val:
            return val

        # Normalise to dict (handles plain dict, Pydantic v1/v2, dataclasses)
        d = _as_dict(val)
        if d:
            # DeepAgents HITLRequest: {"action_requests": [{"name": ...}]}
            ar = d.get("action_requests")
            if ar and isinstance(ar, (list, tuple)) and ar:
                first = ar[0]
                name = (
                    first.get("name", "") if isinstance(first, dict)
                    else getattr(first, "name", "") or ""
                )
                if name:
                    return str(name)
            for k in ("tool_name", "tool", "name", "function_name"):
                if d.get(k):
                    return str(d[k])

        # val is a Pydantic model — try action_requests attribute directly
        if val is not None and not isinstance(val, (str, dict)):
            ar = getattr(val, "action_requests", None)
            if ar:
                try:
                    ar_list = list(ar)
                    if ar_list:
                        first = ar_list[0]
                        name = (
                            first.get("name", "") if isinstance(first, dict)
                            else getattr(first, "name", "") or ""
                        )
                        if name:
                            return str(name)
                except Exception:
                    pass
            for attr in ("tool_name", "name"):
                v = getattr(val, attr, None)
                if v and isinstance(v, str):
                    return v

        return ""

    def _args_from(obj: object) -> dict:
        val = getattr(obj, "value", obj)
        d = _as_dict(val)
        if d:
            ar = d.get("action_requests")
            if ar and isinstance(ar, (list, tuple)) and ar:
                first = ar[0]
                return (
                    first.get("args") or {}
                    if isinstance(first, dict)
                    else _as_dict(getattr(first, "args", None)) or {}
                )
            return d.get("args") or d.get("kwargs") or d.get("input") or {}
        return getattr(obj, "args", {}) or {}

    items = list(interrupt_val) if isinstance(interrupt_val, (list, tuple)) else [interrupt_val]

    log.debug("_parse_interrupt raw: %r", interrupt_val)

    tool_name = ""
    args: dict = {}
    for item in items:
        name = _tool_from(item)
        if name:
            tool_name = name
            args = _args_from(item)
            break

    tool_name = tool_name or "unknown"
    question = _HITL_QUESTIONS.get(
        tool_name,
        f"Agent is at step: {tool_name}. Do you confirm to continue?"
    )
    log.info("_parse_interrupt → tool=%r  question=%s", tool_name, question[:60])
    return tool_name, question, args


async def _restore_checkpoint(config: dict, snapshot: dict) -> None:
    """Restore the pre-run checkpoint (rollback action)."""
    try:
        checkpointer = get_checkpointer()
        ckpt = snapshot.get("checkpoint", {})
        meta = snapshot.get("metadata", {})
        if ckpt:
            await checkpointer.aput(config, ckpt, meta, {})
            log.info("Rolled back checkpoint for thread %s", config["configurable"]["thread_id"])
    except Exception:
        log.exception("Rollback failed for config %s", config)


# ── Render-tool file extraction ───────────────────────────────────────────────

_RENDER_TOOLS: frozenset[str] = frozenset({
    # Inner sub-workflow tools (captured via SubWorkflowProgressCallback.on_tool_end)
    "render_wbs", "render_brd", "save_technical_design_md",
    # Diagram generation — each call emits .drawio + .png paths
    "generate_technical_design_diagram", "export_diagram_png",
    # Outer wrapper tools — fallback if the inner result bubbles up in the summary
    "run_wbs_workflow", "run_brd_workflow",
})


def _scan_output_for_new_files(output_dir: str, since: float) -> list[dict]:
    """Scan output_dir (and CWD-relative fallback) for .xlsx/.docx files newer than since."""
    results: list[dict] = []
    out_p = Path(output_dir)
    if not out_p.exists():
        # Try resolving relative path against CWD (e.g. OUTPUT_DIR="./outputs")
        out_p = (Path.cwd() / output_dir).resolve()
    if not out_p.exists():
        return results
    try:
        for p in out_p.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in (".xlsx", ".docx"):
                continue
            try:
                if p.stat().st_mtime >= since:
                    rel = str(p.relative_to(out_p))
                    results.append({
                        "name": p.name,
                        "path": rel,
                        "type": p.suffix.lstrip(".").upper(),
                        "source": "artifact",
                    })
            except (OSError, ValueError):
                pass
    except OSError:
        pass
    return results


def _resolve_path_str(
    path_str: str,
    output_dir: str,
    workspace: str,
) -> dict | None:
    """Resolve a single path string to a rendered-file dict, or None if unresolvable."""
    p = Path(path_str)
    if not p.is_absolute():
        suffix = p.suffix.lower()
        resolved: Path | None = None
        for base in [Path.cwd(), Path(output_dir) if output_dir else None, Path(workspace) if workspace else None]:
            if base is None:
                continue
            candidate = (base / p).resolve()
            if candidate.exists():
                resolved = candidate
                break
        if resolved is None:
            if suffix in (".xlsx", ".docx", ".pdf", ".png") and output_dir:
                resolved = (Path(output_dir).resolve() / p)
            elif workspace:
                resolved = (Path(workspace).resolve() / p)
            else:
                return None
        p = resolved

    out = Path(output_dir).resolve() if output_dir else None
    ws  = Path(workspace).resolve()  if workspace  else None

    for base, source in [(out, "artifact"), (ws, "workspace")]:
        if base is None:
            continue
        try:
            rel = str(p.relative_to(base))
            return {
                "name": p.name,
                "path": rel,
                "type": p.suffix.lstrip(".").upper() or "FILE",
                "source": source,
            }
        except ValueError:
            continue

    suffix = p.suffix.lower()
    return {
        "name": p.name,
        "path": path_str,
        "type": p.suffix.lstrip(".").upper() or "FILE",
        "source": "artifact" if suffix in (".xlsx", ".docx", ".pdf") else "workspace",
    }


def _extract_rendered_files(
    tool_name: str,
    result_content: str,
    output_dir: str,
    workspace: str,
) -> list[dict]:
    """Extract ALL file paths from a render-tool result.

    Returns a list of {"name", "path", "type", "source"} dicts (may be empty).
    For diagram tools (generate_technical_design_diagram) this returns both
    .drawio and .png so the frontend can show preview + download for each.
    """
    import re
    if tool_name not in _RENDER_TOOLS:
        return []
    patterns = [
        r'→\s*([^\s\n]+\.(?:xlsx|docx|md|drawio|pdf|png))',
        r'output=([^\s\n,)]+\.(?:xlsx|docx|md|drawio|pdf|png))',
        r'(?:saved|rendered|wrote)\s+(?:to\s+)?([^\s\n]+\.(?:xlsx|docx|md|drawio|pdf|png))',
        r'(/[^\s\n]+\.(?:xlsx|docx|md|drawio|pdf|png))',
    ]
    seen_paths: set[str] = set()
    raw_paths: list[str] = []
    for pat in patterns:
        for m in re.finditer(pat, result_content, re.IGNORECASE):
            raw = m.group(1).strip().rstrip(".,;)")
            if raw not in seen_paths:
                seen_paths.add(raw)
                raw_paths.append(raw)
        if raw_paths:
            break  # stop at first pattern that matches anything

    results: list[dict] = []
    seen_resolved: set[str] = set()
    for raw in raw_paths:
        fi = _resolve_path_str(raw, output_dir, workspace)
        if fi and fi["path"] not in seen_resolved:
            seen_resolved.add(fi["path"])
            results.append(fi)
    return results


def _extract_rendered_file(
    tool_name: str,
    result_content: str,
    output_dir: str,
    workspace: str,
) -> dict | None:
    """Compat wrapper — returns first file only. Use _extract_rendered_files for multi-file tools."""
    files = _extract_rendered_files(tool_name, result_content, output_dir, workspace)
    return files[0] if files else None


# ── HITL resume ───────────────────────────────────────────────────────────────

@app.post("/api/threads/{thread_id}/runs/resume")
async def resume_run(thread_id: str, req: ResumeRequest, request: Request):
    """Resume a HITL-interrupted run — streams SSE exactly like /runs/stream.

    Uses astream(Command(resume=...), config=_thread_config(thread_id)) so the
    resumed execution continues inside the SAME LangSmith trace (same run_name
    + thread_id metadata), rather than spawning a new top-level session.
    """
    await _get_thread(thread_id)
    status = await _derive_thread_status(thread_id)

    if status != ThreadStatus.interrupted:
        raise HTTPException(
            400,
            f"Thread is not interrupted (current status: {status.value}). "
            "Only interrupted threads can be resumed."
        )

    # Build HITLResponse in DeepAgents format: {"decisions": [ApproveDecision | RejectDecision]}
    # DeepAgents HumanInTheLoopMiddleware does: interrupt(hitl_request)["decisions"]
    extra = req.edited_args or {}
    feedback = extra.pop("feedback", None)
    if req.decision == "reject":
        decisions_list = [{"type": "reject", "message": feedback or "User rejected"}]
    else:
        approve: dict = {"type": "approve"}
        if feedback:
            approve["message"] = feedback
        decisions_list = [approve]
    resume_payload: dict = {"decisions": decisions_list}

    try:
        run_record = await _run_manager.create_or_reject(thread_id)
    except ConflictError as e:
        raise HTTPException(409, str(e))

    stream = _bridge.create(run_record.run_id)

    # Pre-populate workspace ContextVars before create_task (same as stream_run)
    _resume_thread = await _registry.get(thread_id)
    from tools.workspace import setup_thread_context
    _ctx = contextvars.copy_context()
    _ctx.run(setup_thread_context, thread_id, _resume_thread.input_dir, _resume_thread.workspace, _resume_thread.output_dir)

    task = asyncio.create_task(
        _resume_agent(thread_id, run_record.run_id, resume_payload, stream),
        context=_ctx,
    )
    run_record.task = task

    last_event_id = request.headers.get("Last-Event-ID")

    async def sse_generator() -> AsyncIterator[str]:
        yield format_sse("metadata", {
            "run_id": run_record.run_id,
            "thread_id": thread_id,
            "resumed": True,
        })
        try:
            async for entry in stream.subscribe(last_event_id=last_event_id):
                if entry is _HEARTBEAT:
                    yield ": heartbeat\n\n"
                    continue
                if entry is _END:
                    break
                assert isinstance(entry, StreamEntry)
                yield format_sse(entry.event, entry.data, event_id=entry.id)
        finally:
            if await request.is_disconnected():
                await _run_manager.cancel(run_record.run_id)
            _bridge.remove(run_record.run_id)

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── CopilotKit / AG-UI endpoint ──────────────────────────────────────────────

@app.post("/copilotkit")
async def copilotkit_stream(request: Request):
    """AG-UI / CopilotKit single-endpoint handler.

    CopilotKit first sends POST {"method": "info"} to discover agents,
    then sends RunAgentInput for actual streaming runs.

    Protocol:
      • Info pre-flight  — {"method": "info"} → agent registry JSON
      • New message      — RunAgentInput.messages[-1].content → astream
      • Resume HITL      — RunAgentInput.forwarded_props.command.resume → Command(resume=...)
    """
    envelope = await request.json()

    # CopilotKit wraps every request in an envelope:
    #   {"method": "info"|"agent/run"|..., "params": {...}, "body": {...}}
    # The actual RunAgentInput payload is always inside envelope["body"].
    method = envelope.get("method", "")
    run_body: dict = envelope.get("body", envelope)  # bare or enveloped

    # ── Info pre-flight ──────────────────────────────────────────────────────
    if method == "info":
        return {
            "mode": "sse",
            "agents": {
                "bnk_main_agent": {
                    "description": "BnK multi-agent BRD/WBS document generator",
                    "capabilities": {},
                }
            },
        }

    # ── Agent run ────────────────────────────────────────────────────────────
    try:
        input_data = RunAgentInput.model_validate(run_body)
    except Exception as exc:
        raise HTTPException(422, f"Invalid RunAgentInput: {exc}")

    thread_id = input_data.thread_id
    thread = await _registry.get(thread_id)
    if not thread:
        raise HTTPException(404, f"Thread {thread_id!r} not found")

    encoder = EventEncoder(accept=request.headers.get("accept"))
    run_id = input_data.run_id or str(uuid.uuid4())

    # Determine stream_input before launching task
    forwarded_props = dict(input_data.forwarded_props or {})
    resume_val = forwarded_props.get("command", {}).get("resume", None)

    if resume_val is not None:
        if isinstance(resume_val, str):
            try:
                resume_val = json.loads(resume_val)
            except json.JSONDecodeError:
                pass
        stream_input: dict | Command = Command(resume=resume_val)
        log.info("CopilotKit resume: thread=%s payload=%s", thread_id, resume_val)
    else:
        msgs = list(input_data.messages or [])
        last = msgs[-1] if msgs else None
        if last is None:
            content = ""
        elif hasattr(last, "content"):
            content = last.content or ""
        elif isinstance(last, dict):
            content = last.get("content", "")
        else:
            content = str(last)
        # CopilotKit sends an empty-messages request on mount to refresh agent state.
        # Detect this and return a no-op run (StartedEvent + FinishedEvent) immediately.
        if not content:
            log.info("CopilotKit state-refresh (empty msg): thread=%s — skipping agent run", thread_id)
            enc = EventEncoder(accept=request.headers.get("accept"))
            rid = run_id

            async def _noop_gen():
                yield enc.encode(RunStartedEvent(type=EventType.RUN_STARTED, thread_id=thread_id, run_id=rid))
                yield enc.encode(RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id=thread_id, run_id=rid))

            return StreamingResponse(
                _noop_gen(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
            )
        stream_input = {"messages": [{"role": "user", "content": content}]}
        log.info("CopilotKit new msg: thread=%s content=%r", thread_id, content[:80])

    # Pre-populate workspace ContextVars in a copied context before create_task
    # so the background task (and all LangGraph sub-tasks) inherit the correct paths.
    from tools.workspace import setup_thread_context
    from tools.progress import set_sub_progress_queue
    _ctx = contextvars.copy_context()
    _ctx.run(setup_thread_context, thread_id, thread.input_dir, thread.workspace, thread.output_dir)

    # Queue bridges background task → SSE generator; None sentinel = done.
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    # Sub-progress queue: WBS/BRD sync callbacks push tool-start/end events here.
    # threading.Queue is safe to write from thread and drain from async code.
    import queue as _tq
    _sub_q: _tq.Queue = _tq.Queue()
    _sub_progress_token = _ctx.run(set_sub_progress_queue, _sub_q)

    async def _run_ck() -> None:
        """Background task: run agent.astream() and enqueue encoded AG-UI events."""
        import time as _time
        agent  = thread.agent
        config = _thread_config(thread_id)

        # Record start time for the scan-fallback (new artifact detection)
        _run_start_time = _time.time()

        # Track open AG-UI text message for correct Start/End pairing
        current_msg_id: str | None = None
        # tool_call_id → parent AI message id
        tc_parent: dict[str, str] = {}
        # values-mode: msg_id → characters already sent as AG-UI deltas
        emitted_len: dict[str, int] = {}
        # Fully-emitted message IDs — never re-open or re-emit these
        emitted_msg_ids: set[str] = set()
        # MD5 hashes of full content already shown — catches re-ID'd duplicates
        # (DeepAgents copies sub-agent messages to parent state with new IDs)
        shown_content_hashes: set[str] = set()
        # step progress tracking for chat progress card
        completed_steps: list[str] = []
        active_tc_names: dict[str, str] = {}  # tc_id → tool_name
        # files rendered by render_wbs / render_brd / save_* tools
        rendered_files: list[dict] = []

        async def _close_msg() -> None:
            nonlocal current_msg_id
            if current_msg_id:
                await queue.put(encoder.encode(TextMessageEndEvent(
                    type=EventType.TEXT_MESSAGE_END,
                    message_id=current_msg_id,
                )))
                emitted_msg_ids.add(current_msg_id)
                current_msg_id = None

        async def _drain_sub_progress() -> None:
            """Drain sub-workflow progress events (WBS/BRD callback → threading.Queue)."""
            import queue as _tq
            while True:
                try:
                    item = _sub_q.get_nowait()
                except _tq.Empty:
                    break
                tool_name = item.get("tool", "")
                done = item.get("done", False)
                if done:
                    if tool_name and tool_name not in completed_steps:
                        completed_steps.append(tool_name)
                    # Extract rendered file from sub-workflow tool output
                    output_str = item.get("output", "")
                    if output_str and tool_name in _RENDER_TOOLS:
                        new_files = _extract_rendered_files(
                            tool_name, output_str,
                            thread.output_dir, thread.workspace,
                        )
                        known = {f["path"] for f in rendered_files}
                        for fi in new_files:
                            if fi["path"] not in known:
                                rendered_files.append(fi)
                                known.add(fi["path"])
                        if not new_files:
                            scanned = _scan_output_for_new_files(
                                thread.output_dir, _run_start_time,
                            )
                            known = {f["path"] for f in rendered_files}
                            for sf in scanned:
                                if sf["path"] not in known:
                                    rendered_files.append(sf)
                    await _emit_state()
                else:
                    await _emit_state(active_tool=tool_name)

        async def _emit_state(status: str = "running", active_tool: str | None = None) -> None:
            snapshot: dict = {
                "status": status,
                "completed_steps": completed_steps[-30:],
                "rendered_files": rendered_files,
            }
            if active_tool:
                snapshot["active_tool"] = active_tool
            await queue.put(encoder.encode(StateSnapshotEvent(
                type=EventType.STATE_SNAPSHOT,
                snapshot=snapshot,
            )))

        async def _heartbeat_drain() -> None:
            """Drain sub_q every 0.5 s so sub-workflow steps appear progressively.

            run_wbs_workflow / run_brd_workflow block the event loop for 30-90 s.
            Without this task the queue only drains after the tool returns, giving
            the user no feedback during the long wait.
            """
            try:
                while True:
                    await asyncio.sleep(0.5)
                    await _drain_sub_progress()
            except asyncio.CancelledError:
                pass

        hb_task = asyncio.create_task(_heartbeat_drain())

        try:
            log.info("CopilotKit astream starting: thread=%s", thread_id)
            _astream = agent.astream(
                stream_input,
                config=config,
                stream_mode=["values", "messages"],
            )
            try:
                async for chunk in _astream:
                    if isinstance(chunk, tuple):
                        mode, data = chunk
                    else:
                        mode, data = "values", chunk

                    # ── Messages mode: tool calls and streaming text deltas ──────
                    if mode == "messages":
                        msg_chunk, _ = data if isinstance(data, tuple) else (data, {})
                        msg_id   = getattr(msg_chunk, "id", None) or str(uuid.uuid4())
                        msg_type = getattr(msg_chunk, "type", "")

                        # Track tool calls internally — do NOT emit ToolCall* events to
                        # CopilotKit (they render "HOÀN TẤT" cards in chat). Progress is
                        # surfaced exclusively via StateSnapshotEvent → sidebar widget.
                        for tc in getattr(msg_chunk, "tool_calls", None) or []:
                            tc_id   = tc.get("id") or str(uuid.uuid4())
                            tc_name = tc.get("name") or ""
                            tc_parent[tc_id] = msg_id
                            active_tc_names[tc_id] = tc_name

                        if msg_type == "tool":
                            tcid = getattr(msg_chunk, "tool_call_id", None) or str(uuid.uuid4())
                            finished_name = active_tc_names.pop(tcid, "")
                            if finished_name:
                                completed_steps.append(finished_name)
                                # Extract rendered file from tool result
                                if finished_name in _RENDER_TOOLS:
                                    result_content = getattr(msg_chunk, "content", "")
                                    if isinstance(result_content, list):
                                        result_content = " ".join(
                                            p.get("text", "") if isinstance(p, dict) else str(p)
                                            for p in result_content
                                        )
                                    new_files = _extract_rendered_files(
                                        finished_name, str(result_content),
                                        thread.output_dir, thread.workspace,
                                    )
                                    known = {f["path"] for f in rendered_files}
                                    for fi in new_files:
                                        if fi["path"] not in known:
                                            rendered_files.append(fi)
                                            known.add(fi["path"])
                                    if not new_files:
                                        # Belt-and-suspenders: regex couldn't parse path —
                                        # scan output_dir for files created during this run
                                        scanned = _scan_output_for_new_files(
                                            thread.output_dir, _run_start_time,
                                        )
                                        for sf in scanned:
                                            if sf["path"] not in known:
                                                rendered_files.append(sf)
                                await _emit_state()
                            tc_parent.pop(tcid, None)
                            continue

                        # Text delta from messages-mode (OpenAI/streaming models)
                        delta_content = getattr(msg_chunk, "content", "")
                        if delta_content and isinstance(delta_content, str):
                            if current_msg_id != msg_id:
                                await _close_msg()
                                current_msg_id = msg_id
                                await queue.put(encoder.encode(TextMessageStartEvent(
                                    type=EventType.TEXT_MESSAGE_START,
                                    message_id=msg_id,
                                    role="assistant",
                                )))
                            await queue.put(encoder.encode(TextMessageContentEvent(
                                type=EventType.TEXT_MESSAGE_CONTENT,
                                message_id=msg_id,
                                delta=delta_content,
                            )))
                            emitted_len[msg_id] = emitted_len.get(msg_id, 0) + len(delta_content)

                    # ── Values mode: full state snapshots ────────────────────────
                    elif mode == "values":
                        if not isinstance(data, dict):
                            continue

                        if "__interrupt__" in data:
                            await _close_msg()
                            interrupt_val = data["__interrupt__"]
                            items = (
                                list(interrupt_val)
                                if isinstance(interrupt_val, (list, tuple))
                                else [interrupt_val]
                            )
                            for item in items:
                                raw_value = getattr(item, "value", item)
                                try:
                                    safe_value = json.loads(json.dumps(raw_value, default=str))
                                except Exception:
                                    safe_value = str(raw_value)
                                await queue.put(encoder.encode(CustomEvent(
                                    type=EventType.CUSTOM,
                                    name="on_interrupt",
                                    value=safe_value,
                                )))
                                log.info(
                                    "CopilotKit interrupt: thread=%s tool=%s",
                                    thread_id,
                                    safe_value.get("action_requests", [{}])[0].get("name", "?")
                                    if isinstance(safe_value, dict) else "?",
                                )
                            await queue.put(encoder.encode(RunFinishedEvent(
                                type=EventType.RUN_FINISHED,
                                thread_id=thread_id,
                                run_id=run_id,
                            )))
                            return

                        # Extract AI text from values-mode state snapshot.
                        # Claude/Anthropic delivers complete text here (not in messages-mode).
                        # Dedup strategy (two layers):
                        #   1. emitted_msg_ids: skip message IDs already fully emitted
                        #   2. shown_content_hashes: skip identical content under new IDs
                        #      (DeepAgents re-IDs sub-agent messages when copying to parent)
                        import hashlib
                        for msg in data.get("messages", []):
                            m_id   = getattr(msg, "id", None) or ""
                            m_type = getattr(msg, "type", "")
                            if m_type not in ("ai", "assistant"):
                                continue
                            # Layer 1: skip already-emitted message IDs
                            if m_id and m_id in emitted_msg_ids:
                                continue
                            m_content = getattr(msg, "content", "")
                            # Flatten list content blocks (Anthropic format)
                            if isinstance(m_content, list):
                                m_content = "".join(
                                    b.get("text", "") if isinstance(b, dict) and b.get("type") == "text"
                                    else str(b) if isinstance(b, str) else ""
                                    for b in m_content
                                )
                            if not m_content or not isinstance(m_content, str):
                                continue
                            # Layer 2: skip identical content (catches re-ID'd copies)
                            content_hash = hashlib.md5(
                                m_content.strip().encode(), usedforsecurity=False
                            ).hexdigest()
                            if content_hash in shown_content_hashes:
                                if m_id:
                                    emitted_msg_ids.add(m_id)
                                continue
                            # Check incremental delta (messages-mode may have sent part)
                            already_by_id = emitted_len.get(m_id, 0)
                            new_text = m_content[already_by_id:]
                            if not new_text:
                                if m_id:
                                    emitted_msg_ids.add(m_id)
                                continue
                            # Close any currently streaming message before opening new one
                            if current_msg_id and current_msg_id != m_id:
                                await _close_msg()
                            # values-mode messages are complete — send Start+Content+End atomically
                            actual_id = m_id or str(uuid.uuid4())
                            if not current_msg_id:
                                await queue.put(encoder.encode(TextMessageStartEvent(
                                    type=EventType.TEXT_MESSAGE_START,
                                    message_id=actual_id,
                                    role="assistant",
                                )))
                            await queue.put(encoder.encode(TextMessageContentEvent(
                                type=EventType.TEXT_MESSAGE_CONTENT,
                                message_id=actual_id,
                                delta=new_text,
                            )))
                            await queue.put(encoder.encode(TextMessageEndEvent(
                                type=EventType.TEXT_MESSAGE_END,
                                message_id=actual_id,
                            )))
                            shown_content_hashes.add(content_hash)
                            emitted_msg_ids.add(actual_id)
                            emitted_len[actual_id] = len(m_content)
                            current_msg_id = None  # message is fully closed

                        # Heartbeat: while any tool call is running (e.g. run_wbs_workflow
                        # which blocks 30–90 s), emit state snapshot so sidebar stays alive.
                        if active_tc_names:
                            current_active = list(active_tc_names.values())[-1]
                            await _emit_state(active_tool=current_active)

                    # Drain any sub-workflow progress events (WBS/BRD callback queue)
                    await _drain_sub_progress()

            finally:
                # Explicitly close the astream generator so Python doesn't close it at GC
                # time with an unhandled GeneratorExit that LangGraph logs as an error.
                try:
                    await _astream.aclose()
                except Exception:
                    pass

            # Normal completion — emit final state so frontend sees rendered_files
            await _close_msg()
            await _emit_state(status="done")
            log.info("CopilotKit astream done: thread=%s", thread_id)
            await queue.put(encoder.encode(RunFinishedEvent(
                type=EventType.RUN_FINISHED,
                thread_id=thread_id,
                run_id=run_id,
            )))

        except asyncio.CancelledError:
            await queue.put(encoder.encode(RunErrorEvent(
                type=EventType.RUN_ERROR,
                message="Run cancelled",
            )))
        except Exception as exc:
            log.exception("CopilotKit run failed for thread %s", thread_id)
            await queue.put(encoder.encode(RunErrorEvent(
                type=EventType.RUN_ERROR,
                message=str(exc),
            )))
        finally:
            hb_task.cancel()
            try:
                await hb_task
            except asyncio.CancelledError:
                pass
            await queue.put(None)  # sentinel — tells event_generator to stop

    task = asyncio.create_task(_run_ck(), context=_ctx)

    async def event_generator():
        yield encoder.encode(RunStartedEvent(
            type=EventType.RUN_STARTED,
            thread_id=thread_id,
            run_id=run_id,
        ))
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        except GeneratorExit:
            # Do NOT cancel the background task.
            # BRD/WBS workflows can run for several minutes — cancelling here
            # would throw GeneratorExit into LangGraph's astream mid-yield and
            # abort the workflow. Instead let the task run to completion so files
            # are saved to disk. The queue is unbounded, so _run_ck will drain it
            # and put the None sentinel when done; both are then GC'd normally.
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Run management endpoints ──────────────────────────────────────────────────

@app.get("/api/threads/{thread_id}/runs")
async def list_runs(thread_id: str):
    """List all runs for a thread (newest first)."""
    await _get_thread(thread_id)
    runs = _run_manager.list_by_thread(thread_id)
    return {
        "thread_id": thread_id,
        "runs": [r.to_dict() for r in runs],
    }


@app.get("/api/threads/{thread_id}/runs/{run_id}")
async def get_run(thread_id: str, run_id: str):
    """Get the status of a specific run."""
    await _get_thread(thread_id)
    record = _run_manager.get(run_id)
    if not record or record.thread_id != thread_id:
        raise HTTPException(404, f"Run {run_id!r} not found on thread {thread_id!r}")
    return record.to_dict()


@app.delete("/api/threads/{thread_id}/runs/{run_id}", status_code=200)
async def cancel_run(
    thread_id: str,
    run_id: str,
    action: Literal["interrupt", "rollback"] = "interrupt",
):
    """Cancel a running or pending run.

    action=interrupt  — stop execution, keep current checkpoint (resumable)
    action=rollback   — stop execution, restore pre-run checkpoint
    """
    await _get_thread(thread_id)
    cancelled = await _run_manager.cancel(run_id, action=action)
    if not cancelled:
        raise HTTPException(404, f"Run {run_id!r} not found or already terminal")
    return {"cancelled": run_id, "action": action}


# ── Artifacts ─────────────────────────────────────────────────────────────────

@app.get("/api/threads/{thread_id}/outputs")
async def list_outputs(thread_id: str):
    """List all generated artifact files for this thread."""
    thread = await _get_thread(thread_id)
    output_dir  = Path(thread.output_dir)
    project_dir = output_dir / thread.project_name.replace(" ", "_")

    if not project_dir.exists():
        return {"thread_id": thread_id, "artifacts": []}

    artifacts = [
        {
            "path": str(p.relative_to(output_dir)),
            "name": p.name,
            "type": p.suffix.lstrip(".").upper() or "FILE",
            "size_kb": round(p.stat().st_size / 1024, 1),
        }
        for p in sorted(project_dir.rglob("*"))
        if p.is_file()
    ]
    return {"thread_id": thread_id, "artifacts": artifacts}


@app.get("/api/threads/{thread_id}/artifacts/{artifact_path:path}")
async def download_artifact(thread_id: str, artifact_path: str):
    """Download a generated artifact file."""
    thread = await _get_thread(thread_id)
    full_path = Path(thread.output_dir) / artifact_path
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(404, f"Artifact {artifact_path!r} not found")
    # Encode filename for Content-Disposition (handles Vietnamese / spaces)
    from urllib.parse import quote
    encoded_name = quote(full_path.name, safe="")
    return FileResponse(
        path=str(full_path),
        filename=full_path.name,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=\"{full_path.name}\"; filename*=UTF-8''{encoded_name}",
        },
    )


@app.get("/api/threads/{thread_id}/workspace/{file_path:path}")
async def download_workspace_file(thread_id: str, file_path: str):
    """Download or preview a workspace file (technical_design.md, .drawio, .png, etc.).

    PNG and SVG are served inline (Content-Disposition: inline) so browsers can
    render them as images — suitable for <img src="..."> preview widgets.
    All other types are served as attachments (download).
    """
    thread = await _get_thread(thread_id)
    workspace = Path(thread.workspace)
    full_path = (workspace / file_path).resolve()
    # Prevent path traversal
    if not str(full_path).startswith(str(workspace.resolve())):
        raise HTTPException(403, "Path traversal not allowed")
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(404, f"Workspace file {file_path!r} not found")
    from urllib.parse import quote
    encoded_name = quote(full_path.name, safe="")
    suffix = full_path.suffix.lower()

    # Inline types: rendered in the browser (img src, iframe, fetch)
    _INLINE = {
        ".png":  "image/png",
        ".svg":  "image/svg+xml",
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".md":   "text/markdown; charset=utf-8",
    }
    # Attachment types: force download
    _ATTACHMENT = {
        ".drawio": "application/xml",
        ".docx":   "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx":   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }

    if suffix in _INLINE:
        return FileResponse(
            path=str(full_path),
            media_type=_INLINE[suffix],
            headers={
                "Content-Disposition": f"inline; filename=\"{full_path.name}\"; filename*=UTF-8''{encoded_name}",
                "Cache-Control": "no-cache",
            },
        )

    media_type = _ATTACHMENT.get(suffix, "application/octet-stream")
    return FileResponse(
        path=str(full_path),
        filename=full_path.name,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename=\"{full_path.name}\"; filename*=UTF-8''{encoded_name}",
        },
    )


@app.get("/api/threads/{thread_id}/diagrams")
async def list_diagrams(thread_id: str):
    """List generated architecture diagrams in workspace/diagrams/.

    Returns preview URL (inline PNG) and download URL (.drawio) for each diagram.
    """
    thread = await _get_thread(thread_id)
    diagrams_dir = Path(thread.workspace) / "diagrams"

    if not diagrams_dir.exists():
        return {"thread_id": thread_id, "diagrams": []}

    base_url = f"/api/threads/{thread_id}/workspace/diagrams"
    items: list[dict] = []

    for drawio_file in sorted(diagrams_dir.glob("*.drawio")):
        stem = drawio_file.stem
        png_file = diagrams_dir / f"{stem}.png"
        entry: dict = {
            "name": stem,
            "drawio": {
                "path": f"diagrams/{drawio_file.name}",
                "url": f"{base_url}/{drawio_file.name}",
                "size_kb": round(drawio_file.stat().st_size / 1024, 1),
            },
        }
        if png_file.exists():
            entry["png"] = {
                "path": f"diagrams/{png_file.name}",
                "url": f"{base_url}/{png_file.name}",
                "size_kb": round(png_file.stat().st_size / 1024, 1),
                "preview_url": f"{base_url}/{png_file.name}",
            }
        items.append(entry)

    return {"thread_id": thread_id, "diagrams": items}


# ── Models + Health ───────────────────────────────────────────────────────────

@app.get("/api/models")
async def list_models():
    from packages.config import get_agent_model
    agents = [
        "orchestrator", "intake_agent", "solution_finder_agent",
        "brd_drafter_agent", "wbs_estimator_agent", "critic_agent", "exporter_agent",
    ]
    return {"models": {a: get_agent_model(a) for a in agents}}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "3.0.0",
        "threads": _registry.count(),
        "runs": {
            "total": len(_run_manager._runs),
            "inflight": sum(
                1 for r in _run_manager._runs.values()
                if r.status in (RunStatus.pending, RunStatus.running)
            ),
        },
        "persistence": "memory" if is_memory_fallback() else "postgres",
    }


# ── Backward-compat aliases (/sessions → /api/threads) ───────────────────────

class _LegacyChatRequest(BaseModel):
    message: str

class _LegacyApproveRequest(BaseModel):
    tool_name: str
    decision: str
    edited_args: Optional[dict] = None


@app.post("/sessions")
async def _compat_create_session(req: CreateThreadRequest):
    return await create_thread(req)


@app.post("/sessions/{session_id}/chat")
async def _compat_chat(session_id: str, req: _LegacyChatRequest, request: Request):
    return await stream_run(session_id, RunRequest(message=req.message), request)


@app.post("/sessions/{session_id}/approve")
async def _compat_approve(session_id: str, req: _LegacyApproveRequest):
    decision = req.decision if req.decision in ("approve", "reject", "edit") else "approve"
    return await resume_run(
        session_id,
        ResumeRequest(decision=decision, edited_args=req.edited_args),  # type: ignore[arg-type]
    )


@app.get("/sessions/{session_id}/outputs")
async def _compat_outputs(session_id: str):
    return await list_outputs(session_id)


# ── SPA fallback — serve React app for all non-API routes ────────────────────

@app.get("/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
async def spa_fallback(full_path: str):
    for candidate in (_DIST_DIR / "index.html", _WEB_DIR / "index.html"):
        if candidate.exists():
            return HTMLResponse(candidate.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Run: cd web && npm run build</h1>", status_code=503)


# ── Module-level export so thread_registry can be used in tests ───────────────

def get_registry() -> ThreadRegistry:
    return _registry
