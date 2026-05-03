"""orchestrator.py — Main BnK DeepAgent orchestrator.

Architecture: a SINGLE DeepAgent handles intake + solution-finder + planning
+ user chat. WBS and BRD are encapsulated as **two `create_react_agent`
workflows wrapped as tools** — the main agent calls `run_wbs_workflow` then
`run_brd_workflow`. Critic + render live inside those workflows.

Key design decisions:
  • DeepAgent = supervisor with planning + todolist + memory.
  • Workflow tools = inner `create_react_agent` graphs (NOT DeepAgents).
  • CompositeBackend — virtual /input/, /output/, /workspace mapping.
  • interrupt_on — HITL gate before workflow tool calls.
  • memory=["/AGENTS.md"] — session context survives compaction.
  • System prompt lives in `prompts/orchestrator.py` (deer-flow style).
"""
from __future__ import annotations

import os
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend, CompositeBackend

# Absolute path to skills/ — resolved once at import time so it works
# regardless of the process working directory.
SKILLS_DIR = Path(__file__).parent / "skills"

# ── Intake tools (read input files) ──────────────────────────────────────────
from tools.file_reader import (
    list_input_files,
    read_pdf_smart, read_docx, read_txt, read_pptx, read_xlsx,
    describe_image, write_raw_features,
)

# ── Solution-finder tools (9-step technical design + diagrams) ───────────────
from tools.solution_ops import (
    get_raw_features, patch_solution_section, get_solution_draft,
    apply_user_input, save_technical_design_md, confirm_diagram_generation,
    get_technical_design,
)
from tools.drawio_diagram_gen import generate_technical_design_diagram, export_diagram_png

# ── Workflow tools (2 — wrap create_react_agent graphs) ──────────────────────
from agents.wbs_workflow import run_wbs_workflow
from agents.brd_workflow import run_brd_workflow

# ── Wave 2: WBS post-render fixup + delivery planning (4 tools) ──────────────
# These run AT THE OUTER AGENT LEVEL (not inside wbs_workflow) because
# `confirm_delivery_milestones` calls langgraph.types.interrupt() which
# requires the checkpointer that only the outer DeepAgent has.
from tools.excel_audit import audit_workbook
from tools.excel_patch import patch_workbook
from tools.delivery_ops import compute_delivery_plan, confirm_delivery_milestones, finalize_delivery_plan

# ── Folder management + memory ───────────────────────────────────────────────
from packages.config import get_agent_model, get_llm, apply_onprem_config

# Apply on-prem endpoint settings once at import time (no-op when disabled)
apply_onprem_config()
from tools.folder_manager import (
    get_output_paths, list_project_outputs, set_output_dir,
)
from tools.memory import (
    save_user_preference, recall_user_preferences,
    save_project_decision, recall_project_decisions,
)

# ── Prompts (deer-flow style — all prompts live in the prompts/ package) ─────
from prompts import apply_orchestrator_prompt


# ── Factory ──────────────────────────────────────────────────────────────────

def create_orchestrator(
    input_dir: str | None = None,
    output_dir: str | None = None,
    workspace_dir: str | None = None,
    model: str | None = None,
    checkpointer=None,
    store=None,
    enable_hitl: bool | None = None,
) -> object:
    """Build and return the compiled main DeepAgent.

    Args:
        input_dir:    Directory containing user requirement files.
        output_dir:   Root directory for generated artefacts.
        workspace_dir: Session scratch space for state.
        model:        LLM string e.g. "anthropic:claude-sonnet-4-6".
        checkpointer: LangGraph checkpointer (Tier 1 short-term memory).
        store:        LangGraph BaseStore (Tier 3 long-term memory).
        enable_hitl:  Whether to pause before workflow tool calls.

    Returns:
        Compiled DeepAgent graph (call .invoke() / .stream() / .astream()).
    """
    # ── Resolve config ────────────────────────────────────────────────────────
    _input_dir   = str(Path(input_dir   or os.environ.get("ATTACHMENTS_DIR",   "/tmp/bnk-input")).resolve())
    _output_dir  = str(Path(output_dir  or os.environ.get("OUTPUT_DIR",        "/tmp/bnk-outputs")).resolve())
    _ws_base     = str(Path(workspace_dir or os.environ.get("WORKSPACE_BASE_DIR", "/tmp/bnk-workspace")).resolve())
    _model       = model or get_llm("orchestrator")
    _hitl        = enable_hitl if enable_hitl is not None else (
        os.environ.get("ENABLE_HITL", "true").lower() == "true"
    )

    Path(_input_dir).mkdir(parents=True, exist_ok=True)
    Path(_output_dir).mkdir(parents=True, exist_ok=True)
    Path(_ws_base).mkdir(parents=True, exist_ok=True)

    # ── Backend: composite filesystem ────────────────────────────────────────
    backend = CompositeBackend(
        default=FilesystemBackend(root_dir=_ws_base),
        routes={
            "/input/":  FilesystemBackend(root_dir=_input_dir),
            "/output/": FilesystemBackend(root_dir=_output_dir),
            "/skills/": FilesystemBackend(root_dir=str(SKILLS_DIR)),
        },
    )

    # ── HITL: pause before workflow tool calls ───────────────────────────────
    interrupt_config: dict = {}
    if _hitl:
        interrupt_config = {
            # NOTE: confirm_diagram_generation uses interrupt() internally — NOT listed
            # here because generate_technical_design_diagram is called 3× per turn,
            # which would cause "N decisions != N hanging tool calls" errors.
            # confirm_diagram_generation is called once and handles its own interrupt.
            "run_wbs_workflow": True,
            "run_brd_workflow": True,
            # Pause before milestone confirm — frontend renders proposed dates.
            "confirm_delivery_milestones": True,
        }

    # ── Persistence (checkpointer + store) ───────────────────────────────────
    if checkpointer is None or store is None:
        try:
            from infra.persistence import get_checkpointer, get_store
            checkpointer = checkpointer or get_checkpointer()
            store = store or get_store()
        except RuntimeError:
            from langgraph.checkpoint.memory import MemorySaver
            from langgraph.store.memory import InMemoryStore
            checkpointer = checkpointer or MemorySaver()
            store = store or InMemoryStore()

    # ── Assemble agent ───────────────────────────────────────────────────────
    agent = create_deep_agent(
        model=_model,
        skills=["/skills/"],
        tools=[
            # Intake (read input files)
            list_input_files,
            read_pdf_smart, read_docx, read_txt, read_pptx, read_xlsx,
            describe_image, write_raw_features,
            # Solution finder
            get_raw_features, patch_solution_section, get_solution_draft,
            apply_user_input, save_technical_design_md,
            get_technical_design,
            # Diagram generation gate (single HITL call) + 3× generator + PNG export
            confirm_diagram_generation,
            generate_technical_design_diagram,
            export_diagram_png,
            # Workflow runners (2 — wrap create_react_agent graphs)
            run_wbs_workflow,
            run_brd_workflow,
            # WBS Wave 2: post-render fixup + delivery planning (5 tools)
            # — see skills/excel_workbook + skills/delivery_planning
            audit_workbook,
            patch_workbook,
            compute_delivery_plan,
            confirm_delivery_milestones,
            finalize_delivery_plan,
            # Folder management
            set_output_dir, get_output_paths, list_project_outputs,
            # Long-term memory
            save_user_preference, recall_user_preferences,
            save_project_decision, recall_project_decisions,
        ],
        system_prompt=apply_orchestrator_prompt(),
        backend=backend,
        memory=["/AGENTS.md"],
        interrupt_on=interrupt_config,
        checkpointer=checkpointer,
        store=store,
        name="bnk_main_agent",
        debug=os.environ.get("DEBUG", "false").lower() == "true",
    )

    return agent
