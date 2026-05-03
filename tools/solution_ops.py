"""Solution ops tools — manage the 9-step solution finding workflow.

Files produced per session:
  solution_draft.md        working draft (patched step by step)
  technical_design.md      finalized solution document
  technical_design.drawio  architecture diagram (mxGraphModel XML)
"""
from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool
from loguru import logger as _log

from .workspace import (
    get_workspace, read_json, write_json, read_text, write_text, RAW_FEATURES_FILE,
)

_sol_log = _log.bind(ctx="solution_ops")

# ── Well-known filenames ──────────────────────────────────────────────────────

SOLUTION_DRAFT_FILE     = "solution_draft.json"   # {step: content} dict
TECHNICAL_DESIGN_MD     = "technical_design.md"

_STEP_HEADINGS = {
    1: "## 1. Xác nhận bài toán (Problem Confirmation)",
    2: "## 2. Hướng tiếp cận (Solution Approach)",
    3: "## 3. Kiến trúc hệ thống (System Architecture)",
    4: "## 4. Phân rã module (Module Decomposition)",
    5: "## 5. Tech Stack đề xuất (Technology Selection)",
    6: "## 6. Thiết kế tích hợp (Integration Design)",
    7: "## 7. Phạm vi (Scope Definition)",
    8: "## 8. Giả định ước tính (Estimation Assumptions)",
    9: "## 9. Rủi ro & giải pháp (Risk Assessment)",
}


def _load_draft() -> dict[int, str]:
    raw = read_json(SOLUTION_DRAFT_FILE)
    if not raw:
        return {}
    try:
        return {int(k): v for k, v in raw.items()}
    except (ValueError, AttributeError):
        _sol_log.warning("_load_draft: unexpected structure, resetting draft")
        return {}


def _save_draft(draft: dict[int, str]) -> None:
    write_json(SOLUTION_DRAFT_FILE, {str(k): v for k, v in draft.items()})


def _render_draft(draft: dict[int, str], project_name: str = "") -> str:
    header = f"# Technical Design: {project_name}\n\n" if project_name else "# Technical Design\n\n"
    sections = []
    for step in sorted(_STEP_HEADINGS):
        heading = _STEP_HEADINGS[step]
        content = draft.get(step, "_Chưa có nội dung_")
        sections.append(f"{heading}\n\n{content}")
    return header + "\n\n---\n\n".join(sections)


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def get_raw_features() -> str:
    """Read raw_features.md from workspace — the intake agent's output.

    Call this first to understand the project requirements before starting
    the solution design process.
    """
    content = read_text(RAW_FEATURES_FILE)
    if not content:
        _sol_log.warning("get_raw_features — raw_features.md not found")
        return "[raw_features.md not found — run intake_agent first]"
    _sol_log.info(f"get_raw_features | {len(content):,} chars")
    return content


@tool
def patch_solution_section(step: int, content: str) -> str:
    """Write or overwrite a single step section in the solution draft.

    Args:
        step:    Step number 1-9 (maps to a fixed section heading).
        content: Full markdown content for this section (NO need to repeat heading).
    Returns:
        Confirmation with current section count.
    """
    if step not in range(1, 10):
        return f"[Invalid step {step} — must be 1-9]"
    draft = _load_draft()
    draft[step] = content.strip()
    _save_draft(draft)
    result = f"Step {step} saved ({len(content)} chars). Draft has {len(draft)}/9 sections."
    _sol_log.info(f"patch_solution_section | step={step}  {len(draft)}/9 complete")
    return result


@tool
def get_solution_draft(steps: str = "all") -> str:
    """Read the current solution draft for review.

    Args:
        steps: "all" to get all sections, or comma-separated step numbers
               e.g. "1,2,3" to read specific sections.
    Returns:
        Rendered markdown of the requested sections.
    """
    draft = _load_draft()
    if not draft:
        return "[Solution draft is empty — use patch_solution_section to start]"

    if steps == "all":
        selected = sorted(_STEP_HEADINGS.keys())
    else:
        try:
            selected = [int(s.strip()) for s in steps.split(",")]
        except ValueError:
            return "[Invalid steps format — use 'all' or '1,3,5']"

    parts = []
    for step in selected:
        heading = _STEP_HEADINGS.get(step, f"## Step {step}")
        content = draft.get(step, "_Chưa có nội dung_")
        parts.append(f"{heading}\n\n{content}")
    return "\n\n---\n\n".join(parts)


@tool
def apply_user_input(step: int, user_text: str) -> str:
    """Apply user-provided content to a specific step section.

    Use this when the user provides their own solution text or corrections.
    The user_text replaces the agent-generated content for that step.

    Args:
        step:      Step number 1-9.
        user_text: The user's text to store for this section.
    Returns:
        Confirmation message.
    """
    if step not in range(1, 10):
        return f"[Invalid step {step} — must be 1-9]"
    draft = _load_draft()
    draft[step] = user_text.strip()
    _save_draft(draft)
    return (
        f"User input applied to step {step} ({len(user_text)} chars). "
        "Call get_solution_draft to review."
    )


_STEP_NAMES = {
    1: "Problem Confirmation",
    2: "Solution Approach",
    3: "System Architecture",
    4: "Module Decomposition",
    5: "Tech Stack",
    6: "Integration Design",
    7: "Scope Definition",
    8: "Estimation Assumptions",
    9: "Risk Assessment",
}


@tool
def save_technical_design_md(project_name: str) -> str:
    """Finalize and save technical_design.md from the current solution draft.

    All 9 steps must be drafted with patch_solution_section before calling this.
    If any steps are missing the function returns an error — it will NOT save
    a partial document with placeholder text.

    Args:
        project_name: Project name used as the document header.
    Returns:
        Absolute path of the saved file, or an error listing missing steps.
    """
    draft = _load_draft()
    missing = sorted(s for s in range(1, 10) if s not in draft)
    if missing:
        _sol_log.warning(f"save_technical_design_md — blocked, missing steps {missing}")
        missing_desc = ", ".join(
            f"Step {s} ({_STEP_NAMES[s]})" for s in missing
        )
        return (
            f"[Blocked] {len(missing)} step(s) not yet drafted: {missing_desc}. "
            "Complete each missing step with patch_solution_section(step, content) "
            "then call save_technical_design_md again."
        )

    content = _render_draft(draft, project_name)
    write_text(TECHNICAL_DESIGN_MD, content)
    ws = get_workspace()
    path = str(ws / TECHNICAL_DESIGN_MD)
    _sol_log.success(f"technical_design.md saved → {path}  ({len(content):,} chars)")
    return f"technical_design.md saved → {path} ({len(content):,} chars). All 9 sections present."


_DIAGRAM_TYPES_ALL = ["system_architecture", "component", "deployment"]

_DIAGRAM_ALIASES: dict[str, str] = {
    "1": "system_architecture", "arch": "system_architecture",
    "architecture": "system_architecture", "system": "system_architecture",
    "2": "component", "comp": "component", "components": "component",
    "3": "deployment", "deploy": "deployment", "infra": "deployment",
}


def _parse_diagram_selection(feedback: str) -> list[str]:
    """Parse user feedback into a list of diagram_type strings.

    Accepts: "1,3", "system_architecture, deployment", "all", "1 và 3", etc.
    Returns a non-empty list (defaults to all 3 if unrecognised).
    """
    if not feedback:
        return _DIAGRAM_TYPES_ALL[:]
    text = feedback.lower().replace("và", ",").replace("and", ",").replace(";", ",")
    if any(w in text for w in ("all", "tất cả", "cả 3", "3 cái", "hết")):
        return _DIAGRAM_TYPES_ALL[:]
    selected: list[str] = []
    for token in text.replace(",", " ").split():
        token = token.strip(".")
        resolved = _DIAGRAM_ALIASES.get(token) or (token if token in _DIAGRAM_TYPES_ALL else None)
        if resolved and resolved not in selected:
            selected.append(resolved)
    return selected if selected else _DIAGRAM_TYPES_ALL[:]


@tool
def confirm_diagram_generation() -> str:
    """HITL gate — pause before architecture diagram generation.

    Call this ONCE after save_technical_design_md succeeds, BEFORE calling
    generate_technical_design_diagram. Asks the user which diagrams to generate.

    The return value lists the diagram types the user selected — call
    generate_technical_design_diagram only for those types (in order).

    Resumes when the user approves via the /approve endpoint.
    If the user rejects, the tool returns a cancellation message.
    """
    from langgraph.types import interrupt as _interrupt

    ws = get_workspace()
    md_path = ws / TECHNICAL_DESIGN_MD
    content_size = md_path.stat().st_size if md_path.exists() else 0

    decision = _interrupt({
        "tool": "confirm_diagram_generation",
        "message": (
            "Solution design saved. Chọn diagram cần vẽ (mặc định: cả 3):\n"
            "  1. system_architecture — C4 L1 context diagram\n"
            "  2. component           — C4 L2 module diagram\n"
            "  3. deployment          — infrastructure tiers diagram\n"
            f"Source: technical_design.md ({content_size:,} bytes)\n"
            "Nhập số/tên diagram muốn vẽ (vd: '1,3' hoặc 'all') rồi Approve."
        ),
    })

    # Check reject
    decisions = decision.get("decisions", []) if isinstance(decision, dict) else []
    first = decisions[0] if decisions else {}
    if first.get("type", "approve") in ("reject", "rejected"):
        _sol_log.info("confirm_diagram_generation — user rejected")
        return "[Cancelled] Diagram generation cancelled by user."

    # Parse diagram selection from feedback
    feedback: str = first.get("message", "") or ""
    selected = _parse_diagram_selection(feedback)
    _sol_log.info(f"confirm_diagram_generation — approved, types={selected}")

    types_str = ", ".join(f"'{t}'" for t in selected)
    return (
        f"Diagram generation approved. Generate {len(selected)} diagram(s) in order: {types_str}. "
        f"Call generate_technical_design_diagram once for each type listed above — no others."
    )


@tool
def get_technical_design() -> str:
    """Read the finalized technical_design.md from the current workspace session.

    Call this at the start of BRD drafting to get the full solution context:
    problem confirmation, approach, architecture, modules, tech stack,
    integrations, scope, assumptions, and risks.

    Returns the full technical design document, or a guidance message if
    it hasn't been generated yet (e.g. user skipped solution step).
    """
    content = read_text(TECHNICAL_DESIGN_MD)
    if content:
        return content
    draft = _load_draft()
    if draft:
        return _render_draft(draft)
    return (
        "[technical_design.md not found — solution_finder_agent has not run yet. "
        "You can still draft the BRD from raw_features.md alone.]"
    )


