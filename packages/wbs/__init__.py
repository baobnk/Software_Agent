"""BnK WBS package — section-sharded store for the WBS document.

Wraps the legacy `wbs_agent_kit` schema (kept as the renderer contract) with
a section-sharded persistence layer matching the BRD pattern (Rule §18).

Module layout:
  schema.py    Section sub-models + re-exports of WBSDocument/WBSTask/MasterData
  store.py     WBSStore class — handles disk layout, index, assemble
"""
from .schema import (
    MasterData,
    WBSDocument,
    WBSMetadataSection,
    WBSStructureSection,
    WBSTask,
)
from .store import WBSStore

__all__ = [
    "MasterData",
    "WBSDocument",
    "WBSMetadataSection",
    "WBSStructureSection",
    "WBSTask",
    "WBSStore",
]
