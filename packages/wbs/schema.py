"""WBS section sub-models.

Re-exports `WBSDocument`, `WBSTask`, and `MasterData` from the legacy
`wbs_agent_kit` (kept as the renderer contract — do NOT clone). Adds section
sub-models that mirror the on-disk sharding for token-efficient editing.

Section layout:
  metadata   → 00_metadata.json (project + MasterData)
  structure  → 10_structure.json (L1/L2/L3 nodes, flat list)
  tasks/     → 20_tasks/<code>.json (one file per L4 leaf task)
"""
from __future__ import annotations

import sys
from pathlib import Path

from pydantic import BaseModel, Field

# ── Renderer contract: import the existing types verbatim ────────────────────
try:
    from wbs_agent_kit.src.types import MasterData, WBSDocument, WBSTask
except ImportError:
    sys.path.insert(0, str(Path(__file__).parents[3] / "bnk-agent" / "packages"))
    from wbs_agent_kit.src.types import MasterData, WBSDocument, WBSTask  # type: ignore


# ── Section sub-models ───────────────────────────────────────────────────────

class WBSMetadataSection(BaseModel):
    """Project-level WBS metadata + global master config. → 00_metadata.json"""
    project_code: str = ""
    project_name: str = ""
    version: str = "0.1.0"
    master: MasterData = Field(default_factory=MasterData)


class WBSStructureSection(BaseModel):
    """All non-leaf nodes (L1, L2, L3) flat. → 10_structure.json

    These are rarely edited after the decomposition phase. Kept in one file
    because each node is tiny (no effort fields used).
    """
    nodes: list[WBSTask] = Field(default_factory=list)


__all__ = [
    "MasterData",
    "WBSDocument",
    "WBSTask",
    "WBSMetadataSection",
    "WBSStructureSection",
]
