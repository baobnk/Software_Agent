#!/usr/bin/env python3
"""End-to-end run on a realistic mini project.

Skips the chatty intake + solution-finder phases and feeds a hand-crafted
raw_features.md + technical_design.md directly. Then invokes the two
workflow tools (real LLM) to produce WBS .xlsx and BRD .docx.

Outputs land at: <repo>/sample_outputs/<project_slug>/

Run:
    python scripts/run_real_project.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# Override to a known-good cheap model so the test is deterministic on cost
os.environ.setdefault("MODEL_WBS_ESTIMATOR", "openai:gpt-4o-mini")
os.environ.setdefault("MODEL_BRD_DRAFTER",   "openai:gpt-4o-mini")

from tools.workspace import set_workspace
from agents.wbs_workflow import run_wbs_workflow
from agents.brd_workflow import run_brd_workflow

OUT_ROOT = ROOT / "sample_outputs"
PROJECT_SLUG = "library_mvp"

# ── Mini project fixture: Library Book Management System ─────────────────────

RAW_FEATURES = """\
# Library Book Management System (MVP)

**Source:** internal product brief
**Analyzed:** 2026-04-29

## 1. Bài toán

A small public library currently tracks books and borrowing on paper. They
need a web app for staff to manage the catalog and member borrowings, plus
a public search page for patrons.

- Current state: paper logs, no central catalog
- Target state: web app with login for staff + public read-only search

## 2. Business Cases

### Business Case 1: Catalog management
- Bối cảnh: 5,000+ books, growing 200/month
- Mục tiêu: digitize catalog, auto-generate barcode labels
- Kết quả: search by title / author / ISBN in <1s

### Business Case 2: Borrowing tracking
- Bối cảnh: 800 members, ~150 transactions/week
- Mục tiêu: track who has which book, due dates, overdue list

### Business Case 3: Public search
- Bối cảnh: patrons want to check availability before visiting
- Mục tiêu: public page (no login) for catalog browse + availability

## 3. Functional Requirements (draft)

| ID  | Name | Priority | Description |
|-----|------|----------|-------------|
| FR1 | Catalog CRUD | Critical | Staff add/edit/delete books with metadata |
| FR2 | Borrow / Return | Critical | Staff record borrow + return with due dates |
| FR3 | Public Search | High | Patrons search catalog without login |
| FR4 | Overdue Report | Medium | Daily report of overdue items |

## 4. Non-Functional Requirements

| Category | Metric | Target |
|----------|--------|--------|
| Performance | Search response | ≤ 500 ms |
| Availability | Uptime | ≥ 99 % business hours |
| Security | Staff auth | OAuth2 + role-based |
| Scalability | Concurrent users | ≥ 30 |

## 5. Stakeholders

- Library Director — sponsor, signs off
- Head Librarian — primary user, BA contact
- 4 staff librarians — daily users
- IT volunteer — deployment support

## 6. Constraints

- On-prem deployment (small Linux server)
- Budget cap: 25 man-days
- 3-month timeline for MVP
"""

TECHNICAL_DESIGN = """\
# Technical Design — Library MVP

## 1. Problem Confirmation
Replace paper-based library tracking with a small web app. Public search +
staff CRUD + borrowing tracker. On-prem, low budget.

## 2. Approach
**Recommended:** monolithic web app (Flask + SQLite + simple HTML/HTMX UI).
- Pros: minimal infra, easy to deploy, cheap to maintain
- Cons: limited scale (fine for 800 members)

## 3. Architecture
- Single Flask app on a Linux VM
- SQLite database (file-based)
- HTMX for interactive UI without heavy JS
- Nginx reverse proxy + Let's Encrypt
- Daily SQLite backup via cron

## 4. Module Decomposition

| Module | Sub-modules | FR Coverage | Complexity |
|--------|-------------|-------------|------------|
| Auth | login, role | (cross-cutting) | Low |
| Catalog | book CRUD, ISBN lookup | FR1, FR3 | Low |
| Circulation | borrow, return, overdue | FR2, FR4 | Medium |
| Public UI | search, availability | FR3 | Low |
| Admin Reports | overdue report, exports | FR4 | Low |

## 5. Tech Stack
- Backend: Python 3.12 + Flask 3.0
- DB: SQLite (single-file, with WAL)
- Frontend: HTMX + Tailwind CSS
- Auth: Flask-Login + bcrypt
- Deployment: systemd + nginx

## 6. Integration Design
None — fully self-contained. Optional ISBN lookup via OpenLibrary public API.

## 7. Scope

### In Scope
- Catalog CRUD (FR1)
- Borrow/Return tracking (FR2)
- Public search page (FR3)
- Overdue report (FR4)
- Staff login + 2 roles (admin, librarian)

### Out of Scope
- Mobile app
- Reservations / holds
- Fine collection / payment
- Patron self-service portal

## 8. Estimation Assumptions

- 1 BE developer + 0.3 FE allocation (HTMX is lightweight)
- ISBN dataset is OpenLibrary (free)
- Existing VM available (no infra cost)

## 9. Risks
| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| HTMX learning curve for team | Medium | Low | 2-day spike before sprint 1 |
| OpenLibrary API rate limits | Low | Low | Local cache table |
| Backup not tested | Medium | High | Test restore weekly in dev |
"""


def main() -> int:
    ws = ROOT / "sample_workspace" / PROJECT_SLUG
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    if ws.exists():
        import shutil
        shutil.rmtree(ws)
    ws.mkdir(parents=True, exist_ok=True)
    set_workspace(ws)

    print(f"Workspace: {ws}\n")

    # Pre-populate raw_features.md and technical_design.md (skip chatty phases)
    (ws / "raw_features.md").write_text(RAW_FEATURES, encoding="utf-8")
    (ws / "technical_design.md").write_text(TECHNICAL_DESIGN, encoding="utf-8")
    print(f"  ✓ raw_features.md     ({len(RAW_FEATURES)} chars)")
    print(f"  ✓ technical_design.md ({len(TECHNICAL_DESIGN)} chars)")

    # ── Run WBS workflow ─────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP A: run_wbs_workflow  (real LLM call, ~30-90s)")
    print("=" * 70)
    wbs_brief = (
        "Project: Library Book Management System (MVP).\n"
        "project_code: BNK-LIB-001\n"
        "project_name: Library MVP\n"
        "language: en\n"
        "Decompose into a complete WBS following BnK structure (Phases I-III). "
        "Source: raw_features.md + technical_design.md (already in workspace). "
        "Map L4 tasks to FR1-FR4. Total budget target: ~20-25 md."
    )
    t0 = time.monotonic()
    try:
        wbs_result = run_wbs_workflow.invoke({"brief": wbs_brief})
    except Exception as e:
        print(f"  ✗ WBS workflow failed: {e}")
        return 1
    dt = time.monotonic() - t0
    print(f"  ✓ WBS workflow done in {dt:.1f}s")
    print(f"  result: {wbs_result[:300]}")

    # ── Run BRD workflow ─────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP B: run_brd_workflow  (real LLM call, ~60-120s)")
    print("=" * 70)
    brd_brief = (
        "Solution: small library MVP (Flask + SQLite + HTMX, on-prem). "
        "WBS already created with FR ids: FR1 (Catalog CRUD), FR2 (Borrow/Return), "
        "FR3 (Public Search), FR4 (Overdue Report). "
        "Use these EXACT FR ids in the BRD §5.2 — they match WBS source_feature_id. "
        "language: en. Read raw_features.md + technical_design.md from workspace "
        "for stakeholder, NFR, constraint details."
    )
    t0 = time.monotonic()
    try:
        brd_result = run_brd_workflow.invoke({"brief": brd_brief})
    except Exception as e:
        print(f"  ✗ BRD workflow failed: {e}")
        return 1
    dt = time.monotonic() - t0
    print(f"  ✓ BRD workflow done in {dt:.1f}s")
    print(f"  result: {brd_result[:300]}")

    # ── Copy outputs to sample_outputs/ ──────────────────────────────────────
    print("\n" + "=" * 70)
    print("Outputs")
    print("=" * 70)
    out_dir = OUT_ROOT / PROJECT_SLUG
    out_dir.mkdir(parents=True, exist_ok=True)
    import shutil
    for src in (ws / "WBS.xlsx", ws / "BRD.docx"):
        if src.exists():
            dst = out_dir / src.name
            shutil.copy2(src, dst)
            print(f"  ✓ {dst.relative_to(ROOT)}  ({dst.stat().st_size // 1024} KB)")
        else:
            print(f"  ✗ missing: {src.name}")
    # Also copy state for inspection
    for sd in ("brd", "wbs"):
        src = ws / sd
        if src.exists():
            shutil.copytree(src, out_dir / sd, dirs_exist_ok=True)
    project_json = ws / "project.json"
    if project_json.exists():
        shutil.copy2(project_json, out_dir / "project.json")
    print(f"\n  Inspect everything at: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
