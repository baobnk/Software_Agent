"""api/models.py — Data models for BnK DeepAgent API (deer-flow pattern).

Mirrors deer-flow's RunRecord / RunStatus / DisconnectMode so the client-side
SDK and UI patterns are compatible.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Enums ─────────────────────────────────────────────────────────────────────

class RunStatus(str, Enum):
    pending     = "pending"
    running     = "running"
    succeeded   = "succeeded"
    failed      = "failed"
    interrupted = "interrupted"


class DisconnectMode(str, Enum):
    cancel    = "cancel"    # Abort agent when SSE client disconnects
    continue_ = "continue"  # Keep agent running after disconnect


class ThreadStatus(str, Enum):
    idle        = "idle"        # No active run, not interrupted
    busy        = "busy"        # Run currently in progress
    interrupted = "interrupted" # Paused at HITL checkpoint
    error       = "error"       # Last run failed


# ── RunRecord ─────────────────────────────────────────────────────────────────

@dataclass
class RunRecord:
    """Tracks a single agent execution lifecycle (mirrors deer-flow RunRecord)."""
    run_id: str
    thread_id: str
    status: RunStatus = RunStatus.pending

    # Disconnect/abort behavior
    on_disconnect: DisconnectMode = DisconnectMode.cancel
    abort_action: str = "interrupt"  # "interrupt" | "rollback"

    # Multitask conflict resolution
    multitask_strategy: str = "reject"  # "reject" | "interrupt" | "rollback"

    # Timestamps (ISO 8601)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    # Runtime references (not serialized)
    task: asyncio.Task | None = field(default=None, repr=False)
    abort_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    # Error message if status == failed
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "thread_id": self.thread_id,
            "status": self.status.value,
            "multitask_strategy": self.multitask_strategy,
            "on_disconnect": self.on_disconnect.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
        }


# ── ThreadRecord ──────────────────────────────────────────────────────────────

@dataclass
class ThreadRecord:
    """Thread registry entry — metadata persisted in Store, agent recreated on cache miss."""
    thread_id: str
    project_name: str
    input_dir: str
    output_dir: str
    workspace: str
    language: str
    agent: Any  # compiled DeepAgent graph (not serialized)

    # Optional: remembered so agent can be recreated after restart
    model: str | None = None

    # Runtime state
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "thread_id": self.thread_id,
            "project_name": self.project_name,
            "input_dir": self.input_dir,
            "output_dir": self.output_dir,
            "workspace": self.workspace,
            "language": self.language,
            "model": self.model,
            "created_at": self.created_at,
        }

    def to_store_dict(self) -> dict:
        """Serializable metadata for persistent Store (excludes agent object)."""
        return {
            "thread_id": self.thread_id,
            "project_name": self.project_name,
            "input_dir": self.input_dir,
            "output_dir": self.output_dir,
            "workspace": self.workspace,
            "language": self.language,
            "model": self.model,
            "created_at": self.created_at,
        }
