"""BRDStore — section-sharded persistence with a page index.

Layout under `<workspace>/brd/`:

    _index.json                 ← page index (section → file, last_modified)
    00_metadata.json
    01_introduction.json
    02_context.json
    03_scope.json
    04_stakeholders.json
    05_2_fr/<FR_ID>.json        ← one file per Functional Requirement
    05_3_nfr.json
    05_4_data.json
    05_5_integrations.json
    06_acceptance.json
    07_glossary.json
    08_appendix.json

Why sectioned? Most edits touch ONE section. Loading a 20 KB monolithic
brd_state.json for every patch is wasteful. With this layout, an `upsert_fr`
reads/writes ~1 KB instead of ~20 KB. The full document is only assembled
at render/validation time.

Index is updated *eagerly* on every write (atomic temp+rename).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Type

from pydantic import BaseModel

from .. import project_meta
from .schema import (
    AcceptanceSection,
    AppendixSection,
    BRDDocument,
    ContextSection,
    DataReqSection,
    FunctionalRequirement,
    GlossarySection,
    IntegrationsSection,
    IntroductionSection,
    Language,
    MetadataSection,
    NFRSection,
    ScopeSection,
    StakeholdersSection,
    VersionEntry,
)

log = logging.getLogger(__name__)

# ── Section registry — maps section_id → (filename, Pydantic class) ──────────
# IDs are stable strings used in tools' arguments and the index file.
SECTION_REGISTRY: dict[str, tuple[str, Type[BaseModel]]] = {
    "metadata":     ("00_metadata.json",       MetadataSection),
    "introduction": ("01_introduction.json",   IntroductionSection),
    "context":      ("02_context.json",        ContextSection),
    "scope":        ("03_scope.json",          ScopeSection),
    "stakeholders": ("04_stakeholders.json",   StakeholdersSection),
    "nfr":          ("05_3_nfr.json",          NFRSection),
    "data_req":     ("05_4_data.json",         DataReqSection),
    "integrations": ("05_5_integrations.json", IntegrationsSection),
    "acceptance":   ("06_acceptance.json",     AcceptanceSection),
    "glossary":     ("07_glossary.json",       GlossarySection),
    "appendix":     ("08_appendix.json",       AppendixSection),
}

INDEX_FILE = "_index.json"
FR_DIR = "05_2_fr"
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
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _read_json(path: Path) -> dict | list | None:
    # Use try/except instead of exists()-then-read to avoid TOCTOU race
    # conditions on Windows-mounted filesystems (WSL2 DrvFs / /mnt/...).
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


# ── BRDStore ─────────────────────────────────────────────────────────────────

class BRDStore:
    """Section-sharded BRD persistence rooted at `<workspace>/brd/`."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    # ── State checks ─────────────────────────────────────────────────────────

    @property
    def index_path(self) -> Path:
        return self.root / INDEX_FILE

    @property
    def fr_dir(self) -> Path:
        return self.root / FR_DIR

    def is_initialized(self) -> bool:
        return self.index_path.exists()

    # ── Init ─────────────────────────────────────────────────────────────────

    def init(
        self,
        project_name: str | None = None,
        project_code: str | None = None,
        language: Language | None = None,
        author: str | None = None,
        version: str | None = None,
    ) -> None:
        """Create the section directory + empty section files + index.

        WBS-first pipeline: BRDStore inherits project_code, project_name,
        language, version, author from the canonical
        `<workspace>/project.json` (written by WBSStore.init). Any explicit
        argument here overrides the inherited value.

        Raises FileNotFoundError if the canonical metadata is missing AND
        none of the required args (project_name, project_code) are supplied.

        Overwrites any existing BRD draft.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        self.fr_dir.mkdir(exist_ok=True)

        ws_root = self.root.parent  # workspace/{session}/brd/.. → workspace/{session}/
        canonical = project_meta.read(ws_root)

        # Resolve fields: explicit arg > canonical > error/default
        if canonical is None:
            if project_name is None or project_code is None:
                raise FileNotFoundError(
                    f"No project metadata at {project_meta.project_path(ws_root)} "
                    "and no project_name/project_code provided. Run WBSStore.init "
                    "first (WBS-first pipeline) or pass them explicitly."
                )
            # Bootstrap canonical metadata from the BRD-side init (BRD-first fallback)
            canonical = project_meta.init(
                ws_root,
                project_code=project_code,
                project_name=project_name,
                language=language or "en",  # type: ignore[arg-type]
                version=version or "0.1.0",
                author=author or "BnK Solution",
                overwrite=True,
            )
        else:
            # Pivot any overrides into the canonical file so both stores stay aligned
            updates = {}
            if project_name is not None: updates["project_name"] = project_name
            if project_code is not None: updates["project_code"] = project_code
            if language is not None:     updates["language"] = language
            if version is not None:      updates["version"] = version
            if author is not None:       updates["author"] = author
            if updates:
                canonical = project_meta.update(ws_root, **updates)

        meta = MetadataSection(
            project_name=canonical.project_name,
            project_code=canonical.project_code,
            language=canonical.language,
            author=canonical.author,
            version=canonical.version,
            created_at=canonical.created_at,
            version_history=[
                VersionEntry(
                    version=canonical.version,
                    date=canonical.created_at,
                    description="Initial draft",
                    author=canonical.author,
                ),
            ],
        )
        for section_id, (fname, cls) in SECTION_REGISTRY.items():
            payload = meta if section_id == "metadata" else cls()
            _atomic_write_json(self.root / fname, payload.model_dump())

        # Wipe any leftover FR files
        if self.fr_dir.exists():
            for p in self.fr_dir.glob("*.json"):
                p.unlink()

        self._write_index_full(
            language=canonical.language,
            project_name=canonical.project_name,
            project_code=canonical.project_code,
        )

    # ── Section read / write ─────────────────────────────────────────────────

    def read_section(self, section_id: str) -> BaseModel:
        """Read one section as its Pydantic model. Returns empty model if missing."""
        if section_id not in SECTION_REGISTRY:
            raise KeyError(f"Unknown section_id: {section_id!r}. Allowed: {list(SECTION_REGISTRY)}")
        filename, cls = SECTION_REGISTRY[section_id]
        data = _read_json(self.root / filename)
        return cls.model_validate(data) if data else cls()

    def write_section(self, section_id: str, model: BaseModel) -> None:
        """Persist one section + update its index entry."""
        if section_id not in SECTION_REGISTRY:
            raise KeyError(f"Unknown section_id: {section_id!r}")
        filename, cls = SECTION_REGISTRY[section_id]
        if not isinstance(model, cls):
            raise TypeError(
                f"Section {section_id!r} expects {cls.__name__}, got {type(model).__name__}"
            )
        _atomic_write_json(self.root / filename, model.model_dump())
        self._touch_section(section_id, filled=self._is_section_filled(section_id, model))

    # ── FR read / write / list ───────────────────────────────────────────────

    def _fr_path(self, fr_id: str) -> Path:
        return self.fr_dir / f"{fr_id}.json"

    def read_fr(self, fr_id: str) -> FunctionalRequirement | None:
        data = _read_json(self._fr_path(fr_id))
        return FunctionalRequirement.model_validate(data) if data else None

    def write_fr(self, fr: FunctionalRequirement) -> FunctionalRequirement:
        """Write one FR. If updating, preserves the original section_id (UUID)."""
        existing = self.read_fr(fr.fr_id)
        if existing is not None:
            fr.section_id = existing.section_id  # preserve cross-references
        self.fr_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(self._fr_path(fr.fr_id), fr.model_dump())
        self._touch_fr(fr)
        return fr

    def remove_fr(self, fr_id: str) -> bool:
        path = self._fr_path(fr_id)
        if not path.exists():
            return False
        path.unlink()
        self._remove_fr_from_index(fr_id)
        return True

    def list_fr_ids(self) -> list[str]:
        """Return FR ids from the index, auto-healing if files exceed index entries.

        On WSL2 / network-mounted filesystems, concurrent atomic writes can
        leave the index with fewer entries than actual files on disk. This
        method detects the gap and calls _sync_fr_index_from_files() to heal.
        """
        idx = self.read_index()
        index_ids = {entry["fr_id"] for entry in idx.get("frs", [])}

        # Detect staleness: scan actual files and compare with index
        if self.fr_dir.exists():
            file_ids = {p.stem for p in self.fr_dir.glob("*.json")}
            if file_ids - index_ids:
                # Files on disk not in index → rebuild
                log.warning(
                    "list_fr_ids: index has %d entries but %d FR files on disk — rebuilding index",
                    len(index_ids), len(file_ids),
                )
                self._sync_fr_index_from_files()
                idx = self.read_index()

        return [entry["fr_id"] for entry in idx.get("frs", [])]

    def _sync_fr_index_from_files(self) -> None:
        """Rebuild the 'frs' list in _index.json from actual FR files on disk.

        Used to recover from index staleness caused by filesystem caching on
        WSL2 / DrvFs / network mounts where os.replace() may not flush caches
        fast enough for a tight sequential read-modify-write cycle.
        """
        if not self.fr_dir.exists():
            return
        idx = self.read_index()
        if not idx:
            return

        existing_by_id = {e["fr_id"]: e for e in idx.get("frs", [])}
        rebuilt: list[dict] = []

        for p in sorted(self.fr_dir.glob("*.json")):
            fr_id = p.stem
            data = _read_json(p)
            if data is None:
                continue
            try:
                fr = FunctionalRequirement.model_validate(data)
            except Exception:
                continue

            if fr_id in existing_by_id:
                rebuilt.append(existing_by_id[fr_id])
            else:
                rebuilt.append({
                    "fr_id": fr_id,
                    "section_id": fr.section_id,
                    "path": f"{FR_DIR}/{fr_id}.json",
                    "modified": _now_iso(),
                })

        rebuilt.sort(key=lambda e: (len(e["fr_id"]), e["fr_id"]))
        idx["frs"] = rebuilt
        idx["modified_at"] = _now_iso()
        _atomic_write_json(self.index_path, idx)

    def list_frs(self) -> list[FunctionalRequirement]:
        out: list[FunctionalRequirement] = []
        for fr_id in self.list_fr_ids():
            fr = self.read_fr(fr_id)
            if fr is not None:
                out.append(fr)
        return out

    # ── Assembly (only at render / validation time) ──────────────────────────

    def assemble(self) -> BRDDocument:
        """Read every section + every FR file → return a complete BRDDocument."""
        if not self.is_initialized():
            raise FileNotFoundError(
                f"BRD not initialized at {self.root}. Call BRDStore.init(...) first."
            )

        meta:  MetadataSection      = self.read_section("metadata")     # type: ignore[assignment]
        intro: IntroductionSection  = self.read_section("introduction") # type: ignore[assignment]
        ctx:   ContextSection       = self.read_section("context")      # type: ignore[assignment]
        scp:   ScopeSection         = self.read_section("scope")        # type: ignore[assignment]
        sh:    StakeholdersSection  = self.read_section("stakeholders") # type: ignore[assignment]
        nfr:   NFRSection           = self.read_section("nfr")          # type: ignore[assignment]
        dr:    DataReqSection       = self.read_section("data_req")     # type: ignore[assignment]
        intg:  IntegrationsSection  = self.read_section("integrations") # type: ignore[assignment]
        acc:   AcceptanceSection    = self.read_section("acceptance")   # type: ignore[assignment]
        gl:    GlossarySection      = self.read_section("glossary")     # type: ignore[assignment]
        apx:   AppendixSection      = self.read_section("appendix")     # type: ignore[assignment]

        return BRDDocument(
            **meta.model_dump(),
            **intro.model_dump(),
            **ctx.model_dump(),
            **scp.model_dump(),
            **sh.model_dump(),
            functional_requirements=self.list_frs(),
            **nfr.model_dump(),
            **dr.model_dump(),
            **intg.model_dump(),
            **acc.model_dump(),
            **gl.model_dump(),
            **apx.model_dump(),
        )

    # ── Index ────────────────────────────────────────────────────────────────

    def read_index(self) -> dict:
        data = _read_json(self.index_path)
        return data if isinstance(data, dict) else {}

    def get_summary(self) -> str:
        """Human-readable status — reads ONLY the index (token-cheap)."""
        if not self.is_initialized():
            return "BRD not initialized."
        idx = self.read_index()
        sections = idx.get("sections", {})
        frs = idx.get("frs", [])
        lines = [
            f"Project:  {idx.get('project_name', '?')} ({idx.get('project_code', '?')})",
            f"Language: {idx.get('language', '?')}    Modified: {idx.get('modified_at', '?')}",
            "",
            "Sections:",
        ]
        for sid in SECTION_REGISTRY:
            info = sections.get(sid, {})
            mark = "✓" if info.get("filled") else "—"
            lines.append(f"  {mark} {sid}")
        lines.append("")
        lines.append(f"FRs ({len(frs)}):")
        if not frs:
            lines.append("  (none)")
        else:
            for f in frs:
                lines.append(f"  - {f['fr_id']}  modified={f.get('modified', '?')}")
        return "\n".join(lines)

    # ── Internal index maintenance ───────────────────────────────────────────

    def _is_section_filled(self, section_id: str, model: BaseModel) -> bool:
        """True if section has any non-default content (used for index display)."""
        data = model.model_dump()
        if section_id == "metadata":
            return bool(data.get("project_name"))  # always true after init
        # Treat empty strings and empty lists as 'not filled'
        for k, v in data.items():
            if isinstance(v, str) and v.strip():
                return True
            if isinstance(v, list) and len(v) > 0:
                return True
        return False

    def _write_index_full(
        self, *, language: Language, project_name: str, project_code: str,
    ) -> None:
        idx = {
            "schema_version": SCHEMA_VERSION,
            "project_name": project_name,
            "project_code": project_code,
            "language": language,
            "modified_at": _now_iso(),
            "sections": {
                sid: {"path": fname, "filled": (sid == "metadata"), "modified": _now_iso()}
                for sid, (fname, _) in SECTION_REGISTRY.items()
            },
            "frs": [],
        }
        _atomic_write_json(self.index_path, idx)

    def _touch_section(self, section_id: str, *, filled: bool) -> None:
        idx = self.read_index()
        if not idx:
            return
        sections = idx.setdefault("sections", {})
        entry = sections.setdefault(section_id, {"path": SECTION_REGISTRY[section_id][0]})
        entry["filled"] = filled
        entry["modified"] = _now_iso()
        idx["modified_at"] = _now_iso()
        _atomic_write_json(self.index_path, idx)

    def _touch_fr(self, fr: FunctionalRequirement) -> None:
        idx = self.read_index()
        if not idx:
            return
        frs = idx.setdefault("frs", [])
        for entry in frs:
            if entry["fr_id"] == fr.fr_id:
                entry["section_id"] = fr.section_id
                entry["modified"] = _now_iso()
                break
        else:
            frs.append({
                "fr_id": fr.fr_id,
                "section_id": fr.section_id,
                "path": f"{FR_DIR}/{fr.fr_id}.json",
                "modified": _now_iso(),
            })
        # Keep FR list sorted by fr_id (FR1, FR2, FR10, ...) — natural numeric order
        frs.sort(key=lambda e: (len(e["fr_id"]), e["fr_id"]))
        idx["modified_at"] = _now_iso()
        _atomic_write_json(self.index_path, idx)

    def _remove_fr_from_index(self, fr_id: str) -> None:
        idx = self.read_index()
        if not idx:
            return
        idx["frs"] = [e for e in idx.get("frs", []) if e["fr_id"] != fr_id]
        idx["modified_at"] = _now_iso()
        _atomic_write_json(self.index_path, idx)
