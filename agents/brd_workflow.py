"""BRD workflow — a small `create_agent` graph wrapped as a single tool.

The main DeepAgent calls `run_brd_workflow(brief)` after the WBS workflow
has produced `workspace/project.json`. This black-box graph then runs
`init_brd (inherit metadata) → fill all sections → validate → render`
end-to-end and returns a one-line summary.

System prompt lives in [`prompts/brd_workflow.py`](../prompts/brd_workflow.py).

WBS-first pipeline contract:
- Runs AFTER `run_wbs_workflow`.
- `init_brd()` is called with NO ARGS → inherits project_code,
  project_name, language, version from `workspace/project.json`.
- FR ids in §5.2 must match the `source_feature_id` values that WBS
  tasks reference.
"""
from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.tools import tool

from packages.config import get_llm
from prompts import apply_brd_workflow_prompt
from tools.progress import SubWorkflowProgressCallback
from tools.brd_ops import (
    init_brd, set_brd_text, add_brd_list_item,
    upsert_brd_row, upsert_fr, get_brd_summary,
)
from tools.validators import validate_brd, validate_traceability
from tools.renderer import render_brd


def _build_brd_graph():
    """Compile the inner BRD create_agent graph (lazily)."""
    return create_agent(
        model=get_llm("brd_drafter_agent"),
        tools=[
            init_brd,
            set_brd_text,
            add_brd_list_item,
            upsert_brd_row,
            upsert_fr,
            get_brd_summary,
            validate_brd,
            validate_traceability,
            render_brd,
        ],
        system_prompt=apply_brd_workflow_prompt(),
        name="brd_workflow",
    )


_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = _build_brd_graph()
    return _graph


@tool
def run_brd_workflow(brief: str) -> str:
    """Execute the full BRD workflow: init → fill sections → validate → render .docx.

    Pass a one-paragraph brief covering: solution context, the FR ids
    that WBS used (must match), language, and any specific BRD content
    requirements.

    This tool BLOCKS for the entire BRD construction (typically 60–120s).
    Use AFTER `run_wbs_workflow` has succeeded — BRD inherits project
    metadata from workspace/project.json which WBS wrote.

    Returns a one-line status with output file path.
    """
    graph = _get_graph()
    result = graph.invoke(
        {"messages": [{"role": "user", "content": brief}]},
        config={"callbacks": [SubWorkflowProgressCallback()]},
    )
    last = result["messages"][-1]
    return getattr(last, "content", str(last))
