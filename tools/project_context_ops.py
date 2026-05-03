"""Project context tools — capture everything discovered in the clarification phase.

This is the "source of truth" for non-requirement project metadata:
  - Team composition
  - Delivery timeline & deadline
  - Budget
  - Existing systems & integrations
  - Delivery phases
  - Stakeholders
  - Constraints & assumptions

All downstream agents (BRD drafter, WBS planner, effort estimator) read
from this context to produce accurate, project-specific outputs.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Optional

from langchain_core.tools import tool

from .workspace import read_json, write_json, read_text

PROJECT_CONTEXT_FILE  = "project_context.json"
REQUIREMENTS_FILE     = "requirements_analysis.json"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_ctx() -> dict:
    return read_json(PROJECT_CONTEXT_FILE) or {}


def _save_ctx(data: dict) -> None:
    write_json(PROJECT_CONTEXT_FILE, data)


def _load_analysis() -> dict:
    return read_json(REQUIREMENTS_FILE) or {
        "user_personas": [],
        "business_rules": [],
        "data_entities": [],
        "integration_map": [],
        "risks": [],
        "constraints": [],
        "assumptions": [],
        "moscow_priority": {"must": [], "should": [], "could": [], "wont": []},
    }


def _save_analysis(data: dict) -> None:
    write_json(REQUIREMENTS_FILE, data)


# ── Project Context Tools ─────────────────────────────────────────────────────

@tool
def set_project_background(
    project_name: str,
    project_code: str,
    background: str,
    objectives: list[str],
    client_name: str = "",
    client_industry: str = "",
) -> str:
    """Record the project background and objectives from discovery.

    background: 1-3 paragraphs explaining WHY this project exists.
    objectives: list of specific, measurable goals.
    """
    ctx = _load_ctx()
    ctx.update({
        "project_name": project_name,
        "project_code": project_code,
        "client_name": client_name,
        "client_industry": client_industry,
        "background": background,
        "objectives": objectives,
    })
    _save_ctx(ctx)
    return f"Project background set: {project_name} ({project_code}), {len(objectives)} objectives"


@tool
def set_team_composition(
    be_count: int = 0,
    fe_count: int = 0,
    fullstack_count: int = 0,
    qc_count: int = 1,
    ba_count: int = 1,
    pm_count: int = 1,
    ai_ml_count: int = 0,
    devops_count: int = 0,
    notes: str = "",
) -> str:
    """Record the team composition for effort and timeline calculation.

    This directly affects the WBS calendar timeline.
    Example: 2 BE + 2 FE + 1 QC + 1 BA + 1 PM = standard web project team.
    """
    total_dev = be_count + fe_count + fullstack_count + ai_ml_count
    total = total_dev + qc_count + ba_count + pm_count + devops_count
    ctx = _load_ctx()
    ctx["team"] = {
        "be": be_count,
        "fe": fe_count,
        "fullstack": fullstack_count,
        "qc": qc_count,
        "ba": ba_count,
        "pm": pm_count,
        "ai_ml": ai_ml_count,
        "devops": devops_count,
        "total_dev_capacity": total_dev,
        "total_headcount": total,
        "notes": notes,
    }
    _save_ctx(ctx)
    return (f"Team set: {total_dev} devs (BE:{be_count} FE:{fe_count} FS:{fullstack_count} "
            f"AI:{ai_ml_count}) + QC:{qc_count} BA:{ba_count} PM:{pm_count} | "
            f"Total dev capacity: {total_dev} md/day")


@tool
def set_delivery_timeline(
    target_delivery_date: str,
    start_date: str = "",
    timeline_months: float = 0,
    sprint_length_weeks: int = 2,
    buffer_percentage: float = 15.0,
    delivery_notes: str = "",
) -> str:
    """Record the delivery timeline constraint.

    target_delivery_date: ISO date string (YYYY-MM-DD) or descriptive ("Q3 2025")
    start_date: when development kicks off (ISO date or empty = today)
    timeline_months: total duration in months (calculated if 0)
    sprint_length_weeks: sprint cadence (default 2 weeks)
    buffer_percentage: risk/buffer padding on top of estimated effort (10-30%)
    """
    ctx = _load_ctx()
    if not start_date:
        start_date = date.today().isoformat()

    ctx["timeline"] = {
        "start_date": start_date,
        "target_delivery_date": target_delivery_date,
        "timeline_months": timeline_months,
        "sprint_length_weeks": sprint_length_weeks,
        "buffer_percentage": buffer_percentage,
        "delivery_notes": delivery_notes,
    }
    _save_ctx(ctx)
    return (f"Timeline: {start_date} → {target_delivery_date} "
            f"({timeline_months}m, {sprint_length_weeks}w sprints, {buffer_percentage}% buffer)")


@tool
def set_project_scope(
    in_scope: list[str],
    out_of_scope: list[str],
    delivery_phases: list[dict],
) -> str:
    """Define what IS and IS NOT in scope, and phased delivery plan.

    delivery_phases: list of phase objects, each with:
      {name, description, features: [...], target_date, milestone}

    Example phases for a 6-month project:
      Phase 1 (Month 1-2): Core features (auth, CRUD)
      Phase 2 (Month 3-4): Advanced features (reports, integrations)
      Phase 3 (Month 5-6): AI features, optimization, hardening
    """
    ctx = _load_ctx()
    ctx["scope"] = {
        "in_scope": in_scope,
        "out_of_scope": out_of_scope,
        "delivery_phases": delivery_phases,
    }
    _save_ctx(ctx)
    n_phases = len(delivery_phases)
    n_in = len(in_scope)
    n_out = len(out_of_scope)
    return f"Scope set: {n_in} in-scope, {n_out} out-of-scope, {n_phases} delivery phases"


@tool
def set_budget_and_constraints(
    budget_usd: float = 0,
    budget_vnd: float = 0,
    budget_notes: str = "",
    tech_stack_required: list[str] = None,
    tech_stack_excluded: list[str] = None,
    compliance_requirements: list[str] = None,
    special_constraints: list[str] = None,
) -> str:
    """Record budget and hard constraints (technology, compliance, etc.).

    compliance_requirements: e.g. ["PDPA", "PCI-DSS", "ISO 27001"]
    special_constraints: e.g. ["Must integrate with legacy SAP", "No cloud — on-premise only"]
    """
    ctx = _load_ctx()
    ctx["constraints"] = {
        "budget_usd": budget_usd,
        "budget_vnd": budget_vnd,
        "budget_notes": budget_notes,
        "tech_stack_required": tech_stack_required or [],
        "tech_stack_excluded": tech_stack_excluded or [],
        "compliance": compliance_requirements or [],
        "special": special_constraints or [],
    }
    _save_ctx(ctx)
    return f"Constraints set: budget={budget_usd or budget_vnd}, {len(tech_stack_required or [])} required tech"


@tool
def add_stakeholder(
    name: str,
    role: str,
    organization: str = "",
    responsibilities: str = "",
    contact: str = "",
) -> str:
    """Add a stakeholder/representative to the project.

    Examples:
      name="Nguyễn Văn A", role="Product Owner", org="MBAL", responsibilities="Approve BRD"
      name="BnK Solution", role="Development Team", responsibilities="Design + Build"
    """
    ctx = _load_ctx()
    stakeholders = ctx.get("stakeholders", [])
    stakeholders.append({
        "name": name,
        "role": role,
        "organization": organization,
        "responsibilities": responsibilities,
        "contact": contact,
    })
    ctx["stakeholders"] = stakeholders
    _save_ctx(ctx)
    return f"Stakeholder added: {name} ({role} @ {organization or 'N/A'})"


@tool
def add_integration(
    system_name: str,
    direction: str,
    protocol: str,
    description: str,
    complexity: str = "Medium",
) -> str:
    """Record an external system integration point.

    direction: "inbound" | "outbound" | "bidirectional"
    protocol: "REST API" | "Webhook" | "Database" | "Message Queue" | "File" | "SDK"
    complexity: "Low" | "Medium" | "High" (affects effort estimation)
    """
    ctx = _load_ctx()
    integrations = ctx.get("integrations", [])
    integrations.append({
        "system": system_name,
        "direction": direction,
        "protocol": protocol,
        "description": description,
        "complexity": complexity,
    })
    ctx["integrations"] = integrations
    _save_ctx(ctx)
    return f"Integration: {system_name} ({direction}, {protocol}, complexity={complexity})"


@tool
def get_project_context() -> str:
    """Return full project context summary (team, timeline, scope, integrations)."""
    ctx = _load_ctx()
    if not ctx:
        return "Project context not yet set. Run discovery phase first."

    lines = [f"=== Project Context: {ctx.get('project_name', 'N/A')} ==="]

    team = ctx.get("team", {})
    if team:
        lines.append(f"\nTeam: {team.get('total_dev_capacity', 0)} devs "
                     f"(BE:{team.get('be',0)} FE:{team.get('fe',0)} FS:{team.get('fullstack',0)}) "
                     f"+ QC:{team.get('qc',0)} BA:{team.get('ba',0)} PM:{team.get('pm',0)}")

    tl = ctx.get("timeline", {})
    if tl:
        lines.append(f"Timeline: {tl.get('start_date')} → {tl.get('target_delivery_date')} "
                     f"({tl.get('timeline_months',0)}m, buffer {tl.get('buffer_percentage',15)}%)")

    scope = ctx.get("scope", {})
    if scope:
        phases = scope.get("delivery_phases", [])
        lines.append(f"Scope: {len(scope.get('in_scope',[]))} in-scope items, "
                     f"{len(scope.get('out_of_scope',[]))} out-of-scope, "
                     f"{len(phases)} delivery phases")
        for ph in phases:
            lines.append(f"  • {ph.get('name')}: {ph.get('description', '')[:80]}")

    integrations = ctx.get("integrations", [])
    if integrations:
        lines.append(f"Integrations: {len(integrations)} external systems")
        for intg in integrations:
            lines.append(f"  • {intg['system']} ({intg['direction']}, {intg['complexity']})")

    stakeholders = ctx.get("stakeholders", [])
    if stakeholders:
        lines.append(f"Stakeholders: {', '.join(s['name'] + '(' + s['role'] + ')' for s in stakeholders[:5])}")

    objectives = ctx.get("objectives", [])
    if objectives:
        lines.append(f"\nObjectives ({len(objectives)}):")
        for obj in objectives[:5]:
            lines.append(f"  • {obj}")

    return "\n".join(lines)


# ── Requirements Analysis Tools ───────────────────────────────────────────────

@tool
def add_user_persona(
    persona_name: str,
    role: str,
    goals: list[str],
    pain_points: list[str],
    frequency: str = "Daily",
    technical_level: str = "Medium",
) -> str:
    """Add a user persona to the requirements analysis.

    persona_name: e.g. "Insurance Claims Officer", "End Customer", "Admin"
    goals: what this persona wants to achieve
    pain_points: current problems / frustrations
    frequency: how often they use the system
    technical_level: Low | Medium | High
    """
    data = _load_analysis()
    data["user_personas"].append({
        "name": persona_name,
        "role": role,
        "goals": goals,
        "pain_points": pain_points,
        "frequency": frequency,
        "technical_level": technical_level,
    })
    _save_analysis(data)
    return f"Persona added: {persona_name} ({role}), {len(goals)} goals, {len(pain_points)} pain points"


@tool
def add_business_rule(
    rule_id: str,
    category: str,
    description: str,
    source: str = "",
    priority: str = "High",
) -> str:
    """Add a business rule extracted from requirements.

    rule_id: "BR01", "BR02", ...
    category: "Validation" | "Calculation" | "Workflow" | "Authorization" | "Data"
    source: which requirement document / stakeholder said this
    """
    data = _load_analysis()
    data["business_rules"].append({
        "id": rule_id,
        "category": category,
        "description": description,
        "source": source,
        "priority": priority,
    })
    _save_analysis(data)
    return f"Business rule {rule_id} added: [{category}] {description[:80]}"


@tool
def add_risk(
    risk_id: str,
    category: str,
    description: str,
    probability: str,
    impact: str,
    mitigation: str,
) -> str:
    """Add a project risk to the risk register.

    risk_id: "R01", "R02", ...
    category: "Technical" | "Resource" | "Timeline" | "Requirement" | "Integration" | "Business"
    probability: "Low" | "Medium" | "High"
    impact: "Low" | "Medium" | "High" | "Critical"
    """
    data = _load_analysis()
    data["risks"].append({
        "id": risk_id,
        "category": category,
        "description": description,
        "probability": probability,
        "impact": impact,
        "mitigation": mitigation,
    })
    _save_analysis(data)
    return f"Risk {risk_id} added: [{category}] {description[:80]} (prob={probability}, impact={impact})"


@tool
def add_data_entity(
    entity_name: str,
    description: str,
    key_attributes: list[str],
    relationships: list[str] = None,
) -> str:
    """Add a key data entity identified during requirements analysis.

    Example: entity_name="Claim", key_attributes=["claim_id", "claim_type", "status", "amount"]
    relationships: ["belongs to Customer", "has many Documents"]
    """
    data = _load_analysis()
    data["data_entities"].append({
        "name": entity_name,
        "description": description,
        "key_attributes": key_attributes,
        "relationships": relationships or [],
    })
    _save_analysis(data)
    return f"Data entity added: {entity_name} ({len(key_attributes)} attributes)"


@tool
def set_moscow_priorities(
    must_have: list[str],
    should_have: list[str],
    could_have: list[str] = None,
    wont_have: list[str] = None,
) -> str:
    """Set MoSCoW prioritization for requirement features/FRs.

    must_have:   Critical for launch. Project fails without these.
    should_have: Important but not blocking launch.
    could_have:  Nice to have. Drop if time runs out.
    wont_have:   Explicitly out of scope for this delivery.
    """
    data = _load_analysis()
    data["moscow_priority"] = {
        "must": must_have,
        "should": should_have,
        "could": could_have or [],
        "wont": wont_have or [],
    }
    _save_analysis(data)
    total = len(must_have) + len(should_have) + len(could_have or [])
    return (f"MoSCoW set: Must={len(must_have)} Should={len(should_have)} "
            f"Could={len(could_have or [])} Won't={len(wont_have or [])}")


@tool
def get_requirements_analysis() -> str:
    """Return full requirements analysis summary (personas, rules, risks, entities)."""
    data = _load_analysis()
    lines = ["=== Requirements Analysis ==="]
    lines.append(f"Personas: {len(data['user_personas'])}")
    for p in data["user_personas"]:
        lines.append(f"  • {p['name']} ({p['role']}) — goals: {'; '.join(p['goals'][:2])}")
    lines.append(f"Business Rules: {len(data['business_rules'])}")
    for br in data["business_rules"][:5]:
        lines.append(f"  • {br['id']} [{br['category']}]: {br['description'][:80]}")
    lines.append(f"Data Entities: {len(data['data_entities'])}")
    for de in data["data_entities"]:
        lines.append(f"  • {de['name']}: {', '.join(de['key_attributes'][:4])}")
    lines.append(f"Risks: {len(data['risks'])}")
    for r in data["risks"][:3]:
        lines.append(f"  • {r['id']} [{r['category']}] prob={r['probability']} impact={r['impact']}: {r['description'][:60]}")
    moscow = data.get("moscow_priority", {})
    if moscow.get("must"):
        lines.append(f"MoSCoW — Must: {', '.join(moscow['must'][:5])}")
    return "\n".join(lines)
