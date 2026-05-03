"""WBS workflow — a small `create_agent` graph wrapped as a single tool.

The main DeepAgent (orchestrator) calls `run_wbs_workflow(brief)`; this
black-box graph runs `init_wbs → decompose → estimate → validate → render`
end-to-end and returns a one-line summary including the output .xlsx path.

After this returns, the outer DeepAgent calls Wave-2 tools (audit_workbook,
patch_workbook, compute_delivery_plan, confirm_delivery_milestones) — those
need outer-agent-level interrupt support which inner `create_agent` graphs
without a checkpointer cannot provide. See orchestrator.py for Wave 2 wiring.

System prompt lives in [`prompts/wbs_workflow.py`](../prompts/wbs_workflow.py).

Tool budget inside the workflow (Rule §2 ≤ 8):
  init_wbs, set_master_data, upsert_task, get_wbs_summary,
  validate_wbs, render_wbs   (6 tools — all WBS-scoped)
"""
from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.tools import tool

from packages.config import get_llm
from prompts import apply_wbs_workflow_prompt
from tools.progress import SubWorkflowProgressCallback
from tools.renderer import render_wbs
from tools.validators import validate_wbs
from tools.wbs_ops import get_wbs_summary, init_wbs, set_master_data, upsert_task


def _build_wbs_graph():
    """Compile the inner WBS create_agent graph (lazily)."""
    return create_agent(
        model=get_llm("wbs_estimator_agent"),
        tools=[
            init_wbs,
            set_master_data,
            upsert_task,
            get_wbs_summary,
            validate_wbs,
            render_wbs,
        ],
        system_prompt=apply_wbs_workflow_prompt(),
        name="wbs_workflow",
    )


# Cache the compiled graph at module level (built lazily on first call).
_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = _build_wbs_graph()
    return _graph


@tool
def run_wbs_workflow(brief: str) -> str:
    """Execute the full WBS workflow: init → decompose → estimate → validate → render .xlsx.

    Pass a one-paragraph brief covering: project_code, project_name, target
    language, summary of features, any non-standard rates, and the FR ids
    to link tasks to. The workflow runs to completion (or critic fail) and
    returns a one-line status. State is persisted in `<workspace>/wbs/` and
    `<workspace>/project.json`.

    This tool BLOCKS for the entire WBS construction (typically 30–90s).
    Use AFTER the user has confirmed the solution design.
    """
    graph = _get_graph()
    result = graph.invoke(
        {"messages": [{"role": "user", "content": brief}]},
        config={"callbacks": [SubWorkflowProgressCallback()]},
    )
    last = result["messages"][-1]
    return getattr(last, "content", str(last))
