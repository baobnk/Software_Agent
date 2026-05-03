"""BnK BRD package — schema, per-section operations, and renderer.

Module layout:
  schema.py      Pydantic AST (BRDDocument + nested types)
  operations.py  Explicit CRUD per section: set_purpose, add_constraint,
                 upsert_fr, ... — one function per (section, action) pair
  renderer.py    Render BRDDocument to .docx using language-aware templates
"""
from .schema import (
    # Root + leaf rows
    BRDDocument,
    AudienceEntry,
    FunctionalRequirement,
    GlossaryEntry,
    IntegrationRow,
    NFRRow,
    Stakeholder,
    VersionEntry,
    # Section sub-models (one per template section)
    AcceptanceSection,
    AppendixSection,
    ContextSection,
    DataReqSection,
    GlossarySection,
    IntegrationsSection,
    IntroductionSection,
    MetadataSection,
    NFRSection,
    ScopeSection,
    StakeholdersSection,
)
from .store import BRDStore, SECTION_REGISTRY
from .renderer import render_brd_to_docx, available_languages

__all__ = [
    # Root + rows
    "BRDDocument",
    "AudienceEntry",
    "FunctionalRequirement",
    "GlossaryEntry",
    "IntegrationRow",
    "NFRRow",
    "Stakeholder",
    "VersionEntry",
    # Sections
    "AcceptanceSection",
    "AppendixSection",
    "ContextSection",
    "DataReqSection",
    "GlossarySection",
    "IntegrationsSection",
    "IntroductionSection",
    "MetadataSection",
    "NFRSection",
    "ScopeSection",
    "StakeholdersSection",
    # Store + renderer
    "BRDStore",
    "SECTION_REGISTRY",
    "render_brd_to_docx",
    "available_languages",
]
