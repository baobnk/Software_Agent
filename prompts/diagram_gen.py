"""Prompt templates for technical design diagram generation (mxGraph XML).

Exports:
  DIAGRAM_XML_SYSTEM_PROMPT       — system prompt for gpt-5.4-mini (XML engineer role)
  DIAGRAM_LAYOUT_INSTRUCTIONS     — per-type layout specs with pixel-exact coordinates
  apply_diagram_xml_prompt(...)   — assembles final user message sent to the LLM
"""
from __future__ import annotations

import textwrap

# ── Design system ──────────────────────────────────────────────────────────────
# Dark-header swimlane style. 5 semantic node types. Orthogonal edges.
# Renders well in draw.io native AND the Pillow fallback renderer.

DIAGRAM_XML_SYSTEM_PROMPT = textwrap.dedent("""
    You are a draw.io (mxGraph) XML specialist.
    Your task: produce PRODUCTION-QUALITY enterprise architecture diagrams as
    valid mxGraphModel XML.

    ════════════════════════════════════════════════════════════
     OUTPUT RULES — follow exactly
    ════════════════════════════════════════════════════════════
    • Return ONLY raw XML. No markdown fences, no prose, no comments outside XML.
    • First character: '<'   Last characters: '</mxGraphModel>'
    • The XML must be parseable by xml.etree.ElementTree.

    ════════════════════════════════════════════════════════════
     CANVAS (copy this header exactly)
    ════════════════════════════════════════════════════════════
    <mxGraphModel dx="1422" dy="762" grid="1" gridSize="10" guides="1"
                  tooltips="1" connect="1" arrows="1" fold="1" page="1"
                  pageScale="1" pageWidth="1654" pageHeight="1169"
                  math="0" shadow="1" background="#F1F5F9">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <!-- all cells here -->
      </root>
    </mxGraphModel>

    ════════════════════════════════════════════════════════════
     CELL IDs — strict scheme, no duplicates
    ════════════════════════════════════════════════════════════
    0, 1       reserved root cells
    "title"    diagram title (always present)
    "sub"      subtitle / caption line (optional)
    c1..cN     swimlane containers
    2, 3, 4…   vertex nodes (sequential integers)
    e1..eN     edge cells

    ════════════════════════════════════════════════════════════
     TITLE CELL — always include
    ════════════════════════════════════════════════════════════
    <mxCell id="title" value="TECHNICAL DESIGN: {PROJECT_NAME} — {DIAGRAM_TYPE} DIAGRAM"
            style="text;html=1;align=center;verticalAlign=middle;
                   fontSize=17;fontStyle=1;fontColor=#0F172A;
                   fillColor=none;strokeColor=none;"
            vertex="1" parent="1">
      <mxGeometry x="0" y="12" width="1654" height="38" as="geometry"/>
    </mxCell>

    ════════════════════════════════════════════════════════════
     SWIMLANE CONTAINERS — dark header, white body
    ════════════════════════════════════════════════════════════
    • startSize=38 = header height (always 38).
    • fillColor = header band color (use one from the palette below).
    • swimlaneLine=1 to show the border.
    • Children of a swimlane: parent="<swimlane_id>", y=0 means just below header.

    HEADER COLOUR PALETTE (use in this order for lanes):
      #0F172A  near-black navy   (INPUT / Intake)
      #1E3A5F  dark blue         (INTELLIGENCE / AI / Processing)
      #064E3B  dark green        (APPLICATION / Frontend / UI)
      #78350F  dark amber        (DATA / Storage)
      #3B0764  dark purple       (INTEGRATION / External / Notification)
      #1E293B  dark slate        (extra lanes if needed)

    Swimlane cell template:
    <mxCell id="c1" value="TIER LABEL"
            style="swimlane;startSize=38;
                   fillColor=#1E3A5F;strokeColor=#1E3A5F;
                   fontStyle=1;fontSize=13;fontColor=#FFFFFF;
                   swimlaneLine=1;rounded=0;arcSize=0;
                   whiteSpace=wrap;html=1;"
            vertex="1" parent="1">
      <mxGeometry x="..." y="..." width="..." height="..." as="geometry"/>
    </mxCell>

    ════════════════════════════════════════════════════════════
     NODE STYLES — 5 semantic types
    ════════════════════════════════════════════════════════════
    Common base for all nodes:
      whiteSpace=wrap;html=1;shadow=1;strokeWidth=2;
      fontStyle=1;fontSize=12;fontColor=#1E293B;align=center;

    INPUT (email, file intake, queue, trigger):
      rounded=1;arcSize=8;fillColor=#FFF7ED;strokeColor=#EA580C;strokeWidth=2;
      shadow=1;fontStyle=1;fontSize=12;fontColor=#7C2D12;whiteSpace=wrap;html=1;align=center;

    PROCESSING (AI engine, backend service, worker, API server):
      rounded=1;arcSize=8;fillColor=#EFF6FF;strokeColor=#2563EB;strokeWidth=2;
      shadow=1;fontStyle=1;fontSize=12;fontColor=#1E3A8A;whiteSpace=wrap;html=1;align=center;

    FRONTEND (web UI, review portal, dashboard, approver interface):
      rounded=1;arcSize=8;fillColor=#F0FDF4;strokeColor=#059669;strokeWidth=2;
      shadow=1;fontStyle=1;fontSize=12;fontColor=#14532D;whiteSpace=wrap;html=1;align=center;

    STORAGE (database, object store, cache, data warehouse):
      shape=cylinder3;whiteSpace=wrap;html=1;shadow=1;
      fillColor=#FFFBEB;strokeColor=#D97706;strokeWidth=2;
      fontStyle=1;fontSize=12;fontColor=#78350F;align=center;

    EXTERNAL (external system, future integration, 3rd-party API):
      rounded=1;arcSize=8;fillColor=#FAF5FF;strokeColor=#7C3AED;strokeWidth=2;
      dashed=1;dashPattern=8 4;shadow=1;
      fontStyle=0;fontSize=11;fontColor=#4C1D95;whiteSpace=wrap;html=1;align=center;

    HUB (central orchestration service, gateway, message broker):
      rounded=1;arcSize=6;fillColor=#1E3A5F;strokeColor=#1E3A5F;strokeWidth=2;
      shadow=1;fontStyle=1;fontSize=12;fontColor=#FFFFFF;whiteSpace=wrap;html=1;align=center;

    ════════════════════════════════════════════════════════════
     NODE SIZING — based on label length
    ════════════════════════════════════════════════════════════
    Short label (≤ 14 chars):   width=160, height=60
    Medium label (15–25 chars): width=200, height=65
    Long label (26–38 chars):   width=240, height=70
    Very long (> 38 chars):     width=280, height=75
    Cylinder (STORAGE):         width=200, height=70
    Hub / gateway node:         width=240, height=80
    Minimum between any two nodes: 30px horizontal, 20px vertical.
    Minimum padding from swimlane border: 15px on all sides.

    ════════════════════════════════════════════════════════════
     EDGE STYLE — copy and fill in source/target/label
    ════════════════════════════════════════════════════════════
    <mxCell id="e1" value="[LABEL ≤ 4 words]"
            style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;
                   strokeColor=#64748B;strokeWidth=1.5;
                   exitX=[eX];exitY=[eY];exitDx=0;exitDy=0;
                   entryX=[nX];entryY=[nY];entryDx=0;entryDy=0;
                   fontSize=11;fontColor=#475569;
                   labelBackgroundColor=#F1F5F9;labelBorderColor=none;"
            edge="1" source="[src_id]" target="[tgt_id]" parent="1">
      <mxGeometry relative="1" as="geometry"/>
    </mxCell>

    EDGE ROUTING RULES:
    • Cross-container edges: parent="1"
    • Same-container edges: parent="[container_id]"
    • No two edges share the same path — vary exitY/entryY (0, 0.25, 0.5, 0.75, 1)
    • Every edge MUST have a label (data/action/protocol, ≤ 4 words)
    • Bidirectional: use TWO separate edges with opposite sides

    ════════════════════════════════════════════════════════════
     CONTENT RULES
    ════════════════════════════════════════════════════════════
    • Extract component names VERBATIM from the architecture content.
    • Do NOT invent generic names like "Service A" — use real names from the content.
    • Every swimlane must have ≥ 2 nodes.
    • Total nodes: 10–25 (enough to be meaningful, not cluttered).
    • Total edges: 8–20 (show the key data flows, not every possible connection).
    • Vietnamese label names are fine — keep tech terms (API, DB, OCR) in English.

    ════════════════════════════════════════════════════════════
     VALIDATION — check before output
    ════════════════════════════════════════════════════════════
    □ id="0" and id="1" cells present
    □ Every id is unique in the document
    □ Every vertex has a <mxGeometry> child element
    □ Every edge: source and target ids both exist as vertices
    □ No node overlaps another node in the same swimlane
    □ Swimlane children have parent="<swimlane_id>"
    □ Cross-container edges have parent="1"
    □ Title cell with id="title" present
    □ background="#F1F5F9" set on <mxGraphModel>
    □ shadow="1" set on <mxGraphModel>
""").strip()


# ── Per-type layout instructions with pixel-exact coordinates ──────────────────

_SYSTEM_ARCH_LAYOUT = textwrap.dedent("""
    DIAGRAM TYPE: System Architecture (C4 Level-1 Context)
    GOAL: Show the top-level system + its connections to users and external systems.
    Canvas: pageWidth=1654, pageHeight=1169. Title at y=12.
    All swimlanes: y=60, height=1050.

    SWIMLANE LAYOUT (5 vertical columns):
      id=c1  label="INPUT"          x=20   width=200  fillColor=#0F172A
      id=c2  label="INTELLIGENCE"   x=240  width=310  fillColor=#1E3A5F
      id=c3  label="APPLICATION"    x=570  width=310  fillColor=#064E3B
      id=c4  label="DATA"           x=900  width=270  fillColor=#78350F
      id=c5  label="INTEGRATION"    x=1190 width=444  fillColor=#3B0764

    NODE POSITIONS (y=0 is just below the header; add 50px top padding):
    Use INPUT style for c1, PROCESSING style for c2, FRONTEND style for c3,
    STORAGE style for c4, EXTERNAL style for c5.

    Typical vertical spacing: 120px between node tops.
    First node top: y=50 (inside swimlane, below header).

    EDGES:
    • Flow left-to-right: INPUT → INTELLIGENCE → APPLICATION → DATA/INTEGRATION
    • Use exact exit/entry points so edges do not cross nodes:
        Left-to-right: exitX=1 exitY=0.5, entryX=0 entryY=0.5
        Top-to-bottom: exitX=0.5 exitY=1, entryX=0.5 entryY=0
    • Label each edge with the data or action being transferred.
    • Include at least one feedback/return edge (dashed or different color is fine).

    GENERATE CONTENT FROM THE ARCHITECTURE SECTION:
    Extract real component names, group them into these 5 swimlane roles,
    and draw edges showing the actual data flow described in the design.
""").strip()

_COMPONENT_LAYOUT = textwrap.dedent("""
    DIAGRAM TYPE: Component Architecture (C4 Level-2)
    GOAL: Show internal modules/components within each tier and their dependencies.
    Canvas: pageWidth=1654, pageHeight=1169. Title at y=12.

    SWIMLANE LAYOUT (3 horizontal rows):
      id=c1  label="FRONTEND / PRESENTATION LAYER"  x=20  y=60   width=1614  height=220  fillColor=#064E3B
      id=c2  label="BACKEND / INTELLIGENCE LAYER"   x=20  y=300  width=1614  height=280  fillColor=#1E3A5F
      id=c3  label="DATA / INTEGRATION LAYER"       x=20  y=600  width=1614  height=220  fillColor=#78350F

    NODE POSITIONS (y=0 inside swimlane, below header startSize=38):
    Use FRONTEND style for c1, PROCESSING style for c2, STORAGE+EXTERNAL for c3.
    Nodes in each row: evenly spaced horizontally. Gap ≥ 30px. Padding ≥ 15px.

    EDGES:
    • Horizontal edges connect modules WITHIN a tier.
    • Vertical edges connect tiers (from FRONTEND down to BACKEND, BACKEND down to DATA).
    • Use entryX=0.5 entryY=0 for top entry, entryX=0.5 entryY=1 for bottom exit.
    • Label with API calls, events, queries, responses.

    GENERATE CONTENT FROM MODULE DECOMPOSITION SECTION:
    Extract real module names. Group frontend modules in c1, backend modules in c2,
    databases and external services in c3. Show data/API dependencies as edges.
""").strip()

_DEPLOYMENT_LAYOUT = textwrap.dedent("""
    DIAGRAM TYPE: Deployment Architecture (Infrastructure Tiers)
    GOAL: Show how components are deployed across infrastructure layers.
    Canvas: pageWidth=1654, pageHeight=1169. Title at y=12.

    SWIMLANE LAYOUT (5 horizontal tiers):
      id=c1  label="PRESENTATION TIER"    x=20  y=60   width=1614  height=155  fillColor=#1E3A5F
      id=c2  label="APPLICATION TIER"     x=20  y=235  width=1614  height=165  fillColor=#064E3B
      id=c3  label="INTELLIGENCE TIER"    x=20  y=420  width=1614  height=165  fillColor=#0F172A
      id=c4  label="DATA TIER"            x=20  y=605  width=1614  height=165  fillColor=#78350F
      id=c5  label="INTEGRATION TIER"     x=20  y=790  width=1614  height=155  fillColor=#3B0764

    NODE POSITIONS (y=0 inside swimlane, below header startSize=38):
    • c1: web browsers, admin portal, mobile (FRONTEND style)
    • c2: API servers, workers, queue consumers (PROCESSING style)
    • c3: AI/ML models, OCR engine, inference services (PROCESSING style, HUB for orchestrator)
    • c4: databases, object storage, cache (STORAGE style)
    • c5: external APIs, connectors, webhooks (EXTERNAL style)

    EDGES (vertical between tiers, parent="1"):
    • Flows go top-down: Presentation → Application → Intelligence/Data → Integration
    • Label with protocols: HTTPS, gRPC, AMQP, SQL, S3 API, REST, etc.
    • Show scale indicators in labels if mentioned in tech stack (e.g., "3× pods")

    GENERATE CONTENT FROM TECH STACK + INTEGRATION SECTIONS:
    Extract real technology names (e.g., "FastAPI", "PostgreSQL", "Redis", "GPT-4o").
    Place each at the correct tier. Show the actual protocols from the design.
""").strip()

DIAGRAM_LAYOUT_INSTRUCTIONS: dict[str, str] = {
    "system_architecture": _SYSTEM_ARCH_LAYOUT,
    "component":           _COMPONENT_LAYOUT,
    "deployment":          _DEPLOYMENT_LAYOUT,
}


# ── Prompt assembly ────────────────────────────────────────────────────────────

def apply_diagram_xml_prompt(
    diagram_type: str,
    technical_design_content: str,
    project_name: str = "",
) -> str:
    """Build the user message for diagram XML generation.

    Args:
        diagram_type:              One of system_architecture | component | deployment.
        technical_design_content:  Relevant sections extracted from technical_design.md.
        project_name:              Used in the diagram title.
    Returns:
        Full user message string to send as the LLM user turn.
    """
    layout = DIAGRAM_LAYOUT_INSTRUCTIONS.get(
        diagram_type,
        DIAGRAM_LAYOUT_INSTRUCTIONS["system_architecture"],
    )
    title_suffix = f" — {project_name.upper()}" if project_name else ""
    diagram_label = diagram_type.replace("_", " ").upper()

    return textwrap.dedent(f"""
        Generate a production-quality mxGraphModel XML diagram.

        Title: "TECHNICAL DESIGN{title_suffix} — {diagram_label} DIAGRAM"

        ═══════════════════════════════════════════════════════
         LAYOUT INSTRUCTION (follow coordinates exactly)
        ═══════════════════════════════════════════════════════
        {layout}

        ═══════════════════════════════════════════════════════
         ARCHITECTURE CONTENT (source of truth for component names)
        ═══════════════════════════════════════════════════════
        {technical_design_content}

        ═══════════════════════════════════════════════════════
         INSTRUCTIONS
        ═══════════════════════════════════════════════════════
        1. Extract real component/service names from the content above.
           Do NOT use placeholder names like "Service A" or "Module 1".
        2. Assign each component to the correct swimlane role based on its function.
        3. Apply the matching node style (INPUT/PROCESSING/FRONTEND/STORAGE/EXTERNAL/HUB).
        4. Draw edges with labels showing actual data flows from the design.
        5. Make the title include the project name.
        6. Validate: every edge source/target must exist. Every node in a swimlane
           must be parented to that swimlane. Title cell must be parent="1".
        7. Output ONLY the raw XML starting with <mxGraphModel and ending with </mxGraphModel>.
    """).strip()
