"""Agent factories.

After the architecture refactor (1 main DeepAgent + 2 workflow tools),
this package exports only the two workflow-tool wrappers. Both wrap an
inner `create_react_agent` graph; the system prompts they use live in
the top-level `prompts/` package.

  run_wbs_workflow → wraps WBS construction graph
  run_brd_workflow → wraps BRD construction graph
"""
from .wbs_workflow import run_wbs_workflow
from .brd_workflow import run_brd_workflow

__all__ = [
    "run_wbs_workflow",
    "run_brd_workflow",
]
