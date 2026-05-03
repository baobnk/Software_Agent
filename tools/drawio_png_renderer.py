"""Pure-Python mxGraph XML → PNG renderer using Pillow only.

No browser, no Node.js, no Electron required.
Handles: swimlane containers, vertex nodes (rounded rects), edges, labels.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

# ── Design tokens ──────────────────────────────────────────────────────────────

_CANVAS_BG   = (248, 250, 252)   # #F8FAFC
_TITLE_FG    = (15, 23, 42)      # #0F172A
_BODY_BG     = (255, 255, 255)   # white swimlane body
_EDGE_COLOR  = (100, 116, 139)   # #64748B
_LABEL_FG    = (30, 41, 59)      # #1E293B
_HEADER_TEXT = (255, 255, 255)   # white header labels

_SCALE       = 0.6   # scale factor: 1654×1169 → ~992×701
_PADDING     = 20    # canvas padding in original coords

# fillColor presets (header band colours for swimlanes / node backgrounds)
_FILL_COLORS: dict[str, tuple] = {
    "#0F172A": (15, 23, 42),
    "#1E3A5F": (30, 58, 95),
    "#064E3B": (6, 78, 59),
    "#78350F": (120, 53, 15),
    "#3B0764": (59, 7, 100),
    "#1E293B": (30, 41, 59),
    # node fills
    "#FFF7ED": (255, 247, 237),
    "#EFF6FF": (239, 246, 255),
    "#F0FDF4": (240, 253, 244),
    "#FFFBEB": (255, 251, 235),
    "#FAF5FF": (250, 245, 255),
    "#F8FAFC": (248, 250, 252),
}

_STROKE_COLORS: dict[str, tuple] = {
    "#EA580C": (234, 88, 12),
    "#2563EB": (37, 99, 235),
    "#059669": (5, 150, 105),
    "#D97706": (217, 119, 6),
    "#7C3AED": (124, 58, 237),
    "#64748B": (100, 116, 139),
}

_DEFAULT_FILL   = (255, 255, 255)
_DEFAULT_STROKE = (100, 116, 139)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Cell:
    id: str
    value: str
    style: dict[str, str]
    # geometry (in mxGraph coordinates, relative to parent)
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    parent: str = "1"
    is_vertex: bool = True
    is_edge: bool = False
    source: str = ""
    target: str = ""
    # absolute position (computed after parsing)
    abs_x: float = 0.0
    abs_y: float = 0.0


# ── XML parsing ───────────────────────────────────────────────────────────────

def _parse_style(style_str: str) -> dict[str, str]:
    d: dict[str, str] = {}
    for part in (style_str or "").split(";"):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            d[k.strip()] = v.strip()
        elif part:
            d[part] = "1"
    return d


def _hex_to_rgb(s: str) -> tuple[int, int, int]:
    s = (s or "").strip().lstrip("#")
    if len(s) == 3:
        s = s[0]*2 + s[1]*2 + s[2]*2
    if len(s) != 6:
        return _DEFAULT_FILL
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return _DEFAULT_FILL


def _color(style: dict[str, str], key: str, defaults: dict, fallback: tuple) -> tuple[int, int, int]:
    v = style.get(key, "")
    if v and v != "none":
        if v in defaults:
            return defaults[v]
        if v.startswith("#"):
            return _hex_to_rgb(v)
    return fallback


def parse_drawio(xml_str: str) -> list[Cell]:
    root = ET.fromstring(xml_str)
    ns = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""

    cells: list[Cell] = []
    for elem in root.iter():
        if elem.tag.split("}")[-1] != "mxCell":
            continue
        cid = elem.get("id", "")
        if cid in ("0", "1"):
            continue

        value = (elem.get("value") or "").replace("\\n", "\n").replace("<br>", "\n")
        style  = _parse_style(elem.get("style", ""))
        parent = elem.get("parent", "1")
        vertex = elem.get("vertex") == "1"
        edge   = elem.get("edge") == "1"
        source = elem.get("source", "")
        target = elem.get("target", "")

        geo = elem.find("mxGeometry") or elem.find(
            f"{{{ns}}}mxGeometry" if ns else "mxGeometry"
        )
        x = float(geo.get("x", 0)) if geo is not None else 0.0
        y = float(geo.get("y", 0)) if geo is not None else 0.0
        w = float(geo.get("width", 0)) if geo is not None else 0.0
        h = float(geo.get("height", 0)) if geo is not None else 0.0

        cells.append(Cell(
            id=cid, value=value, style=style,
            x=x, y=y, w=w, h=h,
            parent=parent, is_vertex=vertex, is_edge=edge,
            source=source, target=target,
        ))
    return cells


def resolve_positions(cells: list[Cell]) -> dict[str, Cell]:
    by_id: dict[str, Cell] = {c.id: c for c in cells}

    def _abs(c: Cell) -> tuple[float, float]:
        if c.parent == "1" or c.parent not in by_id:
            return c.x, c.y
        p = by_id[c.parent]
        px, py = _abs(p)
        start_size = float(p.style.get("startSize", 0))
        return px + c.x, py + c.y + start_size

    for c in cells:
        if c.is_vertex and not c.is_edge:
            c.abs_x, c.abs_y = _abs(c)

    return by_id


# ── Pillow rendering ──────────────────────────────────────────────────────────

def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    try:
        face = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
        return ImageFont.truetype(face, size)
    except (IOError, OSError):
        pass
    try:
        import platform
        fonts = (
            ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]
            if platform.system() != "Windows" else
            ["C:/Windows/Fonts/arial.ttf"]
        )
        for f in fonts:
            if Path(f).exists():
                return ImageFont.truetype(f, size)
    except Exception:
        pass
    return ImageFont.load_default()


def _draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    x: float, y: float, w: float, h: float,
    radius: float,
    fill: tuple,
    stroke: tuple,
    stroke_width: int = 2,
) -> None:
    r = min(int(radius), int(w // 2), int(h // 2))
    x, y, w, h = int(x), int(y), int(w), int(h)
    draw.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=fill, outline=stroke, width=stroke_width)


def _wrap_text(text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        if not para:
            lines.append("")
            continue
        words = para.split()
        cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            bbox = font.getbbox(test)
            if bbox[2] - bbox[0] <= max_width:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
    return lines or [""]


def _draw_text_centered(
    draw: ImageDraw.ImageDraw,
    cx: float, cy: float, text: str,
    font: ImageFont.ImageFont,
    color: tuple,
    max_w: int = 10000,
) -> None:
    wrapped = _wrap_text(text, font, max_w)
    line_h = font.getbbox("Ag")[3] + 2
    total_h = len(wrapped) * line_h
    top = cy - total_h / 2
    for line in wrapped:
        bbox = font.getbbox(line)
        lw = bbox[2] - bbox[0]
        draw.text((cx - lw / 2, top), line, font=font, fill=color)
        top += line_h


def _arrow_head(
    draw: ImageDraw.ImageDraw,
    x1: float, y1: float, x2: float, y2: float,
    color: tuple, size: int = 8,
) -> None:
    angle = math.atan2(y2 - y1, x2 - x1)
    pts = [
        (x2, y2),
        (x2 - size * math.cos(angle - 0.4), y2 - size * math.sin(angle - 0.4)),
        (x2 - size * math.cos(angle + 0.4), y2 - size * math.sin(angle + 0.4)),
    ]
    draw.polygon(pts, fill=color)


def render_to_png(xml_str: str, output_path: Path, scale: float = _SCALE) -> None:
    """Parse mxGraph XML and render to PNG using Pillow."""
    cells = parse_drawio(xml_str)
    by_id = resolve_positions(cells)

    # Detect canvas dimensions from pageWidth/pageHeight attributes
    root = ET.fromstring(xml_str)
    pw = float(root.get("pageWidth", 1654))
    ph = float(root.get("pageHeight", 1169))

    img_w = int(pw * scale)
    img_h = int(ph * scale)
    img = Image.new("RGB", (img_w, img_h), _CANVAS_BG)
    draw = ImageDraw.Draw(img)

    font_title  = _font(int(18 * scale), bold=True)
    font_header = _font(int(13 * scale), bold=True)
    font_node   = _font(int(11 * scale), bold=False)
    font_edge   = _font(int(9  * scale), bold=False)

    def s(v: float) -> float:
        return v * scale

    # ── Pass 1: swimlane containers (paint bottom → top so body is behind nodes)
    for c in cells:
        if not c.is_vertex or c.is_edge:
            continue
        if c.style.get("swimlane") != "1":
            continue

        x, y, w, h = s(c.abs_x), s(c.abs_y), s(c.w), s(c.h)
        hdr_h = s(float(c.style.get("startSize", 38)))
        fill_hex = c.style.get("fillColor", "#1E293B")
        fill_rgb = _color(c.style, "fillColor", _FILL_COLORS, (30, 41, 59))
        stroke_rgb = _color(c.style, "strokeColor", _FILL_COLORS, fill_rgb)

        # Body (white)
        draw.rectangle([int(x), int(y), int(x + w), int(y + h)], fill=_BODY_BG, outline=stroke_rgb, width=1)
        # Header band
        draw.rectangle([int(x), int(y), int(x + w), int(y + hdr_h)], fill=fill_rgb, outline=stroke_rgb, width=1)
        # Label
        _draw_text_centered(draw, x + w / 2, y + hdr_h / 2, c.value, font_header, _HEADER_TEXT, int(w - 8))

    # ── Pass 2: vertex nodes (non-swimlane)
    for c in cells:
        if not c.is_vertex or c.is_edge:
            continue
        if c.style.get("swimlane") == "1":
            continue
        if c.style.get("text") == "1":
            # title cell
            x, y, w, h = s(c.abs_x), s(c.abs_y), s(c.w), s(c.h)
            _draw_text_centered(draw, x + w / 2, y + h / 2, c.value, font_title, _TITLE_FG, int(w - 16))
            continue

        x, y, w, h = s(c.abs_x), s(c.abs_y), s(c.w), s(c.h)
        fill_rgb   = _color(c.style, "fillColor",   _FILL_COLORS,   _DEFAULT_FILL)
        stroke_rgb = _color(c.style, "strokeColor", _STROKE_COLORS, _DEFAULT_STROKE)
        sw = int(float(c.style.get("strokeWidth", 2)) * scale)
        is_cylinder = c.style.get("shape") in ("cylinder3", "cylinder")

        if is_cylinder:
            # Draw as ellipse-topped rectangle (simplified)
            eh = max(8, int(h * 0.18))
            draw.rectangle([int(x), int(y + eh), int(x + w), int(y + h)], fill=fill_rgb, outline=stroke_rgb, width=sw)
            draw.ellipse([int(x), int(y), int(x + w), int(y + 2 * eh)], fill=fill_rgb, outline=stroke_rgb, width=sw)
        else:
            radius = int(float(c.style.get("arcSize", 8)) / 100 * min(w, h))
            _draw_rounded_rect(draw, x, y, w, h, radius, fill_rgb, stroke_rgb, sw)

        _draw_text_centered(draw, x + w / 2, y + h / 2, c.value, font_node, _LABEL_FG, int(w - 8))

    # ── Pass 3: edges
    for c in cells:
        if not c.is_edge:
            continue
        src = by_id.get(c.source)
        tgt = by_id.get(c.target)
        if src is None or tgt is None:
            continue
        x1 = s(src.abs_x + src.w / 2)
        y1 = s(src.abs_y + src.h / 2)
        x2 = s(tgt.abs_x + tgt.w / 2)
        y2 = s(tgt.abs_y + tgt.h / 2)
        draw.line([(x1, y1), (x2, y2)], fill=_EDGE_COLOR, width=max(1, int(1.5 * scale)))
        _arrow_head(draw, x1, y1, x2, y2, _EDGE_COLOR, int(8 * scale))
        if c.value:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            _draw_text_centered(draw, mx, my - int(8 * scale), c.value, font_edge, _EDGE_COLOR)

    img.save(str(output_path), "PNG", optimize=True)
