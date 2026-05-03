#!/usr/bin/env python3
"""Smoke-render every BRD template with a fixture context.

Verifies that:
  • docxtpl can parse the template (no syntax errors in jinja tags)
  • all loops / placeholders match the fixture schema
  • output renders without missing-variable errors

Outputs to /tmp/brd_smoke_<lang>.docx — open them in Word to spot-check.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from docxtpl import DocxTemplate

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "templates" / "brd"
OUT_DIR = ROOT / "sample_brd"


def fixture_context() -> dict:
    """Realistic-shaped data covering every loop and placeholder."""
    return {
        "project_name": "GEHP Document Intelligence Platform",
        "project_code": "BNK-GEHP-001",
        "version": "0.1.0",
        "author": "BnK Solution",
        "created_at": str(date.today()),
        "version_history": [
            {"version": "0.1.0", "date": "2026-04-29", "description": "Initial draft", "author": "BnK"},
        ],
        "purpose": (
            "Establish a unified document intelligence platform that ingests, "
            "classifies, and extracts structured data from contract files."
        ),
        "intended_audience": [
            {"role": "Project Manager", "party": "GEHP", "responsibility": "Approves scope and timeline"},
            {"role": "Tech Lead",       "party": "BnK",  "responsibility": "Owns architecture and delivery"},
        ],
        "background": "GEHP currently processes 5,000+ contracts/month manually...",
        "objectives": "Reduce manual review time by 60%; achieve 95% extraction accuracy on key fields.",
        "constraints": [
            "Must run on-premises (no public cloud).",
            "Initial budget capped at 80 man-days.",
        ],
        "assumptions": [
            "Sample contract dataset (≥500 docs) is available before sprint 1.",
            "GEHP IT team will provide VM resources within 1 week of kickoff.",
        ],
        "scope_in": [
            "OCR + IDP service for contract documents",
            "Web UI for human review and correction",
            "REST API for downstream system integration",
        ],
        "scope_out": [
            "Mobile app",
            "Migration of legacy archive (>2 years old)",
        ],
        "stakeholders": [
            {"id": "S1", "name": "Nguyen Van A", "role": "Sponsor",     "responsibility": "Funds project, signs off"},
            {"id": "S2", "name": "Le Thi B",    "role": "BA Lead",     "responsibility": "Captures requirements"},
            {"id": "S3", "name": "Tran C",      "role": "Solution Arch.", "responsibility": "Designs architecture"},
        ],
        "functional_requirements": [
            {
                "fr_id": "FR1",
                "name": "Document Upload",
                "priority": "Critical",
                "short_description": "Users can upload PDF/DOCX/image files for processing",
                "description": (
                    "The system shall accept document uploads via web UI and REST API, "
                    "validating file type and size at the boundary."
                ),
                "user_stories": [
                    "As a reviewer, I want to drag-and-drop multiple files so I can batch-process quickly.",
                    "As an integrator, I want a REST endpoint so I can push files from the upstream ERP.",
                ],
                "acceptance_criteria": [
                    "Files up to 50 MB are accepted; larger files return 413.",
                    "Supported formats: PDF, DOCX, PNG, JPG, TIFF.",
                ],
                "interface_notes": "POST /api/v1/documents — multipart form-data; returns {document_id, status}.",
            },
            {
                "fr_id": "FR2",
                "name": "Field Extraction",
                "priority": "High",
                "short_description": "Auto-extract key contract fields with confidence scores",
                "description": "The system extracts party names, dates, amounts, and clauses with per-field confidence.",
                "user_stories": [
                    "As a reviewer, I want extracted fields highlighted so I can verify them quickly.",
                ],
                "acceptance_criteria": [
                    "Mean accuracy ≥ 95% on the validation set (n=200).",
                    "Each extracted field carries a confidence score in [0, 1].",
                ],
                "interface_notes": "Async job; results delivered via webhook or GET /api/v1/documents/{id}/fields.",
            },
        ],
        "nfr_rows": [
            {"category": "Performance",  "metric": "Avg processing time / page", "target": "≤ 3 s"},
            {"category": "Scalability",  "metric": "Concurrent uploads",         "target": "≥ 50"},
            {"category": "Availability", "metric": "Monthly uptime",             "target": "≥ 99.5 %"},
            {"category": "Security",     "metric": "Auth method",                "target": "OAuth 2.0 + RBAC"},
        ],
        "data_requirements": (
            "Input: PDF/DOCX/image up to 50 MB. Output: JSON document with extracted "
            "fields, bounding boxes, and per-field confidence. Retention: 90 days hot, "
            "1 year cold archive."
        ),
        "integrations": [
            {"system": "GEHP ERP",        "direction": "Inbound",  "protocol": "REST",   "note": "Webhook on completion"},
            {"system": "Active Directory", "direction": "Inbound",  "protocol": "LDAP",   "note": "User SSO"},
            {"system": "S3 (MinIO)",       "direction": "Outbound", "protocol": "S3 API", "note": "Document archive"},
        ],
        "acceptance_criteria": [
            "All FR1-FR2 acceptance items pass UAT.",
            "Validation set accuracy meets NFR target.",
            "Documentation handover complete (BRD, WBS, runbook).",
        ],
        "glossary": [
            {"term": "IDP", "definition": "Intelligent Document Processing"},
            {"term": "OCR", "definition": "Optical Character Recognition"},
            {"term": "BRD", "definition": "Business Requirements Document"},
        ],
        "appendix": "Reference materials, sample contracts, and prior BRD links live in the project SharePoint.",
    }


def render(template_path: Path, ctx: dict, out_path: Path) -> None:
    tpl = DocxTemplate(str(template_path))
    tpl.render(ctx)
    tpl.save(str(out_path))


def main() -> int:
    if not TEMPLATES_DIR.exists():
        print(f"ERROR: templates directory missing: {TEMPLATES_DIR}", file=sys.stderr)
        print("Run: python scripts/build_brd_template.py", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ctx = fixture_context()

    templates = sorted(TEMPLATES_DIR.glob("BnK_BRD_Template_v*.docx"))
    if not templates:
        print(f"ERROR: no templates found in {TEMPLATES_DIR}", file=sys.stderr)
        return 1

    fails: list[tuple[str, str]] = []
    for tpl_path in templates:
        # Extract language suffix from filename: ..._v2.0_en.docx → 'en'
        lang = tpl_path.stem.rsplit("_", 1)[-1]
        out_path = OUT_DIR / f"brd_smoke_{lang}.docx"
        try:
            render(tpl_path, ctx, out_path)
            size_kb = out_path.stat().st_size // 1024
            print(f"  ✓ {lang:>3}  →  {out_path}  ({size_kb} KB)")
        except Exception as e:
            print(f"  ✗ {lang:>3}  →  FAILED: {e}", file=sys.stderr)
            fails.append((lang, str(e)))

    if fails:
        print(f"\n{len(fails)} template(s) failed to render.", file=sys.stderr)
        return 1

    print(f"\nAll {len(templates)} templates rendered successfully → {OUT_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
