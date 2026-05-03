"""Shared project metadata — single source of truth across BRDStore and WBSStore.

Lives at `<workspace>/project.json`. Contains the small set of fields that
MUST stay consistent between BRD and WBS: project_code, project_name,
language, version. Initialized by whichever store runs first (per the
WBS-first pipeline, that is `WBSStore.init` → `BRDStore.init` reads).

This file is small (~200 B) and read by every store at init/assemble time,
so it is cheap to share without imposing a token cost on edit operations.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

Language = Literal["en", "vi", "ja", "zh"]

PROJECT_FILE = "project.json"


class ProjectMeta(BaseModel):
    """Canonical project metadata. Governs both BRD and WBS."""
    project_code: str
    project_name: str
    language: Language = "en"
    version: str = "0.1.0"
    author: str = "BnK Solution"
    created_at: str = Field(default_factory=lambda: datetime.now().date().isoformat())


def project_path(workspace_root: str | Path) -> Path:
    return Path(workspace_root) / PROJECT_FILE


def exists(workspace_root: str | Path) -> bool:
    return project_path(workspace_root).exists()


def read(workspace_root: str | Path) -> ProjectMeta | None:
    """Return the canonical ProjectMeta, or None if not yet initialized."""
    p = project_path(workspace_root)
    if not p.exists():
        return None
    return ProjectMeta.model_validate_json(p.read_text(encoding="utf-8"))


def require(workspace_root: str | Path) -> ProjectMeta:
    """Read project metadata or raise — use when downstream MUST have it."""
    meta = read(workspace_root)
    if meta is None:
        raise FileNotFoundError(
            f"Project metadata not initialized at {project_path(workspace_root)}. "
            "Run WBSStore.init or call init_project() first."
        )
    return meta


def write(workspace_root: str | Path, meta: ProjectMeta) -> Path:
    """Atomic write the project metadata file. Returns its path."""
    p = project_path(workspace_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=f".{p.name}.", suffix=".tmp", dir=str(p.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(meta.model_dump_json(indent=2))
        os.replace(tmp_name, p)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return p


def init(
    workspace_root: str | Path,
    *,
    project_code: str,
    project_name: str,
    language: Language = "en",
    version: str = "0.1.0",
    author: str = "BnK Solution",
    overwrite: bool = False,
) -> ProjectMeta:
    """Create the project.json file. If it exists and overwrite=False, returns
    the existing metadata unchanged.
    """
    existing = read(workspace_root)
    if existing is not None and not overwrite:
        return existing
    meta = ProjectMeta(
        project_code=project_code,
        project_name=project_name,
        language=language,
        version=version,
        author=author,
    )
    write(workspace_root, meta)
    return meta


def update(
    workspace_root: str | Path,
    *,
    project_code: str | None = None,
    project_name: str | None = None,
    language: Language | None = None,
    version: str | None = None,
    author: str | None = None,
) -> ProjectMeta:
    """Patch any subset of fields in the existing project.json."""
    meta = require(workspace_root)
    if project_code is not None: meta.project_code = project_code
    if project_name is not None: meta.project_name = project_name
    if language     is not None: meta.language     = language
    if version      is not None: meta.version      = version
    if author       is not None: meta.author       = author
    write(workspace_root, meta)
    return meta
