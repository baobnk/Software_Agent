"""Render a `BRDDocument` to a .docx file using language-aware templates.

Templates live at `templates/brd/BnK_BRD_Template_{VERSION}_{lang}.docx`
and are produced by `scripts/build_brd_template.py`. This renderer:

  • picks the template matching `brd.language`
  • dumps the AST to a Jinja2-friendly dict
  • lets docxtpl fill placeholders and table-row loops
  • injects the Word updateFields setting so the TOC refreshes on open
  • writes the result to `output_path`

If the template for the requested language is missing, falls back to English
with a logged warning rather than failing the render.
"""
from __future__ import annotations

import logging
from pathlib import Path

from docxtpl import DocxTemplate
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from .schema import BRDDocument

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent     # bnk-deepagent/
TEMPLATES_DIR = ROOT / "templates" / "brd"
TEMPLATE_VERSION = "v2.0"
DEFAULT_LANGUAGE = "en"


def _enable_update_fields(tpl: DocxTemplate) -> None:
    """Add <w:updateFields w:val="true"/> to document settings.

    This instructs Word (and LibreOffice) to update all field codes —
    including the TOC — the first time the document is opened.
    """
    try:
        settings_part = tpl.docx.settings.element
        # Avoid duplicates
        existing = settings_part.find(qn("w:updateFields"))
        if existing is not None:
            return
        uf = OxmlElement("w:updateFields")
        uf.set(qn("w:val"), "true")
        settings_part.append(uf)
    except Exception as e:
        log.warning("_enable_update_fields: could not inject updateFields: %s", e)


def template_path(language: str) -> Path:
    """Return the absolute path to the template for `language`.

    Falls back to the default language if the requested one is missing.
    """
    candidate = TEMPLATES_DIR / f"BnK_BRD_Template_{TEMPLATE_VERSION}_{language}.docx"
    if candidate.exists():
        return candidate

    fallback = TEMPLATES_DIR / f"BnK_BRD_Template_{TEMPLATE_VERSION}_{DEFAULT_LANGUAGE}.docx"
    if fallback.exists():
        log.warning(
            "Template for language %r missing, falling back to %s",
            language, DEFAULT_LANGUAGE,
        )
        return fallback

    raise FileNotFoundError(
        f"No BRD template found for language={language!r} (and no English fallback). "
        f"Run: python scripts/build_brd_template.py"
    )


def available_languages() -> list[str]:
    """List languages for which a template currently exists on disk."""
    if not TEMPLATES_DIR.exists():
        return []
    prefix = f"BnK_BRD_Template_{TEMPLATE_VERSION}_"
    out: list[str] = []
    for p in TEMPLATES_DIR.glob(f"{prefix}*.docx"):
        out.append(p.stem[len(prefix):])
    return sorted(out)


def render_brd_to_docx(brd: BRDDocument, output_path: str | Path) -> Path:
    """Render `brd` to a .docx file at `output_path`. Returns the resolved path.

    The output directory is created if it does not exist.
    """
    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    tpl = DocxTemplate(str(template_path(brd.language)))
    tpl.render(brd.model_dump())
    _enable_update_fields(tpl)  # forces Word to refresh TOC on first open
    tpl.save(str(out))
    return out
