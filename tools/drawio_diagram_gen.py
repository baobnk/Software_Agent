"""Draw.io diagram generation tool — mxGraph XML via LLM + Pillow PNG renderer.

Pipeline:
  1. LLM generates mxGraph XML from technical_design.md sections.
  2. XML is sanitized (strip declaration, fix bare &, close truncated tags).
  3. .drawio saved unconditionally — always readable in draw.io desktop/web.
  4. PNG rendered via Pillow — non-fatal if it fails (bad XML still editable).

Model: configurable via `technical_design_diagram` in config/agent_models.yaml
       (defaults to openai:gpt-5.4-mini)

API endpoints:
  Preview:  GET /api/threads/{id}/workspace/diagrams/{type}.png
  Download: GET /api/threads/{id}/workspace/diagrams/{type}.drawio
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from langchain_core.tools import tool
from loguru import logger as _log
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from packages.config import get_agent_model
from prompts.diagram_gen import DIAGRAM_XML_SYSTEM_PROMPT, apply_diagram_xml_prompt
from .workspace import get_workspace

_diag_log = _log.bind(ctx="drawio_diagram_gen")

_VALID_TYPES     = ("system_architecture", "component", "deployment")
_DESIGN_FILE     = "technical_design.md"
_DIAGRAMS_SUBDIR = "diagrams"


# ── XML sanitizer ─────────────────────────────────────────────────────────────

# Valid XML entity references — do NOT escape these
_VALID_ENTITY_RE = re.compile(
    r'&(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);',
    re.IGNORECASE,
)

def _sanitize_xml(raw: str) -> str:
    """Fix common LLM XML output issues so ElementTree can parse it.

    Handles:
    • Markdown code fences (```xml ... ```)
    • BOM + XML declaration (<?xml ...?>)
    • Content before <mxGraphModel (LLM preamble text)
    • Unescaped bare & in attribute values (most common cause of parse errors)
    • HTML entities (&nbsp; &mdash; etc.) → numeric equivalents
    • Truncated output — closes unclosed </root> and </mxGraphModel>
    """
    s = raw.strip()

    # Strip markdown fences
    if s.startswith("```"):
        s = re.sub(r"^```[^\n]*\n?", "", s)
        s = re.sub(r"\n?```\s*$", "", s.strip())
        s = s.strip()

    # Strip BOM
    s = s.lstrip("﻿")

    # Strip XML declaration
    s = re.sub(r"<\?xml[^?]*\?>\s*", "", s)

    # Skip any preamble before <mxGraphModel
    idx = s.find("<mxGraphModel")
    if idx > 0:
        s = s[idx:]
    elif idx == -1:
        # No mxGraphModel found at all — return as-is, caller handles it
        return s

    # Replace known HTML-only entities with numeric XML equivalents
    _html_entities = {
        "&nbsp;":   "&#160;",
        "&mdash;":  "&#8212;",
        "&ndash;":  "&#8211;",
        "&ldquo;":  "&#8220;",
        "&rdquo;":  "&#8221;",
        "&lsquo;":  "&#8216;",
        "&rsquo;":  "&#8217;",
        "&hellip;": "&#8230;",
        "&rarr;":   "&#8594;",
        "&larr;":   "&#8592;",
        "&bull;":   "&#8226;",
        "&copy;":   "&#169;",
        "&reg;":    "&#174;",
        "&trade;":  "&#8482;",
    }
    for html_ent, xml_ent in _html_entities.items():
        s = s.replace(html_ent, xml_ent)

    # Fix bare & (not already part of a valid XML entity reference)
    # Strategy: split on &, then re-join — only add amp; when not already valid
    parts = s.split("&")
    fixed = [parts[0]]
    for chunk in parts[1:]:
        # Check if this & starts a valid entity reference
        if _VALID_ENTITY_RE.match("&" + chunk[:20]):
            fixed.append("&" + chunk)
        else:
            fixed.append("&amp;" + chunk)
    s = "".join(fixed)

    # Fix bare < inside double-quoted attribute values
    # XML forbids unescaped < inside attribute values; LLMs emit e.g. value="A < B"
    # Strategy: find all ="..." spans, escape < and > within them.
    def _fix_attr_lt(m: re.Match) -> str:
        inner = m.group(1).replace("<", "&lt;").replace(">", "&gt;")
        return f'="{inner}"'
    s = re.sub(r'="([^"]*)"', _fix_attr_lt, s)

    # Close truncated output (LLM hit token limit)
    tail = s.rstrip()
    if not tail.endswith("</mxGraphModel>"):
        if not re.search(r"</root>", tail):
            tail += "\n  </root>"
        tail += "\n</mxGraphModel>"
        s = tail

    return s


def _is_parseable(xml_str: str) -> tuple[bool, str]:
    """Try parsing the XML. Returns (ok, error_message)."""
    try:
        ET.fromstring(xml_str)
        return True, ""
    except ET.ParseError as exc:
        return False, str(exc)


def _validate_diagram_xml(xml_str: str) -> tuple[bool, str]:
    """Validate mxGraph XML structure after sanitization.

    Checks:
      1. Syntactically valid XML
      2. Root tag is mxGraphModel
      3. Contains at least one swimlane container
      4. Contains at least 3 vertex cells (non-swimlane nodes)

    Returns (ok, reason) — reason is '' when ok=True.
    """
    ok, parse_err = _is_parseable(xml_str)
    if not ok:
        return False, f"XML parse error: {parse_err}"

    root = ET.fromstring(xml_str)
    tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    if tag != "mxGraphModel":
        return False, f"Root tag is '{tag}', expected 'mxGraphModel'"

    cells = [e for e in root.iter() if (e.tag.split("}")[-1]) == "mxCell"]
    real_cells = [c for c in cells if c.get("id") not in ("0", "1")]

    swimlanes = [
        c for c in real_cells
        if c.get("vertex") == "1" and "swimlane" in (c.get("style") or "")
    ]
    if not swimlanes:
        return False, "Diagram has no swimlane containers — diagram appears empty or malformed"

    vertices = [
        c for c in real_cells
        if c.get("vertex") == "1" and "swimlane" not in (c.get("style") or "")
    ]
    if len(vertices) < 3:
        return False, f"Only {len(vertices)} node(s) found — diagram too sparse (need ≥ 3)"

    return True, ""


# ── Internal helpers ──────────────────────────────────────────────────────────

def _load_technical_design() -> str:
    ws = get_workspace()
    path = ws / _DESIGN_FILE
    if not path.exists():
        raise FileNotFoundError(f"technical_design.md not found at {path}")
    return path.read_text(encoding="utf-8")


def _extract_sections(md_text: str, section_numbers: list[int]) -> str:
    parts: list[str] = []
    for n in section_numbers:
        m = re.search(rf"(##\s*{n}\..*?)(?=\n##\s*\d+\.|\Z)", md_text, re.DOTALL)
        if m:
            parts.append(m.group(1).strip())
    return "\n\n".join(parts) or md_text[:4000]


def _section_numbers_for_type(diagram_type: str) -> list[int]:
    return {
        "system_architecture": [3, 4, 6],
        "component":           [4, 3],
        "deployment":          [5, 6, 3],
    }.get(diagram_type, [3, 4])


def _diagrams_dir() -> Path:
    d = get_workspace() / _DIAGRAMS_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _output_paths(diagram_type: str) -> tuple[Path, Path]:
    d = _diagrams_dir()
    return d / f"{diagram_type}.drawio", d / f"{diagram_type}.png"


def _generate_xml_via_llm(diagram_type: str, content: str, project_name: str) -> str:
    model_str = get_agent_model("technical_design_diagram")
    _, _, model_name = model_str.partition(":")
    if not model_name:
        model_name = model_str

    llm = ChatOpenAI(model=model_name, temperature=0.1)
    user_msg = apply_diagram_xml_prompt(diagram_type, content, project_name)

    _diag_log.info(
        f"[XML-GEN] type={diagram_type} model={model_name} "
        f"content={len(content)}chars prompt={len(user_msg)}chars"
    )
    response = llm.invoke([
        SystemMessage(content=DIAGRAM_XML_SYSTEM_PROMPT),
        HumanMessage(content=user_msg),
    ])
    raw = response.content
    _diag_log.debug(
        f"[XML-GEN] raw={len(raw)}chars "
        f"has_mxGraphModel={('<mxGraphModel' in raw)} "
        f"cell_count={raw.count('<mxCell')}"
    )
    sanitized = _sanitize_xml(raw)
    _diag_log.debug(
        f"[XML-GEN] after sanitize={len(sanitized)}chars "
        f"cell_count={sanitized.count('<mxCell')}"
    )
    return sanitized


def _render_png(xml: str, png_path: Path) -> str | None:
    """Render mxGraph XML to PNG via MCP drawio (native quality) or Pillow (fallback).

    MCP opens a browser tab for draw.io rendering — produces pixel-perfect PNG.
    Falls back to Pillow if MCP is unavailable or fails.

    Returns error message or None on success.
    """
    _diag_log.info(f"[RENDER] start → {png_path.name}")
    drawio_path = png_path.with_suffix(".drawio")

    # ── MCP path (native draw.io quality) ─────────────────────────────────────
    try:
        from tools.drawio_mcp_renderer import render_to_png_via_mcp
        _diag_log.info("[RENDER] trying MCP path")
        mcp_err = render_to_png_via_mcp(xml, drawio_path, png_path)
        if mcp_err is None:
            _diag_log.success(f"[RENDER] MCP OK → {png_path.name}")
            return None
        _diag_log.warning(f"[RENDER] MCP failed: {mcp_err} — falling back to Pillow")
    except ImportError as ie:
        _diag_log.debug(f"[RENDER] MCP not importable ({ie}), using Pillow")
    except Exception as exc:
        _diag_log.warning(f"[RENDER] MCP error: {exc} — falling back to Pillow")

    # ── Pillow fallback ────────────────────────────────────────────────────────
    ok, parse_err = _is_parseable(xml)
    if not ok:
        _diag_log.warning(f"[RENDER] XML not parseable for Pillow: {parse_err}")
        return f"XML parse error: {parse_err}"
    try:
        from tools.drawio_png_renderer import render_to_png
        render_to_png(xml, png_path)
        _diag_log.success(f"[RENDER] Pillow OK → {png_path.name}  ({png_path.stat().st_size:,} bytes)")
        return None
    except Exception as exc:
        _diag_log.error(f"[RENDER] Pillow failed: {exc}")
        return str(exc)


# ── Tool ──────────────────────────────────────────────────────────────────────

@tool
def generate_technical_design_diagram(
    diagram_type: str = "system_architecture",
    project_name: str = "",
) -> str:
    """Generate a draw.io architecture diagram + PNG from technical_design.md.

    Pipeline:
      1. Reads technical_design.md from the session workspace.
      2. Calls gpt-5.4-mini to produce mxGraph XML (dark-header swimlane style).
      3. Saves the XML as workspace/diagrams/{type}.drawio  (always — editable in draw.io).
      4. Renders the XML to PNG via Pillow (non-fatal if XML has render issues).

    API endpoints after tool runs:
      Preview:  GET /api/threads/{id}/workspace/diagrams/{type}.png
      Download: GET /api/threads/{id}/workspace/diagrams/{type}.drawio

    Call 3× after confirm_diagram_generation() approves:
      diagram_type="system_architecture"  → C4 L1 context diagram
      diagram_type="component"            → C4 L2 module diagram
      diagram_type="deployment"           → infrastructure tiers diagram

    Args:
        diagram_type: One of: system_architecture, component, deployment.
        project_name: Optional project name used in the diagram title.

    Returns:
        Paths to saved files. PNG may be absent if XML was too malformed to render.
    """
    if diagram_type not in _VALID_TYPES:
        return f"[Error] Unknown diagram_type '{diagram_type}'. Valid: {', '.join(_VALID_TYPES)}"

    try:
        md_text = _load_technical_design()
    except FileNotFoundError as exc:
        return f"[Error] {exc}"

    content   = _extract_sections(md_text, _section_numbers_for_type(diagram_type))
    model_str = get_agent_model("technical_design_diagram")
    drawio_path, png_path = _output_paths(diagram_type)

    # Phase 1: LLM → sanitized + validated mxGraph XML (up to 3 attempts)
    xml: str = ""
    last_err: str = ""
    _MAX_ATTEMPTS = 3
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            xml = _generate_xml_via_llm(diagram_type, content, project_name)
        except Exception as exc:
            _diag_log.error(f"LLM diagram generation failed (attempt {attempt}): {exc}")
            return f"[Error] Diagram XML generation failed: {exc}"

        if "<mxGraphModel" not in xml:
            last_err = f"LLM did not return mxGraphModel XML (got {len(xml)} chars)"
            _diag_log.warning(f"Attempt {attempt}: {last_err}")
            continue

        valid, reason = _validate_diagram_xml(xml)
        if valid:
            _diag_log.info(f"Diagram XML valid on attempt {attempt}")
            break

        last_err = reason
        _diag_log.warning(f"Attempt {attempt}: diagram validation failed — {reason}. Retrying…")
        xml = ""  # clear so we retry
    else:
        return (
            f"[Error] Diagram XML failed validation after {_MAX_ATTEMPTS} attempts. "
            f"Last error: {last_err}"
        )

    # Phase 2: Save .drawio unconditionally (user can always open in draw.io)
    try:
        drawio_path.write_text(xml, encoding="utf-8")
        _diag_log.success(f"Drawio saved → {drawio_path}")
    except Exception as exc:
        return f"[Error] Failed to save .drawio: {exc}"

    # Phase 3: Render PNG (non-fatal — .drawio is the primary deliverable)
    png_err = _render_png(xml, png_path)

    lines = [
        "Diagram generated:",
        f"  .drawio → {drawio_path}  ({drawio_path.stat().st_size:,} bytes)",
    ]
    if png_err:
        lines.append(f"  .png    → [render failed: {png_err}]")
        lines.append(f"  Note: open the .drawio file in draw.io to export a high-quality PNG.")
    else:
        lines.append(f"  .png    → {png_path}  ({png_path.stat().st_size:,} bytes)")
        lines.append(f"  Preview: GET /api/threads/{{thread_id}}/workspace/diagrams/{diagram_type}.png")
    lines.append(f"Type: {diagram_type} | Model: {model_str}")
    return "\n".join(lines)


# ── Standalone PNG export tool ─────────────────────────────────────────────────

@tool
def export_diagram_png(diagram_type: str = "system_architecture") -> str:
    """Convert an existing .drawio file to PNG.

    Reads workspace/diagrams/{diagram_type}.drawio, renders it to PNG via Pillow,
    and saves workspace/diagrams/{diagram_type}.png.

    Args:
        diagram_type: One of: system_architecture, component, deployment.

    Returns:
        Path to the saved PNG, or an error message.
    """
    if diagram_type not in _VALID_TYPES:
        return f"[Error] Unknown diagram_type '{diagram_type}'. Valid: {', '.join(_VALID_TYPES)}"

    drawio_path, png_path = _output_paths(diagram_type)
    if not drawio_path.exists():
        return (
            f"[Error] {drawio_path.name} not found. "
            f"Run generate_technical_design_diagram(diagram_type='{diagram_type}') first."
        )

    xml = drawio_path.read_text(encoding="utf-8")
    xml = _sanitize_xml(xml)

    png_err = _render_png(xml, png_path)
    if png_err:
        return f"[Error] PNG render failed: {png_err}"

    _diag_log.success(f"PNG exported → {png_path}")
    return f"PNG exported → {png_path}  ({png_path.stat().st_size:,} bytes)"
