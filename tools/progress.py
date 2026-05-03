"""Thread-safe progress emitter for sync sub-workflow tools.

Sub-workflow tools (run_wbs_workflow, run_brd_workflow) call graph.invoke()
which blocks the thread. This module provides a threading.Queue channel so
their internal tool calls can push progress to the parent SSE stream.

Usage (caller side — api/main.py):
    import queue as tq
    sub_q: tq.Queue = tq.Queue()
    token = set_sub_progress_queue(sub_q)
    ... run agent ...
    # After each astream chunk, drain sub_q:
    while not sub_q.empty():
        item = sub_q.get_nowait()  # {"tool": str, "done": bool, "output": str}
        ...

Usage (tool side — automatically via SubWorkflowProgressCallback):
    graph.invoke(..., config={"callbacks": [SubWorkflowProgressCallback()]})
"""
from __future__ import annotations

import queue as _tq
from contextvars import ContextVar
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

_sub_progress_q: ContextVar[_tq.Queue | None] = ContextVar(
    "sub_progress_q", default=None
)


def set_sub_progress_queue(q: "_tq.Queue") -> Any:
    """Store queue in contextvar; returns token for reset."""
    return _sub_progress_q.set(q)


def clear_sub_progress_queue(token: Any) -> None:
    _sub_progress_q.reset(token)


def _push(tool_name: str, completed: bool, output: str = "") -> None:
    q = _sub_progress_q.get()
    if q is not None:
        try:
            q.put_nowait({"tool": tool_name, "done": completed, "output": output})
        except Exception:
            pass


class SubWorkflowProgressCallback(BaseCallbackHandler):
    """LangChain callback that reports tool start/end via threading.Queue.

    Each queue item: {"tool": str, "done": bool, "output": str}
    output is the tool's return value (capped at 1000 chars) when done=True.
    """

    def __init__(self) -> None:
        super().__init__()
        self._stack: list[str] = []

    def on_tool_start(self, serialized: dict, input_str: str, **kwargs: Any) -> None:
        name = serialized.get("name", "") or kwargs.get("name", "")
        self._stack.append(name)
        _push(name, completed=False)

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        if self._stack:
            name = self._stack.pop()
            output_str = str(output) if output is not None else ""
            _push(name, completed=True, output=output_str[:1000])

    def on_tool_error(self, error: Any, **kwargs: Any) -> None:
        if self._stack:
            _push(self._stack.pop(), completed=True)
