"""LangChain @tool wrapper for excel_audit_core.

One tool: `audit_workbook(xlsx_path)`. Read-only.
"""
from __future__ import annotations

from langchain_core.tools import tool
from loguru import logger as _log

from .excel_audit_core import audit_workbook as _audit, format_audit

_audit_log = _log.bind(ctx="excel_audit")


@tool
def audit_workbook(xlsx_path: str) -> str:
    """Read a BnK WBS .xlsx file and report what's wrong.

    Returns a human-readable audit covering:
      - WBS sheet: missing L1/L2 hierarchy rows, junk rows, TOTAL row presence
      - Effort sheet: module IDs that don't match any WBS row
      - Delivery Plan: master planning / milestones still TBD, missing roles
      - Master Data: missing role rates / percentages
      - Workbook-level: missing named ranges

    Use this BEFORE calling patch_workbook so you know exactly what to fix.
    """
    _audit_log.info(f"audit_workbook | path={xlsx_path}")
    report = _audit(xlsx_path)
    return format_audit(report)
