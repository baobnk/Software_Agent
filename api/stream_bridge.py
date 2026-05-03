"""api/stream_bridge.py — In-memory SSE stream bridge (deer-flow pattern).

Each run gets a dedicated asyncio.Queue.  The agent worker puts StreamEntry
objects; the SSE consumer yields them as SSE frames.  Supports heartbeat and
reconnection via Last-Event-ID.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Any

# Sentinels
_END = object()
_HEARTBEAT = object()

HEARTBEAT_INTERVAL = 15  # seconds


@dataclass
class StreamEntry:
    event: str
    data: Any
    id: str = field(default_factory=lambda: str(int(time.monotonic_ns())))


class RunStream:
    """Queue for a single run's SSE events."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()
        self._history: list[StreamEntry] = []

    def put(self, entry: StreamEntry) -> None:
        self._history.append(entry)
        self._queue.put_nowait(entry)

    def end(self) -> None:
        self._queue.put_nowait(_END)

    async def subscribe(
        self,
        last_event_id: str | None = None,
        heartbeat_interval: int = HEARTBEAT_INTERVAL,
    ) -> AsyncIterator[StreamEntry | object]:
        # Replay missed events if reconnecting
        if last_event_id is not None:
            ids = [e.id for e in self._history]
            if last_event_id in ids:
                start = ids.index(last_event_id) + 1
                for entry in self._history[start:]:
                    yield entry

        while True:
            try:
                entry = await asyncio.wait_for(
                    self._queue.get(), timeout=heartbeat_interval
                )
            except asyncio.TimeoutError:
                yield _HEARTBEAT
                continue

            if entry is _END:
                yield _END
                return
            yield entry


class StreamBridge:
    """Registry of per-run RunStream instances."""

    def __init__(self) -> None:
        self._streams: dict[str, RunStream] = {}

    def create(self, run_id: str) -> RunStream:
        stream = RunStream()
        self._streams[run_id] = stream
        return stream

    def get(self, run_id: str) -> RunStream | None:
        return self._streams.get(run_id)

    def remove(self, run_id: str) -> None:
        self._streams.pop(run_id, None)


# ── SSE frame formatting ──────────────────────────────────────────────────────

def format_sse(event: str, data: Any, *, event_id: str | None = None) -> str:
    """Format a single SSE frame."""
    payload = json.dumps(data, default=str, ensure_ascii=False)
    parts = [f"event: {event}", f"data: {payload}"]
    if event_id:
        parts.append(f"id: {event_id}")
    parts.append("")
    return "\n".join(parts) + "\n"
