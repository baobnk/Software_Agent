"""Workspace context — session-scoped directory for intermediate state files.

Every tool reads/writes JSON through here so Pydantic validation is guaranteed
and agents never corrupt each other across concurrent sessions.
"""
from __future__ import annotations

import contextvars
import json
import os
import uuid
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel
from loguru import logger as _log

T = TypeVar("T", bound=BaseModel)
_ws_log = _log.bind(ctx="workspace")

_ws_var: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "bnk_workspace", default=None
)
_input_dir_var: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "bnk_input_dir", default=None
)
_output_dir_var: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "bnk_output_dir", default=None
)
# When --input is a single file, store just that filename so list_input_files
# returns only that one file instead of scanning the whole parent directory.
_input_single_file_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "bnk_input_single_file", default=None
)

# Module-level fallback registry: {thread_id: input_dir_path}
# Populated by register_thread() at thread creation and run time so tools
# can find the correct paths even when ContextVars don't propagate through
# LangGraph's internal task/thread dispatch.
_thread_input_registry: dict[str, Path] = {}
_thread_ws_registry: dict[str, Path] = {}

# ContextVar for the active thread_id — set before asyncio.create_task so it
# is definitely inherited even when _input_dir_var/_ws_var are set later.
_active_thread_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "bnk_active_thread_id", default=None
)

# ── Public API ────────────────────────────────────────────────────────────────

def register_thread(thread_id: str, input_dir: str | Path, workspace: str | Path) -> None:
    """Register thread paths in module-level registry.

    Call at thread creation time so the registry is populated for the lifetime
    of the process — even if ContextVars fail to propagate inside LangGraph.
    """
    _thread_input_registry[thread_id] = Path(input_dir).resolve()
    _thread_ws_registry[thread_id] = Path(workspace).resolve()


def setup_thread_context(
    thread_id: str,
    input_dir: str | Path,
    workspace: str | Path,
    output_dir: str | Path | None = None,
) -> None:
    """Set all workspace ContextVars AND register in module-level registry.

    Designed to be called via contextvars.copy_context().run(...) BEFORE
    asyncio.create_task() so the pre-populated context is inherited by the
    task and all sub-tasks created by LangGraph/DeepAgents.
    """
    resolved_input = Path(input_dir).resolve()
    resolved_ws = Path(workspace).resolve()
    register_thread(thread_id, resolved_input, resolved_ws)
    _input_dir_var.set(resolved_input)
    _ws_var.set(resolved_ws)
    _active_thread_id_var.set(thread_id)
    if output_dir is not None:
        _output_dir_var.set(Path(output_dir).resolve())
    _ws_log.info(f"Thread context: {thread_id} | input={resolved_input} | ws={resolved_ws}")


def set_workspace(path: str | Path) -> None:
    resolved = Path(path).resolve()
    _ws_var.set(resolved)
    _ws_log.info(f"Workspace → {resolved}")


def set_output_dir_ctx(path: str | Path) -> None:
    """Set the per-thread output directory ContextVar (not the global env var)."""
    resolved = Path(path).resolve()
    _output_dir_var.set(resolved)
    _ws_log.info(f"Output dir → {resolved}")


def get_output_dir() -> Path:
    """Return per-thread output dir from ContextVar, falling back to OUTPUT_DIR env var."""
    od = _output_dir_var.get()
    if od is not None:
        return od
    return Path(os.environ.get("OUTPUT_DIR", "/tmp/bnk-outputs")).resolve()


def set_input_dir(path: str | Path) -> None:
    """Set input directory. If path is a FILE, use its parent and store the filename filter."""
    resolved = Path(path).resolve()
    if resolved.is_file():
        _input_dir_var.set(resolved.parent)
        _input_single_file_var.set(resolved.name)
        _ws_log.info(f"Input file → {resolved}  (dir={resolved.parent})")
    else:
        _input_dir_var.set(resolved)
        _input_single_file_var.set(None)
        _ws_log.info(f"Input dir  → {resolved}")


def get_input_dir() -> Path | None:
    return _input_dir_var.get()


def get_input_single_file() -> str | None:
    """Return single filename filter, or None if whole directory is in scope."""
    return _input_single_file_var.get()


def resolve_path(path_str: str) -> Path:
    """Resolve a path, translating /input/ virtual prefix to real input dir.

    Handles trailing-slash variants: /input/, /input, /input/foo.pdf

    Fallback chain (most to least reliable):
      1. _input_dir_var ContextVar (set via setup_thread_context before task creation)
      2. Module-level registry keyed by _active_thread_id_var ContextVar
      3. ATTACHMENTS_DIR env var (wrong for multi-session, last resort)
    """
    s = path_str.rstrip("/")
    if s == "/input" or s.startswith("/input/"):
        # 1. ContextVar — fastest, set by setup_thread_context before task creation
        input_dir: Path | None = get_input_dir()

        # 2. Module-level registry via thread_id ContextVar
        if input_dir is None:
            thread_id = _active_thread_id_var.get()
            if thread_id and thread_id in _thread_input_registry:
                input_dir = _thread_input_registry[thread_id]
                _ws_log.warning(
                    f"resolve_path: using registry fallback for thread {thread_id} → {input_dir}"
                )

        # 3. Env var (no per-thread path, but better than returning /input literally)
        if input_dir is None:
            env_base = os.environ.get("ATTACHMENTS_DIR", "/tmp/bnk-input")
            input_dir = Path(env_base).resolve()
            _ws_log.warning(
                f"resolve_path: ContextVar unset, falling back to env ATTACHMENTS_DIR={input_dir}"
            )

        relative = s[len("/input"):].lstrip("/")
        return input_dir / relative if relative else input_dir
    return Path(path_str)


def get_workspace() -> Path:
    ws = _ws_var.get()
    # Fallback: look up module-level registry via thread_id ContextVar
    if ws is None:
        thread_id = _active_thread_id_var.get()
        if thread_id and thread_id in _thread_ws_registry:
            ws = _thread_ws_registry[thread_id]
            _ws_log.warning(f"get_workspace: using registry fallback for thread {thread_id}")
    if ws is None:
        base = Path(os.environ.get("WORKSPACE_BASE_DIR", "/tmp/bnk-workspace")).resolve()
        ws = base / str(uuid.uuid4())
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def new_session_workspace(session_id: str | None = None) -> Path:
    """Create a new session workspace and bind it to the current context."""
    base = Path(os.environ.get("WORKSPACE_BASE_DIR", "/tmp/bnk-workspace")).resolve()
    sid = session_id or str(uuid.uuid4())
    ws = base / sid
    ws.mkdir(parents=True, exist_ok=True)
    _ws_var.set(ws)
    return ws


# ── File helpers ──────────────────────────────────────────────────────────────

def _state_path(filename: str) -> Path:
    return get_workspace() / filename


def read_json(filename: str) -> dict[str, Any] | None:
    p = _state_path(filename)
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        # Try to salvage the file with json_repair before giving up.
        try:
            from json_repair import repair_json
            repaired = repair_json(text, return_objects=True, ensure_ascii=False)
            if isinstance(repaired, dict):
                _ws_log.warning("read_json: repaired corrupt JSON in {}", p.name)
                return repaired
        except Exception:
            pass
        # Unrecoverable — rename so the agent doesn't loop on it.
        corrupt = p.with_suffix(p.suffix + ".corrupt")
        try:
            p.rename(corrupt)
        except OSError:
            pass
        _ws_log.warning(
            "read_json: unrecoverable JSON in {} ({}); renamed to {}",
            p.name, exc, corrupt.name,
        )
        return None


def _atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically using a unique temp file + rename.

    Uses a UUID-suffixed temp file to avoid races when concurrent tool calls
    write the same target file simultaneously (common in LangGraph thread pools).
    """
    tmp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def write_json(filename: str, data: dict[str, Any]) -> None:
    _atomic_write(
        _state_path(filename),
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
    )


def read_model(filename: str, model_cls: type[T]) -> T | None:
    raw = read_json(filename)
    if raw is None:
        return None
    return model_cls.model_validate(raw)


def write_model(filename: str, model: BaseModel) -> None:
    write_json(filename, model.model_dump(mode="json"))


def read_text(filename: str) -> str:
    p = _state_path(filename)
    return p.read_text(encoding="utf-8") if p.exists() else ""


def write_text(filename: str, content: str) -> None:
    _atomic_write(_state_path(filename), content)


# ── Well-known filenames ──────────────────────────────────────────────────────

BRD_STATE_FILE   = "brd_state.json"
WBS_STATE_FILE   = "wbs_state.json"
ISSUES_FILE      = "issues.json"
SCOPE_NOTE_FILE  = "scope_note.md"
RAW_FEATURES_FILE = "raw_features.md"
