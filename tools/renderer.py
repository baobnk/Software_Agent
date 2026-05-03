"""Rendering tools — convert Pydantic AST → .docx / .xlsx.

BRD: uses the v2 template + per-section operations (`packages/brd/`).
WBS: still delegates to wbs_agent_kit renderer (legacy single source of truth).

The exporter agent calls these tools with the target output path.
"""
from __future__ import annotations

import sys
from pathlib import Path

from langchain_core.tools import tool

# BRD v2 — section-sharded store
from packages.brd import BRDStore, render_brd_to_docx, available_languages
# WBS v2 — section-sharded store (renderer kept in wbs_agent_kit)
from packages.wbs import WBSStore

try:
    from wbs_agent_kit.src.render_wbs import render_wbs as _render_wbs
except ImportError:
    sys.path.insert(0, str(Path(__file__).parents[2] / "bnk-agent" / "packages"))
    from wbs_agent_kit.src.render_wbs import render_wbs as _render_wbs  # type: ignore

from .workspace import get_workspace, get_output_dir


def _output_root(root: Path, safe_name: str) -> Path:
    """Return the project-level output folder, never double-nesting the name.

    If `root` already ends with `safe_name` (because the caller set OUTPUT_DIR
    to a project-specific path), return it as-is.  Otherwise append `safe_name`.
    """
    if root.name == safe_name:
        return root
    return root / safe_name


@tool
def render_brd(output_path: str = "") -> str:
    """Render BRD state to a Word (.docx) file.

    If output_path is given, saves there (agent-controlled destination).
    Otherwise auto-derives the path from OUTPUT_DIR + project metadata:
      {OUTPUT_DIR}/{project_name}/BRD/{project_name}_BRD_v{version}.docx

    The file is ALWAYS also copied to workspace/BRD.docx for easy access.

    Args:
        output_path: Absolute path for the output file. Leave empty to auto-derive.
    Returns:
        Saved file path and size, or an error message.
    """
    import os
    import shutil

    store = BRDStore(get_workspace() / "brd")
    if not store.is_initialized():
        return "ERROR: BRD not initialized. Has brd_drafter run yet?"

    try:
        doc = store.assemble()
    except Exception as e:
        return f"ERROR assembling BRD: {e}"

    ws = get_workspace()
    workspace_copy = ws / "BRD.docx"

    # ── Resolve output path ───────────────────────────────────────────────────
    if output_path:
        final_out = output_path
    else:
        root = get_output_dir()  # per-thread ContextVar, falls back to OUTPUT_DIR env var
        safe_name = (doc.project_name or "project").replace(" ", "_")
        version = (doc.version or "0.1.0").replace(".", "_")
        final_out = str(_output_root(root, safe_name) / "BRD" / f"{safe_name}_BRD_v{version}.docx")

    try:
        out = render_brd_to_docx(doc, final_out)
        size_kb = out.stat().st_size // 1024
        # Workspace copy is a convenience shortcut — skip silently if it fails
        # (e.g., read-only workspace mount in Docker).
        try:
            if str(out) != str(workspace_copy):
                shutil.copy2(str(out), str(workspace_copy))
        except Exception:
            pass
        return f"BRD rendered → {out}  ({size_kb} KB, language={doc.language})"
    except FileNotFoundError as e:
        return (
            f"ERROR: {e}. Available languages: {available_languages()}. "
            f"Run: python scripts/build_brd_template.py"
        )
    except Exception as e:
        return f"ERROR rendering BRD: {e}"


@tool
def render_wbs(output_path: str = "", team_size: int = 3) -> str:
    """Render WBS state to a .xlsx file.

    If output_path is given, saves there (agent-controlled destination).
    Otherwise auto-derives the path from OUTPUT_DIR + project metadata:
      {OUTPUT_DIR}/{project_name}/WBS/{project_name}_WBS_v{version}.xlsx

    The file is ALWAYS also copied to workspace/WBS.xlsx for easy access.

    Args:
        output_path: Absolute path for the output file. Leave empty to auto-derive.
        team_size:   Number of developers (used for Delivery Plan duration calc).
    Returns:
        Saved file path and size, or an error message.
    """
    import os
    import shutil
    from loguru import logger as _log
    _r_log = _log.bind(ctx="renderer")

    store = WBSStore(get_workspace() / "wbs")
    if not store.is_initialized():
        _r_log.error("render_wbs — WBS not initialized")
        return "ERROR: WBS state not found. Has wbs_estimator run yet?"
    doc = store.assemble()
    meta = store.read_metadata()

    ws = get_workspace()
    workspace_copy = ws / "WBS.xlsx"

    # ── Resolve output path ───────────────────────────────────────────────────
    if output_path:
        final_out = Path(output_path)
    else:
        root = get_output_dir()  # per-thread ContextVar, falls back to OUTPUT_DIR env var
        safe_name = doc.project_name.replace(" ", "_") if doc.project_name else "project"
        version = (meta.version or "0.1.0").replace(".", "_")
        final_out = _output_root(root, safe_name) / "WBS" / f"{safe_name}_WBS_v{version}.xlsx"

    final_out.parent.mkdir(parents=True, exist_ok=True)

    _r_log.info(f"render_wbs | {doc.project_code}  team={team_size}  out={final_out}")
    try:
        _render_wbs(doc, str(final_out), team_size=team_size)
        size_kb = final_out.stat().st_size // 1024
        _r_log.success(f"  WBS.xlsx saved → {final_out}  ({size_kb} KB)")
        # Workspace copy is a convenience shortcut — skip silently if it fails
        # (e.g., read-only workspace mount in Docker).
        try:
            if str(final_out) != str(workspace_copy):
                shutil.copy2(str(final_out), str(workspace_copy))
        except Exception:
            pass
        return f"WBS.xlsx saved → {final_out}  ({size_kb} KB)"
    except Exception as e:
        _r_log.error(f"  render_wbs error: {e}")
        return f"ERROR rendering WBS: {e}"
