"""api/run_manager.py — Thread-safe run lifecycle manager (deer-flow pattern).

Responsibilities:
  - Create RunRecord and enforce per-thread multitask strategy
  - Track run status transitions
  - Cancel/abort running tasks (interrupt or rollback action)
  - Serve as the single source of truth for in-flight runs

Multitask strategies (when a new run arrives while one is already running):
  reject     → raise ConflictError (default, safest)
  interrupt  → cancel current run, preserve checkpoint, start new run
  rollback   → cancel current run, restore pre-run checkpoint, start new run
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from api.models import DisconnectMode, RunRecord, RunStatus

log = logging.getLogger(__name__)


class ConflictError(Exception):
    """Raised when multitask_strategy=reject and thread already has an inflight run."""


class RunManager:
    """In-memory run registry with thread-safe mutations."""

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._lock = asyncio.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    async def create_or_reject(
        self,
        thread_id: str,
        *,
        on_disconnect: DisconnectMode = DisconnectMode.cancel,
        multitask_strategy: str = "reject",
    ) -> RunRecord:
        """Atomically check for inflight runs and create a new RunRecord.

        Raises ConflictError if multitask_strategy="reject" and an inflight run exists.
        For "interrupt"/"rollback" strategies, signals existing runs to abort first.
        """
        async with self._lock:
            inflight = self._inflight(thread_id)

            if inflight:
                if multitask_strategy == "reject":
                    raise ConflictError(
                        f"Thread {thread_id!r} already has an active run. "
                        "Use multitask_strategy='interrupt' to override."
                    )
                # Cancel all inflight runs for this thread
                for record in inflight:
                    log.info(
                        "Aborting run %s (strategy=%s) for new run on thread %s",
                        record.run_id, multitask_strategy, thread_id,
                    )
                    record.abort_action = multitask_strategy  # "interrupt" | "rollback"
                    record.abort_event.set()

            record = RunRecord(
                run_id=str(uuid.uuid4()),
                thread_id=thread_id,
                status=RunStatus.pending,
                on_disconnect=on_disconnect,
                multitask_strategy=multitask_strategy,
            )
            self._runs[record.run_id] = record
            return record

    def set_status(self, run_id: str, status: RunStatus) -> None:
        record = self._runs.get(run_id)
        if record:
            record.status = status
            record.updated_at = datetime.now(timezone.utc).isoformat()

    def set_error(self, run_id: str, error: str) -> None:
        record = self._runs.get(run_id)
        if record:
            record.error = error
            record.status = RunStatus.failed
            record.updated_at = datetime.now(timezone.utc).isoformat()

    async def cancel(self, run_id: str, action: str = "interrupt") -> bool:
        """Signal a run to abort. Returns True if found and signal sent."""
        record = self._runs.get(run_id)
        if not record:
            return False
        if record.status not in (RunStatus.pending, RunStatus.running):
            return False
        record.abort_action = action
        record.abort_event.set()
        if record.task and not record.task.done():
            record.task.cancel()
        self.set_status(run_id, RunStatus.interrupted)
        return True

    def get(self, run_id: str) -> RunRecord | None:
        return self._runs.get(run_id)

    def list_by_thread(self, thread_id: str) -> list[RunRecord]:
        """Return runs for a thread, newest first."""
        runs = [r for r in self._runs.values() if r.thread_id == thread_id]
        return sorted(runs, key=lambda r: r.created_at, reverse=True)

    def has_inflight(self, thread_id: str) -> bool:
        return bool(self._inflight(thread_id))

    def current_run(self, thread_id: str) -> RunRecord | None:
        """Return the most recent non-terminal run for this thread."""
        inflight = self._inflight(thread_id)
        if inflight:
            return inflight[0]
        # Fall back to the most recent run of any status
        runs = self.list_by_thread(thread_id)
        return runs[0] if runs else None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _inflight(self, thread_id: str) -> list[RunRecord]:
        return [
            r for r in self._runs.values()
            if r.thread_id == thread_id
            and r.status in (RunStatus.pending, RunStatus.running)
        ]
