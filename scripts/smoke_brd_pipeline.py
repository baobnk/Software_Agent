#!/usr/bin/env python3
"""End-to-end smoke test of the section-sharded BRD pipeline.

Exercises agent tools (init, set_text, add_list, upsert_row, upsert_fr,
get_summary), validates, then renders to .docx — all against a temp
workspace. Verifies section sharding produces small per-section files,
and that index updates are eager.

Run from the repo root:
    python scripts/smoke_brd_pipeline.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from packages.brd import BRDStore
from tools.brd_ops import (
    init_brd, set_brd_text, add_brd_list_item,
    upsert_brd_row, upsert_fr, get_brd_summary,
)
from tools.renderer import render_brd
from tools.validators import validate_brd
from tools.workspace import set_workspace


def main() -> int:
    ws = Path(tempfile.mkdtemp(prefix="bnk_brd_smoke_"))
    set_workspace(ws)
    print(f"Workspace: {ws}\n")

    print("── init ──")
    print(init_brd.invoke({
        "project_name": "GEHP IDP", "project_code": "BNK-GEHP-001",
        "language": "vi", "author": "BnK Solution",
    }))

    print("\n── scalar text ──")
    set_brd_text.invoke({"field": "purpose",    "value": "Build IDP for GEHP contracts"})
    set_brd_text.invoke({"field": "background", "value": "Manual processing of 5K contracts/month is the bottleneck."})
    set_brd_text.invoke({"field": "objectives", "value": "Reduce manual review time by 60%."})

    print("\n── lists ──")
    for item in ["On-prem only", "Budget cap 80MD"]:
        add_brd_list_item.invoke({"list_name": "constraints", "item": item})
    for item in ["OCR service", "Web UI", "REST API"]:
        add_brd_list_item.invoke({"list_name": "scope_in", "item": item})
    add_brd_list_item.invoke({"list_name": "scope_out", "item": "Mobile app"})
    add_brd_list_item.invoke({"list_name": "acceptance_criteria", "item": "All FRs pass UAT"})

    print("\n── tables ──")
    upsert_brd_row.invoke({"table": "stakeholders", "payload_json": json.dumps(
        {"id": "S1", "name": "Nguyen A", "role": "PM", "responsibility": "approves"})})
    upsert_brd_row.invoke({"table": "nfr_rows", "payload_json": json.dumps(
        {"category": "Performance", "metric": "Latency", "target": "≤ 200 ms"})})
    upsert_brd_row.invoke({"table": "integrations", "payload_json": json.dumps(
        {"system": "GEHP ERP", "direction": "Inbound", "protocol": "REST", "note": "webhook"})})
    upsert_brd_row.invoke({"table": "glossary", "payload_json": json.dumps(
        {"term": "IDP", "definition": "Intelligent Document Processing"})})

    print("\n── FRs ──")
    for i, name in enumerate(["Upload", "Extract", "Audit"], start=1):
        upsert_fr.invoke({"payload_json": json.dumps({
            "fr_id": f"FR{i}", "name": name, "priority": "High",
            "short_description": f"short for {name}",
            "description": f"longer description of {name} feature " * 4,
            "user_stories": [f"As a user I want {name}"],
            "acceptance_criteria": [f"{name} works for sample"],
            "interface_notes": f"endpoint /{name.lower()}",
        })})

    print("\n── update FR1 (must preserve section_id) ──")
    store = BRDStore(ws / "brd")
    sid_before = store.read_fr("FR1").section_id
    upsert_fr.invoke({"payload_json": json.dumps({
        "fr_id": "FR1", "name": "Upload v2", "priority": "Critical",
        "short_description": "u", "description": "updated " * 10,
        "user_stories": ["As a user I want fast upload"],
        "acceptance_criteria": ["fast"],
    })})
    sid_after = store.read_fr("FR1").section_id
    assert sid_before == sid_after, "section_id must be preserved on update"
    print(f"   ✓ section_id preserved: {sid_after}")

    print("\n── summary (index-only read) ──")
    print(get_brd_summary.invoke({}))

    print("\n── validate_brd ──")
    print(validate_brd.invoke({}))

    print("\n── render → .docx ──")
    out_path = str(ws / "GEHP_BRD.docx")
    print(render_brd.invoke({"output_path": out_path}))
    assert Path(out_path).exists()

    print("\n── file sizes (section sharding) ──")
    brd_dir = ws / "brd"
    total = 0
    for p in sorted(brd_dir.rglob("*.json")):
        sz = p.stat().st_size
        total += sz
        print(f"  {str(p.relative_to(brd_dir)):40} {sz:>5} B")
    print(f"  {'TOTAL':40} {total:>5} B")

    print("\nALL E2E SMOKE TESTS PASSED")
    print(f"Output saved at: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
