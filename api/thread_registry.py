"""api/thread_registry.py — Thread registry: hot cache + LangGraph Store + file fallback.

Three-tier persistence (fastest to most durable):

  1. Hot cache      — in-memory dict, fastest, lost on restart
  2. LangGraph Store— Postgres-backed when DATABASE_URL is set (survives restarts)
  3. File fallback  — workspace/{thread_id}/_thread.json (always written, no DB needed)

On a cache miss the registry tries tier 2 then tier 3, recreates the agent
from the saved metadata, and warms the cache.

`warm_cache_from_disk()` is called once at server startup to pre-load all
threads from tier 3 so requests don't need a per-thread restore on the first hit.

Namespace: ("threads", thread_id)  key: "metadata"
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from api.models import ThreadRecord

log = logging.getLogger(__name__)


class ThreadRegistry:
    """Thread registry: hot in-memory cache + LangGraph Store + file fallback."""

    def __init__(self) -> None:
        self._cache: dict[str, ThreadRecord] = {}
        self._workspace_base = Path(
            os.environ.get("WORKSPACE_BASE_DIR", "/tmp/bnk-workspace")
        ).resolve()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _meta_path(self, thread_id: str) -> Path:
        return self._workspace_base / thread_id / "_thread.json"

    def _write_file(self, record: ThreadRecord) -> None:
        """Write thread metadata to workspace/{thread_id}/_thread.json."""
        try:
            path = self._meta_path(record.thread_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(record.to_store_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            log.debug("File write failed for thread %s", record.thread_id, exc_info=True)

    def _read_file(self, thread_id: str) -> dict | None:
        """Read thread metadata from workspace/{thread_id}/_thread.json."""
        try:
            path = self._meta_path(thread_id)
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            log.debug("File read failed for thread %s", thread_id, exc_info=True)
        return None

    async def _build_record(self, thread_id: str, meta: dict) -> ThreadRecord | None:
        """Recreate ThreadRecord + agent from persisted metadata."""
        try:
            from infra.persistence import get_checkpointer, get_store
            from orchestrator import create_orchestrator

            agent = create_orchestrator(
                input_dir=meta["input_dir"],
                output_dir=meta["output_dir"],
                workspace_dir=meta["workspace"],
                model=meta.get("model"),
                checkpointer=get_checkpointer(),
                store=get_store(),
            )
            record = ThreadRecord(
                thread_id=thread_id,
                project_name=meta["project_name"],
                input_dir=meta["input_dir"],
                output_dir=meta["output_dir"],
                workspace=meta["workspace"],
                language=meta.get("language", "vi"),
                model=meta.get("model"),
                agent=agent,
                created_at=meta.get("created_at", ""),
            )
            # Re-register workspace paths so tool ContextVars resolve correctly
            try:
                from tools.workspace import register_thread
                register_thread(
                    thread_id,
                    meta["input_dir"],
                    meta["workspace"],
                )
            except Exception:
                pass

            self._cache[thread_id] = record
            return record
        except Exception:
            log.exception("Failed to recreate agent for thread %s", thread_id)
            return None

    # ── Write ─────────────────────────────────────────────────────────────────

    async def save(self, record: ThreadRecord) -> None:
        """Persist metadata and update local cache."""
        self._cache[record.thread_id] = record

        # Tier 3: always write file (survives restarts without a DB)
        self._write_file(record)

        # Tier 2: write to LangGraph Store when available
        try:
            from infra.persistence import get_store
            store = get_store()
            await store.aput(
                ("threads", record.thread_id),
                "metadata",
                record.to_store_dict(),
            )
        except Exception:
            log.debug("Store write failed for thread %s — file fallback active", record.thread_id)

    async def delete(self, thread_id: str) -> None:
        """Remove thread from all tiers."""
        self._cache.pop(thread_id, None)

        # Remove file
        try:
            p = self._meta_path(thread_id)
            if p.exists():
                p.unlink()
        except Exception:
            pass

        # Remove from Store
        try:
            from infra.persistence import get_store
            await get_store().adelete(("threads", thread_id), "metadata")
        except Exception:
            pass

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get(self, thread_id: str) -> Optional[ThreadRecord]:
        """Return ThreadRecord, restoring from Store/file on cache miss."""
        if thread_id in self._cache:
            return self._cache[thread_id]
        return await self._restore(thread_id)

    def count(self) -> int:
        return len(self._cache)

    def has(self, thread_id: str) -> bool:
        return thread_id in self._cache

    # ── Restore ───────────────────────────────────────────────────────────────

    async def _restore(self, thread_id: str) -> Optional[ThreadRecord]:
        """Try tier-2 (Store) then tier-3 (file) to rebuild a missing thread."""

        # Tier 2: LangGraph Store
        try:
            from infra.persistence import get_store
            item = await get_store().aget(("threads", thread_id), "metadata")
            if item is not None:
                log.info("Restored thread %s from LangGraph Store", thread_id)
                return await self._build_record(thread_id, item.value)
        except Exception:
            log.debug("Store lookup failed for thread %s", thread_id, exc_info=True)

        # Tier 3: file fallback
        meta = self._read_file(thread_id)
        if meta is not None:
            log.info("Restored thread %s from file fallback (_thread.json)", thread_id)
            return await self._build_record(thread_id, meta)

        log.warning("Thread %s not found in cache, Store, or file fallback", thread_id)
        return None

    # ── Startup warm-up ───────────────────────────────────────────────────────

    async def warm_cache_from_disk(self) -> int:
        """Scan workspace dir for _thread.json files and pre-load into cache.

        Call once at server startup so the first request to any thread doesn't
        pay a cold restore penalty.  Returns the number of threads loaded.
        """
        if not self._workspace_base.exists():
            return 0

        loaded = 0
        for meta_path in sorted(self._workspace_base.glob("*/_thread.json")):
            thread_id = meta_path.parent.name
            if thread_id in self._cache:
                continue
            meta = self._read_file(thread_id)
            if meta is None:
                continue
            record = await self._build_record(thread_id, meta)
            if record:
                loaded += 1

        if loaded:
            log.info("warm_cache_from_disk: pre-loaded %d thread(s)", loaded)
        return loaded
