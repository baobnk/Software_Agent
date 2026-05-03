"""WBSStore — section-sharded WBS persistence with a page index.

Layout under `<workspace>/wbs/`:

    _index.json                ← page index (modified, totals, task list)
    00_metadata.json           ← project_code, project_name, version, MasterData
    10_structure.json          ← L1/L2/L3 nodes (flat list)
    20_tasks/<code>.json       ← one file per L4 leaf task (volatile)

Why split this way (vs. all in one file or one file per node):
  • L1/L2/L3 are **structural** — set up during decomposition, rarely edited.
    Keeping them in one file (~2 KB) is fine.
  • L4 tasks are **volatile** — re-estimated many times. Per-task sharding
    means each `upsert_task` reads/writes ~500 B instead of the whole WBS.

Index is updated *eagerly* on every write (atomic temp + rename).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

from .. import project_meta
from .schema import (
    MasterData,
    WBSDocument,
    WBSMetadataSection,
    WBSStructureSection,
    WBSTask,
)

log = logging.getLogger(__name__)

INDEX_FILE = "_index.json"
METADATA_FILE = "00_metadata.json"
STRUCTURE_FILE = "10_structure.json"
TASKS_DIR = "20_tasks"
SCHEMA_VERSION = "v2.0"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _atomic_write_json(path: Path, data: dict | list) -> None:
    """Atomic write: serialize → temp → rename. Survives crashes mid-write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _read_json(path: Path) -> dict | list | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            from json_repair import repair_json
            repaired = repair_json(text, return_objects=True, ensure_ascii=False)
            if isinstance(repaired, (dict, list)):
                log.warning("_read_json: repaired corrupt JSON in %s", path.name)
                return repaired
        except Exception:
            pass
        corrupt = path.with_suffix(path.suffix + ".corrupt")
        try:
            path.rename(corrupt)
        except OSError:
            pass
        log.warning("_read_json: unrecoverable JSON in %s; renamed to %s", path.name, corrupt.name)
        return None


# ── Code-key helpers (sort tasks naturally: I, I.A, I.A.1, BE-1, BE-10, ...) ─

def _natural_key(code: str) -> tuple:
    """Sort key that interleaves alpha and numeric runs for natural ordering."""
    parts: list = []
    buf = ""
    for ch in code:
        if ch.isdigit():
            buf += ch
        else:
            if buf:
                parts.append((1, int(buf)))
                buf = ""
            parts.append((0, ch))
    if buf:
        parts.append((1, int(buf)))
    return tuple(parts)


# ── WBSStore ─────────────────────────────────────────────────────────────────

class WBSStore:
    """Section-sharded WBS persistence rooted at `<workspace>/wbs/`."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    # ── Path properties ──────────────────────────────────────────────────────

    @property
    def index_path(self) -> Path:
        return self.root / INDEX_FILE

    @property
    def metadata_path(self) -> Path:
        return self.root / METADATA_FILE

    @property
    def structure_path(self) -> Path:
        return self.root / STRUCTURE_FILE

    @property
    def tasks_dir(self) -> Path:
        return self.root / TASKS_DIR

    def is_initialized(self) -> bool:
        return self.index_path.exists()

    # ── Init ─────────────────────────────────────────────────────────────────

    def init(
        self,
        project_code: str,
        project_name: str,
        language: str = "en",
        version: str = "0.1.0",
    ) -> None:
        """Create the section directory + empty section files + index.

        WBS-first pipeline: this also writes the canonical
        `<workspace>/project.json` so BRDStore can later inherit metadata
        without duplication. If `project.json` already exists, this updates
        it with the supplied values.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        self.tasks_dir.mkdir(exist_ok=True)

        # 1) Write canonical shared metadata (workspace/project.json)
        ws_root = self.root.parent  # workspace/{session}/wbs/.. → workspace/{session}/
        project_meta.init(
            ws_root,
            project_code=project_code,
            project_name=project_name,
            language=language,  # type: ignore[arg-type]
            version=version,
            overwrite=True,
        )

        # 2) Write WBS section files
        meta = WBSMetadataSection(
            project_code=project_code,
            project_name=project_name,
            version=version,
        )
        _atomic_write_json(self.metadata_path, meta.model_dump())
        _atomic_write_json(self.structure_path, WBSStructureSection().model_dump())

        # Wipe any leftover task files
        for p in self.tasks_dir.glob("*.json"):
            p.unlink()

        self._write_index_full()

    # ── Metadata + Master ────────────────────────────────────────────────────

    def read_metadata(self) -> WBSMetadataSection:
        data = _read_json(self.metadata_path)
        return WBSMetadataSection.model_validate(data) if data else WBSMetadataSection()

    def write_metadata(self, meta: WBSMetadataSection) -> None:
        _atomic_write_json(self.metadata_path, meta.model_dump())
        self._touch_meta()

    def update_master(self, master: MasterData) -> None:
        """Patch only the master block of metadata."""
        meta = self.read_metadata()
        meta.master = master
        self.write_metadata(meta)

    # ── Structure (L1/L2/L3) ─────────────────────────────────────────────────

    def read_structure(self) -> WBSStructureSection:
        data = _read_json(self.structure_path)
        return WBSStructureSection.model_validate(data) if data else WBSStructureSection()

    def write_structure(self, structure: WBSStructureSection) -> None:
        _atomic_write_json(self.structure_path, structure.model_dump())
        self._touch_structure(len(structure.nodes))

    def upsert_node(self, node: WBSTask) -> None:
        """Add or update one structural node (L1/L2/L3) in the structure file."""
        if node.hierarchy_level == 4:
            raise ValueError(
                f"Use write_task for L4 leaves (got {node.code} L{node.hierarchy_level})"
            )
        struct = self.read_structure()
        for i, existing in enumerate(struct.nodes):
            if existing.code == node.code:
                struct.nodes[i] = node
                break
        else:
            struct.nodes.append(node)
        struct.nodes.sort(key=lambda n: _natural_key(n.code))
        self.write_structure(struct)

    def remove_node(self, code: str) -> bool:
        struct = self.read_structure()
        before = len(struct.nodes)
        struct.nodes = [n for n in struct.nodes if n.code != code]
        if len(struct.nodes) == before:
            return False
        self.write_structure(struct)
        return True

    # ── L4 tasks (per-file sharding) ─────────────────────────────────────────

    def _task_path(self, code: str) -> Path:
        # Sanitize: code may contain '/' or other unsafe chars in general.
        # In our domain, codes are alphanumeric + dot + dash, so direct use is OK.
        return self.tasks_dir / f"{code}.json"

    def read_task(self, code: str) -> WBSTask | None:
        data = _read_json(self._task_path(code))
        return WBSTask.model_validate(data) if data else None

    def write_task(self, task: WBSTask) -> WBSTask:
        """Write one L4 task. Preserves source_section_id on update."""
        if task.hierarchy_level != 4:
            raise ValueError(
                f"write_task expects L4 leaf (got {task.code} L{task.hierarchy_level}). "
                f"Use upsert_node for L1/L2/L3."
            )
        existing = self.read_task(task.code)
        if existing is not None and existing.source_section_id and not task.source_section_id:
            task.source_section_id = existing.source_section_id
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(self._task_path(task.code), task.model_dump())
        self._touch_task(task)
        return task

    def remove_task(self, code: str) -> bool:
        path = self._task_path(code)
        if not path.exists():
            return False
        path.unlink()
        self._remove_task_from_index(code)
        return True

    def list_task_codes(self) -> list[str]:
        idx = self.read_index()
        return [t["code"] for t in idx.get("tasks", [])]

    def list_tasks(self) -> list[WBSTask]:
        out: list[WBSTask] = []
        for code in self.list_task_codes():
            t = self.read_task(code)
            if t is not None:
                out.append(t)
        return out

    # ── Assembly (render / validation) ───────────────────────────────────────

    def assemble(self) -> WBSDocument:
        """Read metadata + structure + all L4 tasks → assembled WBSDocument."""
        if not self.is_initialized():
            raise FileNotFoundError(
                f"WBS not initialized at {self.root}. Call WBSStore.init(...) first."
            )

        meta = self.read_metadata()
        struct = self.read_structure()
        leaves = self.list_tasks()

        # Combine non-leaves and leaves; sort naturally so renderer sees correct order.
        all_tasks = list(struct.nodes) + leaves
        all_tasks.sort(key=lambda t: _natural_key(t.code))

        return WBSDocument(
            project_code=meta.project_code,
            project_name=meta.project_name,
            tasks=all_tasks,
            master=meta.master,
        )

    # ── Index ────────────────────────────────────────────────────────────────

    def read_index(self) -> dict:
        data = _read_json(self.index_path)
        return data if isinstance(data, dict) else {}

    def get_summary(self) -> str:
        """Human-readable status — reads ONLY the index (token-cheap)."""
        if not self.is_initialized():
            return "WBS not initialized."
        idx = self.read_index()
        lines = [
            f"Project:  {idx.get('project_name', '?')} ({idx.get('project_code', '?')})",
            f"Modified: {idx.get('modified_at', '?')}",
            "",
            f"Structure (L1/L2/L3): {idx.get('structure_count', 0)} nodes",
            f"Tasks (L4):           {idx.get('task_count', 0)}",
            f"Effort — BE: {idx.get('total_md_be', 0):.1f} md   FE: {idx.get('total_md_fe', 0):.1f} md",
        ]
        tasks = idx.get("tasks", [])
        if tasks:
            lines.append("")
            lines.append("L4 tasks:")
            for t in tasks[:20]:
                lines.append(
                    f"  {t['code']:>10}  BE={t.get('md_be', 0):.1f} FE={t.get('md_fe', 0):.1f}  {t.get('feature', '')[:40]}"
                )
            if len(tasks) > 20:
                lines.append(f"  … ({len(tasks) - 20} more)")
        return "\n".join(lines)

    # ── Internal index maintenance ───────────────────────────────────────────

    def _write_index_full(self) -> None:
        meta = self.read_metadata()
        idx = {
            "schema_version": SCHEMA_VERSION,
            "project_code": meta.project_code,
            "project_name": meta.project_name,
            "modified_at": _now_iso(),
            "metadata_modified": _now_iso(),
            "structure_modified": _now_iso(),
            "structure_count": 0,
            "task_count": 0,
            "total_md_be": 0.0,
            "total_md_fe": 0.0,
            "tasks": [],
        }
        _atomic_write_json(self.index_path, idx)

    def _touch_meta(self) -> None:
        idx = self.read_index()
        if not idx:
            return
        meta = self.read_metadata()
        idx["project_code"] = meta.project_code
        idx["project_name"] = meta.project_name
        idx["metadata_modified"] = _now_iso()
        idx["modified_at"] = _now_iso()
        _atomic_write_json(self.index_path, idx)

    def _touch_structure(self, count: int) -> None:
        idx = self.read_index()
        if not idx:
            return
        idx["structure_count"] = count
        idx["structure_modified"] = _now_iso()
        idx["modified_at"] = _now_iso()
        _atomic_write_json(self.index_path, idx)

    def _touch_task(self, task: WBSTask) -> None:
        idx = self.read_index()
        if not idx:
            return
        tasks = idx.setdefault("tasks", [])
        entry = {
            "code": task.code,
            "feature": task.feature,
            "md_be": task.md_be,
            "md_fe": task.md_fe,
            "source_feature_id": task.source_feature_id,
            "modified": _now_iso(),
        }
        for i, e in enumerate(tasks):
            if e["code"] == task.code:
                tasks[i] = entry
                break
        else:
            tasks.append(entry)
        tasks.sort(key=lambda e: _natural_key(e["code"]))
        idx["task_count"] = len(tasks)
        idx["total_md_be"] = sum(e.get("md_be", 0) for e in tasks)
        idx["total_md_fe"] = sum(e.get("md_fe", 0) for e in tasks)
        idx["modified_at"] = _now_iso()
        _atomic_write_json(self.index_path, idx)

    def _remove_task_from_index(self, code: str) -> None:
        idx = self.read_index()
        if not idx:
            return
        tasks = [e for e in idx.get("tasks", []) if e["code"] != code]
        idx["tasks"] = tasks
        idx["task_count"] = len(tasks)
        idx["total_md_be"] = sum(e.get("md_be", 0) for e in tasks)
        idx["total_md_fe"] = sum(e.get("md_fe", 0) for e in tasks)
        idx["modified_at"] = _now_iso()
        _atomic_write_json(self.index_path, idx)
