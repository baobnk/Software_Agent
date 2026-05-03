"""Centralized prompt templates for BnK DeepAgent.

Each module exports:
  • A `<NAME>_PROMPT_TEMPLATE` constant — the raw template string.
  • An `apply_<name>_prompt(...)` function — composes the final string,
    substituting any dynamic sections (skills, memory, etc.).

Why a dedicated package (deer-flow style) instead of inline strings:
  • Prompts are large (hundreds of lines) and dominate the file when inlined.
  • Production teams need to A/B test, version, and iterate on prompts
    independently of the orchestration code.
  • Multiple agents may share prompt fragments (sections, hard-rule blocks).
  • Easier to lint, search, and diff prompt-only changes.

Layout:
  orchestrator.py     Main DeepAgent prompt (intake + solution + delegation)
  wbs_workflow.py     WBS workflow prompt (decompose → estimate → render)
  brd_workflow.py     BRD workflow prompt (fill sections → validate → render)
  diagram_gen.py      mxGraph XML diagram prompt (solution_finder → drawio tool)
"""
from .orchestrator import (
    ORCHESTRATOR_PROMPT_TEMPLATE,
    apply_orchestrator_prompt,
)
from .wbs_workflow import (
    WBS_WORKFLOW_PROMPT_TEMPLATE,
    apply_wbs_workflow_prompt,
)
from .brd_workflow import (
    BRD_WORKFLOW_PROMPT_TEMPLATE,
    apply_brd_workflow_prompt,
)
from .diagram_gen import (
    DIAGRAM_XML_SYSTEM_PROMPT,
    DIAGRAM_LAYOUT_INSTRUCTIONS,
    apply_diagram_xml_prompt,
)

__all__ = [
    "ORCHESTRATOR_PROMPT_TEMPLATE",
    "WBS_WORKFLOW_PROMPT_TEMPLATE",
    "BRD_WORKFLOW_PROMPT_TEMPLATE",
    "apply_orchestrator_prompt",
    "apply_wbs_workflow_prompt",
    "apply_brd_workflow_prompt",
    "DIAGRAM_XML_SYSTEM_PROMPT",
    "DIAGRAM_LAYOUT_INSTRUCTIONS",
    "apply_diagram_xml_prompt",
]
