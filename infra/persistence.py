"""Postgres-backed persistence for LangGraph: checkpointer + store.

Two-tier memory:
  • AsyncPostgresSaver — short-term per-thread state (graph checkpoints).
  • AsyncPostgresStore — long-term cross-thread KV (user prefs, project facts).

Both share a single AsyncConnectionPool so we don't open two pools to the
same database.

Lifecycle:
  • Call `init_persistence()` once at process startup (FastAPI lifespan or
    CLI entrypoint). It creates the pool, runs idempotent setup() on the
    checkpointer and store, and warms a connection.
  • Use `get_checkpointer()` / `get_store()` from anywhere afterwards.
  • Call `close_persistence()` on shutdown to drain the pool.

Environment:
  DATABASE_URL   postgresql://user:pass@host:5432/dbname  (required for prod)

Falls back to MemorySaver + InMemoryStore when DATABASE_URL is unset
(useful for unit tests and local CLI runs without docker).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

log = logging.getLogger(__name__)

# ── Module-level singletons (initialized by init_persistence) ────────────────
# Pool is typed Any so this module imports without psycopg installed.
_pool: Optional[Any] = None
_checkpointer: Optional[BaseCheckpointSaver] = None
_store: Optional[BaseStore] = None
_using_memory_fallback: bool = False


# ── Public API ───────────────────────────────────────────────────────────────

async def init_persistence(database_url: str | None = None) -> None:
    """Initialize Postgres pool, checkpointer, and store.

    Idempotent: safe to call multiple times. Subsequent calls are no-ops.

    Args:
        database_url: Postgres URL. Defaults to DATABASE_URL env var.
                      If neither is set, falls back to in-memory backends.
    """
    global _pool, _checkpointer, _store, _using_memory_fallback

    if _checkpointer is not None and _store is not None:
        return  # already initialized

    url = database_url or os.environ.get("DATABASE_URL")

    if not url:
        log.warning(
            "DATABASE_URL not set — falling back to MemorySaver + InMemoryStore. "
            "DO NOT use this in production."
        )
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.store.memory import InMemoryStore

        _checkpointer = MemorySaver()
        _store = InMemoryStore()
        _using_memory_fallback = True
        return

    # ── Production path: Postgres (lazy imports — psycopg only required here) ──
    try:
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from langgraph.store.postgres.aio import AsyncPostgresStore
    except ImportError as e:
        raise RuntimeError(
            "DATABASE_URL is set but Postgres deps are missing. Install with: "
            "pip install langgraph-checkpoint-postgres langgraph-store-postgres "
            "'psycopg[binary,pool]'"
        ) from e

    pool_size = int(os.environ.get("DB_POOL_SIZE", "20"))
    min_size  = int(os.environ.get("DB_POOL_MIN", "2"))

    _pool = AsyncConnectionPool(
        conninfo=url,
        max_size=pool_size,
        min_size=min_size,
        kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
        open=False,
    )
    await _pool.open(wait=True, timeout=30.0)

    _checkpointer = AsyncPostgresSaver(_pool)
    await _checkpointer.setup()  # creates checkpoint tables (idempotent)

    _store = AsyncPostgresStore(_pool)
    await _store.setup()  # creates store tables (idempotent)

    _using_memory_fallback = False
    log.info(
        "Persistence ready: AsyncPostgresSaver + AsyncPostgresStore (pool size=%d)",
        pool_size,
    )


async def close_persistence() -> None:
    """Drain the connection pool. Call from FastAPI lifespan shutdown."""
    global _pool, _checkpointer, _store

    if _pool is not None:
        await _pool.close()
        _pool = None
    _checkpointer = None
    _store = None


def get_checkpointer() -> BaseCheckpointSaver:
    """Return the initialized checkpointer.

    If called before `init_persistence()` (e.g. from a sync CLI entrypoint
    with no DATABASE_URL), silently falls back to MemorySaver.
    """
    global _checkpointer, _store, _using_memory_fallback
    if _checkpointer is None:
        _lazy_init_memory()
    return _checkpointer  # type: ignore[return-value]


def get_store() -> BaseStore:
    """Return the initialized store.

    If called before `init_persistence()` (e.g. from a sync CLI entrypoint
    with no DATABASE_URL), silently falls back to InMemoryStore.
    """
    global _checkpointer, _store, _using_memory_fallback
    if _store is None:
        _lazy_init_memory()
    return _store  # type: ignore[return-value]


def _lazy_init_memory() -> None:
    """Initialize in-memory fallback synchronously.

    Called when get_checkpointer() / get_store() are used before
    init_persistence() — typical in CLI runs without a database.
    In production (FastAPI), init_persistence() should always be awaited
    at startup so this path is never taken.
    """
    global _checkpointer, _store, _using_memory_fallback
    if _checkpointer is not None and _store is not None:
        return
    log.warning(
        "Persistence not initialized — falling back to MemorySaver + InMemoryStore. "
        "Call `await init_persistence()` at startup for production use."
    )
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.store.memory import InMemoryStore

    if _checkpointer is None:
        _checkpointer = MemorySaver()
    if _store is None:
        _store = InMemoryStore()
    _using_memory_fallback = True


def is_memory_fallback() -> bool:
    """True if running with MemorySaver/InMemoryStore (i.e. DATABASE_URL unset)."""
    return _using_memory_fallback


# ── Namespace conventions (READ THIS BEFORE CALLING store.put) ───────────────
#
# Use namespace tuples ≤ 4 elements. Leftmost element scopes tenancy.
#
#   ("users",    user_id, "preferences")
#       → durable user prefs (language, timezone, default OUTPUT_DIR, model)
#
#   ("users",    user_id, "projects", project_id)
#       → per-user-per-project facts (decisions, glossary additions, scope notes)
#
#   ("projects", project_id, "glossary")
#       → project-wide terminology shared across users
#
#   ("projects", project_id, "decisions")
#       → architectural decisions logged during solution_finder iterations
#
#   ("global",   "domain_rules")
#       → org-wide reference data (read-mostly; usually loaded from YAML)
#
# Anti-patterns:
#   ✗ Storing BRD/WBS document state in the Store — those are workspace files.
#   ✗ Storing chat history in the Store — that is the checkpointer's job.
#   ✗ Namespace tuples > 4 elements — slow Postgres index lookups.
#   ✗ Putting unbounded user-content blobs (>10KB) in a single value.
