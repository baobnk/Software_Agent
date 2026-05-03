"""Diagram image generation tool using OpenRouter + google/gemini-3.1-flash-image-preview.

Generates solution architecture diagrams as PNG images from text descriptions.

Cost: $0.50/M input tokens + $3/M output tokens (much cheaper than gpt-image-2).
A LangGraph interrupt() is raised before each API call so the user must confirm.

API:  https://openrouter.ai/api/v1/chat/completions
Docs: https://openrouter.ai/docs/guides/overview/multimodal/image-generation
"""
from __future__ import annotations

import base64
import os
from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool
from loguru import logger as _log

from .workspace import get_workspace

_img_log = _log.bind(ctx="diagram_image_gen")

# ── Constants ─────────────────────────────────────────────────────────────────

_MODEL = "google/gemini-3.1-flash-image-preview"
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_ASPECT_RATIO_MAP = {
    "1536x1024": "3:2",
    "1024x1024": "1:1",
    "1024x1536": "2:3",
    "1792x1024": "16:9",
    "1024x1792": "9:16",
}

# ── Visual style template (shared across all diagram types) ───────────────────

_VISUAL_STYLE = """
VISUAL STYLE — follow exactly:
- Background: very dark navy charcoal (#0D1117 or #111827). NOT white. NOT light grey.
- All text: white or very light grey (#F8FAFC) — high contrast on dark background.
- Font: clean modern sans-serif (Inter, Roboto, or Helvetica Neue). Bold for headings.
- Title bar: full-width dark strip at the very top. White bold ALL-CAPS title text.
  Subtitle below in smaller italic white text.
- Section boxes: rounded rectangles with a COLORED HEADER BAND (top 20-25% of box height)
  + dark body (#1E293B). Header band color varies by role (see color coding below).
  Content inside body: small white bullet-point text, key fields, sub-components.
- COLOR CODING by component role:
    Teal/cyan  (#0EA5E9 or #00BCD4) — core AI/processing engine (the dominant center piece)
    Blue       (#2563EB or #1A73E8) — UI / web application / review portal
    Amber/gold (#F59E0B or #D97706) — notifications / alerts / human review
    Green      (#10B981 or #059669) — approved / success / output paths
    Purple     (#7C3AED)            — future / later-phase / external integrations (dashed border)
    Steel blue (#334155)            — data stores / databases
- Main processing engine: VISUALLY DOMINANT — at least 2× wider and taller than other boxes.
  Placed in the center-left area. Contains sub-boxes showing its internal modules.
- Numbered circles (filled colored circles with white number): mark each step in flow (1→2→3…)
- Arrows: semi-transparent white or light grey lines with small arrowheads.
  Solid lines = current-phase flow. Dashed lines = future-phase or optional paths.
  Each arrow has a short label (2–4 words) in small white text.
- "HUMAN-IN-THE-LOOP" badge: amber pill-shaped label near the review/correction step.
- Legend box: bottom-left corner. Dark box with small colored swatches + labels.
  Shows: solid arrow=current flow, dashed=future phase, color meanings.
- Overall aesthetic: professional enterprise architecture POSTER / technical infographic.
  Must look like a slide from a senior consultant's deck — polished, not generic.
"""

# ── Per-diagram-type layout hints ─────────────────────────────────────────────

_LAYOUT_HINTS: dict[str, str] = {
    "system_architecture": """
LAYOUT (left-to-right processing flow on dark canvas):

LEFT COLUMN (narrow, intake):
  - "EMAIL INTAKE" small box at top (amber tinted)
  - Below: "1. DOCUMENT PRE-PROCESSING MODULE" section (teal header)
    Sub-items in body: Normalize Pages, Detect Orientation, Skew Correction, Quality Check

CENTER-LEFT (dominant, large box — 35% canvas width):
  - "IDP PROCESSING ENGINE" (teal header, very large)
    Label beneath: "(OCR & AI Analysis)" in italic
    Sub-boxes inside: "OCR Module", "Document Understanding Models", "Field Extraction"
    Show extracted fields as small tags: Vendor, Invoice #, Date, Amount, Tax, PO Ref
    Bottom of box: "Confidence Scoring" + "Field Validation Rules" row

CENTER-RIGHT:
  - "5. WEB REVIEW & VALIDATION UI" (blue header, medium size)
    Body: High Confidence → auto-queue, Low Confidence → manual review flag
    "HUMAN-IN-THE-LOOP" amber badge here
    Shows: CORRECT DATA / APPROVE / FLAG actions
  - Below: small "APPROVED" green output indicator

RIGHT COLUMN:
  - "NOTIFICATION SERVICE" (amber header, small box, top right)
    Sub: Alert Channels, Email Digests
  - "LATER-PHASE INTEGRATIONS" section (purple dashed border)
    Sub-items: Approval Workflow, ERP Connector (Sage), Payment Batching
    Label: "OUT OF POC SCOPE — Phase 2+"

BOTTOM BAR (full width, dark steel):
  - "4. DATA TIER" label
  - "DOCUMENT STORE" cylinder icon (steel blue)
  - "METADATA DATABASE" cylinder icon (steel blue) — with: Invoice Records, Audit Trail, User Edits
  - Right of bottom bar: "6. READY FOR DOWNSTREAM ACTIONS" green section

NUMBER FLOW: Circles with numbers 1→2→3→4→5→6 showing the sequence.
""",
    "component": """
LAYOUT (3 horizontal tier rows on dark canvas):

TOP ROW — "INTAKE & PRE-PROCESSING" (teal header band):
  Two modules side by side: Email Intake Module | Document Pre-processing Module
  Each box shows 3–4 bullet sub-responsibilities.

MIDDLE ROW — "INTELLIGENCE CORE" (blue header band, slightly taller):
  Three modules: OCR & Extraction | Validation & Review | Workflow State
  OCR & Extraction is wider (key module). Show confidence scoring sub-item inside it.
  "HUMAN-IN-THE-LOOP" badge on Validation & Review box.

BOTTOM ROW — "PLATFORM SERVICES" (steel header band):
  Four modules: Audit & Traceability | API / Integration | Notification | Reporting

Arrows flow downward between rows with labels. Inter-module arrows within rows are horizontal.
""",
    "deployment": """
LAYOUT (5 horizontal swimlane tiers, top-to-bottom, full-width dark canvas):

Tier 1 — PRESENTATION (blue header): Web Review Portal, AP User Browser, Approver Browser
Tier 2 — APPLICATION (teal header): FastAPI Service, Email Worker, OCR/AI Worker, Workflow Engine
Tier 3 — INTELLIGENCE (amber header): OCR Engine, AI Extraction Model, Confidence Scorer
Tier 4 — DATA (steel header): PostgreSQL DB, Object Storage / S3, Redis Cache
Tier 5 — INTEGRATION (purple dashed header): Email Connector, Future Sage ERP, Approval API

Vertical arrows between tiers show HTTP calls and DB queries. Each tier is a distinct dark band.
""",
    "data_flow": """
LAYOUT (left-to-right DFD on dark canvas):

External entities (amber rectangles, leftmost and rightmost columns):
  Left: "Email / Upload" source
  Right: "Downstream API / ERP" sink

Processes (teal rounded rectangles, middle columns, numbered P1–P6):
  P1: Receive & Store PDF → P2: Pre-process → P3: OCR Extraction →
  P4: Confidence Scoring → P5: Route to Review → P6: User Review & Correct

Data stores (steel blue open-ended rectangles, along bottom):
  DS1: Document Store | DS2: Metadata Database

Flow arrows show data moving left-to-right through processes.
Feedback loop: P6 writes corrections back to DS2.
""",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_prompt(diagram_type: str, content: str) -> str:
    layout = _LAYOUT_HINTS.get(diagram_type, "")
    return (
        f"Create a PRODUCTION-QUALITY dark-themed technical architecture infographic diagram.\n\n"
        f"{_VISUAL_STYLE}\n\n"
        f"DIAGRAM TYPE: {diagram_type.replace('_', ' ').upper()}\n\n"
        f"LAYOUT SPECIFICATION:\n{layout}\n\n"
        f"ARCHITECTURE CONTENT (extract all component names, responsibilities, and "
        f"data flows from this — use the exact names from the content):\n{content}\n\n"
        "FINAL CHECKLIST before rendering:\n"
        "□ Dark background (#0D1117) — NOT white or light\n"
        "□ IDP Processing Engine box is the largest element (dominant center piece)\n"
        "□ Numbered flow circles (1→2→3...) visible\n"
        "□ HUMAN-IN-THE-LOOP badge present near review step\n"
        "□ Legend box in bottom-left corner\n"
        "□ Title bar at top with full system name\n"
        "□ All text is white/light and legible\n"
        "□ Later-phase integrations have dashed purple borders\n"
    )


def _call_openrouter_image_api(prompt: str, aspect_ratio: str) -> bytes:
    import requests  # noqa: PLC0415 — lazy import

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set in environment")

    payload = {
        "model": _MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image", "text"],
        "image_config": {"aspect_ratio": aspect_ratio},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    _img_log.info(f"Calling OpenRouter {_MODEL} | aspect_ratio={aspect_ratio} | prompt_len={len(prompt)}")
    resp = requests.post(_OPENROUTER_URL, json=payload, headers=headers, timeout=120)

    if not resp.ok:
        raise RuntimeError(f"OpenRouter API error {resp.status_code}: {resp.text[:500]}")

    result = resp.json()

    # Extract image from response — OpenRouter returns images in message.images
    message = result["choices"][0]["message"]
    images = message.get("images") or []

    if not images:
        # Fallback: check content array for image_url parts
        content_parts = message.get("content") or []
        if isinstance(content_parts, list):
            images = [
                p for p in content_parts
                if isinstance(p, dict) and p.get("type") == "image_url"
            ]

    if not images:
        raise RuntimeError(
            f"No images in response. Message content: {str(message)[:300]}"
        )

    data_url: str = images[0].get("image_url", {}).get("url", "")
    if not data_url:
        raise RuntimeError(f"Empty image URL in response: {images[0]}")

    # data_url = "data:image/png;base64,<b64data>"
    if "," in data_url:
        b64_data = data_url.split(",", 1)[1]
    else:
        b64_data = data_url

    return base64.b64decode(b64_data)


def _save_image(image_bytes: bytes, diagram_type: str) -> Path:
    ws = get_workspace()
    diagrams_dir = ws / "diagrams"
    diagrams_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = diagrams_dir / f"{diagram_type}_{timestamp}.png"
    out_path.write_bytes(image_bytes)
    _img_log.success(f"Image saved → {out_path} ({len(image_bytes):,} bytes)")
    return out_path


# ── Tool ──────────────────────────────────────────────────────────────────────

@tool
def generate_solution_diagram_image(
    diagram_type: str,
    content: str,
    size: str = "1536x1024",
) -> str:
    """Generate a solution architecture diagram as PNG using OpenRouter Gemini image model.

    A HITL interrupt WILL pause the graph before the API call — the user must
    approve before the image is generated.

    Cost: ~$0.50/M input + $3/M output tokens (via OpenRouter).
    Requires OPENROUTER_API_KEY in environment.

    Args:
        diagram_type: One of: system_architecture, component, deployment,
                      data_flow, integration, sequence.
        content:      Key components, flows, and labels to include.
                      Extract from technical_design.md section 3 or 4.
        size:         "1536x1024" (landscape, default), "1024x1024" (square),
                      "1792x1024" (wide 16:9), "1024x1536" (portrait).

    Returns:
        Absolute path of saved PNG file, or cancellation message.
    """
    if diagram_type not in _DIAGRAM_CONTEXT:
        valid = ", ".join(_DIAGRAM_CONTEXT.keys())
        return f"[Error] Unknown diagram_type '{diagram_type}'. Valid: {valid}"
    if size not in _ASPECT_RATIO_MAP:
        valid = ", ".join(_ASPECT_RATIO_MAP.keys())
        return f"[Error] Invalid size '{size}'. Valid: {valid}"

    prompt = _build_prompt(diagram_type, content)
    aspect_ratio = _ASPECT_RATIO_MAP[size]

    # HITL: pause graph before spending tokens
    try:
        from langgraph.types import interrupt  # noqa: PLC0415
        decision = interrupt({
            "tool": "generate_solution_diagram_image",
            "message": (
                f"Xác nhận generate diagram '{diagram_type}'?\n"
                f"Model: {_MODEL} (via OpenRouter)\n"
                f"Size: {size} (aspect_ratio={aspect_ratio})\n"
                f"Cost: ~$0.50/M input + $3/M output tokens\n\n"
                f"Prompt preview:\n{prompt[:400]}..."
            ),
            "diagram_type": diagram_type,
            "model": _MODEL,
            "size": size,
            "aspect_ratio": aspect_ratio,
            "prompt_preview": prompt[:400],
        })
        if not decision or decision.get("approved") is not True:
            _img_log.info(f"generate_solution_diagram_image cancelled | {diagram_type}")
            return "[Cancelled] Image generation cancelled. No API call was made."
    except ImportError:
        _img_log.warning("LangGraph interrupt not available — skipping HITL (test mode)")

    try:
        image_bytes = _call_openrouter_image_api(prompt, aspect_ratio)
    except Exception as exc:
        _img_log.error(f"OpenRouter image generation failed: {exc}")
        return f"[Error] Image generation failed: {exc}"

    try:
        out_path = _save_image(image_bytes, diagram_type)
    except Exception as exc:
        _img_log.error(f"Failed to save image: {exc}")
        return f"[Error] Image generated but failed to save: {exc}"

    return (
        f"Diagram saved → {out_path}\n"
        f"Type: {diagram_type} | Model: {_MODEL} | Size: {size} | "
        f"{len(image_bytes):,} bytes"
    )
