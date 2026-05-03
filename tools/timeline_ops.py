"""Timeline + effort modeling tools.

Core insight: effort và timeline KHÔNG phải constant — chúng phụ thuộc vào:
  1. Domain của client (banking = more security/testing/docs)
  2. Deployment environment (on-prem vs cloud)
  3. Solution architecture (monolith vs microservices)
  4. Team velocity (seniority, familiarity with stack)
  5. Integration complexity
  6. Risk buffer
  7. Non-dev work: UAT, documentation, training, deployment

Domain multipliers (built-in):
  - banking/finance:  security +30%, docs +20%, UAT 3-4 weeks, on-prem likely
  - healthcare:       HIPAA audit +20%, docs +25%, data sensitivity high
  - insurance:        business rules complexity +25%, UAT 2-3 weeks
  - ecommerce:        payment integration overhead, load test +5 days
  - government:       docs +30%, testing +25%, long approval cycle
  - standard/saas:    baseline multipliers
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional

from langchain_core.tools import tool

from .workspace import read_json, write_json, read_text

TIMELINE_FILE    = "timeline.json"
EFFORT_MODEL_FILE = "effort_model.json"

# ── Domain multipliers ────────────────────────────────────────────────────────

DOMAIN_PROFILES: dict[str, dict] = {
    "banking": {
        "be_multiplier": 1.30,      # security, encryption, audit trails
        "qc_pct": 0.40,             # more testing coverage required
        "ba_pct": 0.20,             # more compliance docs
        "uat_weeks": 4,             # on-site UAT, multiple rounds
        "buffer_pct": 20,           # regulatory risk
        "deploy_days": 5,           # on-prem, change management, CAB approval
        "security_extra_days": 5,   # pen test, security review
        "doc_extra_days": 3,        # user manual, SOD documentation
        "notes": "On-premise likely. High security (PCI-DSS/Basel). Multi-round UAT. CAB approval for deployment.",
    },
    "insurance": {
        "be_multiplier": 1.25,
        "qc_pct": 0.35,
        "ba_pct": 0.18,
        "uat_weeks": 3,
        "buffer_pct": 18,
        "deploy_days": 4,
        "security_extra_days": 3,
        "doc_extra_days": 3,
        "notes": "Complex business rules. Regulatory compliance. UAT involves claims officers.",
    },
    "healthcare": {
        "be_multiplier": 1.20,
        "qc_pct": 0.35,
        "ba_pct": 0.18,
        "uat_weeks": 3,
        "buffer_pct": 18,
        "deploy_days": 3,
        "security_extra_days": 4,   # HIPAA, data privacy
        "doc_extra_days": 3,
        "notes": "Patient data privacy (HIPAA/PDPA). Audit trails mandatory. Clinical UAT with doctors/nurses.",
    },
    "government": {
        "be_multiplier": 1.15,
        "qc_pct": 0.35,
        "ba_pct": 0.25,             # heavy documentation requirements
        "uat_weeks": 4,
        "buffer_pct": 25,           # high uncertainty, changing requirements
        "deploy_days": 5,
        "security_extra_days": 3,
        "doc_extra_days": 5,
        "notes": "Long approval cycles. Heavy docs (TDD, SRS, UAT report). Government security standards.",
    },
    "ecommerce": {
        "be_multiplier": 1.10,
        "qc_pct": 0.28,
        "ba_pct": 0.12,
        "uat_weeks": 2,
        "buffer_pct": 12,
        "deploy_days": 2,
        "security_extra_days": 2,   # payment security
        "doc_extra_days": 1,
        "notes": "Payment gateway integration overhead. Load testing critical. Cloud-native.",
    },
    "logistics": {
        "be_multiplier": 1.15,
        "qc_pct": 0.30,
        "ba_pct": 0.14,
        "uat_weeks": 2,
        "buffer_pct": 15,
        "deploy_days": 2,
        "security_extra_days": 1,
        "doc_extra_days": 2,
        "notes": "Real-time tracking. Multiple 3rd party integrations (maps, shipping APIs).",
    },
    "standard": {
        "be_multiplier": 1.0,
        "qc_pct": 0.25,
        "ba_pct": 0.12,
        "uat_weeks": 2,
        "buffer_pct": 10,
        "deploy_days": 1,
        "security_extra_days": 1,
        "doc_extra_days": 1,
        "notes": "Standard SaaS / internal tool. Cloud deployment. Normal QC coverage.",
    },
}

# ── Complexity score table (per module type) ──────────────────────────────────
# score 1-5, used as effort multiplier: actual_md = base_md * (0.7 + 0.15 * score)

MODULE_COMPLEXITY_GUIDE = {
    "simple_crud":         1,
    "crud_with_filter":    2,
    "workflow_engine":     4,
    "report_dashboard":    3,
    "payment_integration": 4,
    "ai_ml_feature":       5,
    "auth_rbac":           3,
    "realtime_websocket":  3,
    "data_migration":      3,
    "third_party_api":     3,
    "file_ocr_processing": 4,
    "blockchain":          5,
}


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def set_domain_and_environment(
    domain: str,
    deployment_env: str,
    architecture: str = "monolith",
    existing_tech_debt: str = "Low",
    team_seniority: str = "Mid",
    notes: str = "",
) -> str:
    """Set the project domain and deployment environment.

    domain: banking | insurance | healthcare | government | ecommerce | logistics | standard
    deployment_env: cloud | on_premise | hybrid
    architecture: monolith | microservices | serverless | modular_monolith
    existing_tech_debt: Low | Medium | High (affects refactor effort)
    team_seniority: Junior | Mid | Senior | Mixed

    This is CRITICAL — it determines all effort multipliers.
    """
    domain_key = domain.lower().replace("-", "_").replace(" ", "_")
    if domain_key not in DOMAIN_PROFILES:
        domain_key = "standard"
    profile = DOMAIN_PROFILES[domain_key]

    # Team seniority adjustment
    seniority_factor = {"junior": 1.30, "mid": 1.0, "senior": 0.80, "mixed": 1.10}.get(
        team_seniority.lower(), 1.0
    )

    # Deployment env adjustment
    deploy_overhead = {"cloud": 0, "on_premise": 3, "hybrid": 2}.get(
        deployment_env.lower().replace("-", "_"), 0
    )

    model = {
        "domain": domain_key,
        "deployment_env": deployment_env,
        "architecture": architecture,
        "tech_debt": existing_tech_debt,
        "team_seniority": team_seniority,
        "seniority_factor": seniority_factor,
        "deploy_overhead_days": deploy_overhead + profile["deploy_days"],
        "profile": profile,
        "notes": notes or profile["notes"],
    }
    write_json(EFFORT_MODEL_FILE, model)

    return (
        f"Domain profile set: {domain_key.upper()}\n"
        f"  BE multiplier: {profile['be_multiplier']}x\n"
        f"  QC: {profile['qc_pct']*100:.0f}% of dev effort\n"
        f"  BA: {profile['ba_pct']*100:.0f}% of dev effort\n"
        f"  UAT: {profile['uat_weeks']} weeks\n"
        f"  Buffer: {profile['buffer_pct']}%\n"
        f"  Deploy overhead: {model['deploy_overhead_days']} days\n"
        f"  Team seniority factor: {seniority_factor}x\n"
        f"  Note: {profile['notes']}"
    )


@tool
def score_module_complexity(
    module_name: str,
    fr_id: str,
    base_be_days: float,
    base_fe_days: float,
    complexity_score: int,
    integration_count: int = 0,
    has_ai_ml: bool = False,
    notes: str = "",
) -> str:
    """Score a module's complexity and get adjusted effort estimates.

    complexity_score: 1 (simple CRUD) → 5 (highly complex, novel tech)
    integration_count: number of external systems this module touches
    has_ai_ml: True if module involves ML model training/inference

    Returns adjusted man-days WITH domain and complexity multipliers applied.
    """
    effort_model = read_json(EFFORT_MODEL_FILE) or {}
    profile = effort_model.get("profile", DOMAIN_PROFILES["standard"])
    seniority_factor = effort_model.get("seniority_factor", 1.0)

    # Complexity multiplier: score 1→0.85x, 2→1.0x, 3→1.2x, 4→1.5x, 5→2.0x
    complexity_mult = {1: 0.85, 2: 1.0, 3: 1.2, 4: 1.5, 5: 2.0}.get(complexity_score, 1.0)

    # Integration overhead: each external system adds 0.3 days per integration
    integration_overhead = integration_count * 0.3

    # AI/ML overhead
    ai_overhead = 2.0 if has_ai_ml else 0.0

    # Apply all multipliers
    adjusted_be = (base_be_days * complexity_mult * profile["be_multiplier"]
                   + integration_overhead + ai_overhead) * seniority_factor
    adjusted_fe = base_fe_days * complexity_mult * seniority_factor

    adjusted_be = round(adjusted_be, 1)
    adjusted_fe = round(adjusted_fe, 1)

    # Save to timeline file
    tl = read_json(TIMELINE_FILE) or {"modules": [], "total_be": 0, "total_fe": 0}
    tl.setdefault("modules", []).append({
        "name": module_name,
        "fr_id": fr_id,
        "complexity_score": complexity_score,
        "base_be": base_be_days,
        "base_fe": base_fe_days,
        "adjusted_be": adjusted_be,
        "adjusted_fe": adjusted_fe,
        "integration_count": integration_count,
        "has_ai_ml": has_ai_ml,
        "notes": notes,
    })
    tl["total_be"] = round(sum(m["adjusted_be"] for m in tl["modules"]), 1)
    tl["total_fe"] = round(sum(m["adjusted_fe"] for m in tl["modules"]), 1)
    write_json(TIMELINE_FILE, tl)

    return (
        f"{module_name} ({fr_id}) — complexity={complexity_score}/5\n"
        f"  Base: BE={base_be_days}d FE={base_fe_days}d\n"
        f"  Adjusted: BE={adjusted_be}d FE={adjusted_fe}d "
        f"(multipliers: domain={profile['be_multiplier']}x, complexity={complexity_mult}x, "
        f"seniority={seniority_factor}x)"
    )


@tool
def compute_project_timeline() -> str:
    """Calculate the full project calendar timeline from accumulated effort scores.

    Uses: domain profile, team composition, sprint length, buffer %.
    Returns: sprint plan, key milestones, total calendar duration.

    Call AFTER all modules have been scored with score_module_complexity.
    """
    from tools.workspace import read_json as _rj
    effort_model = _rj(EFFORT_MODEL_FILE) or {}
    ctx_raw = _rj("project_context.json") or {}
    tl = _rj(TIMELINE_FILE) or {}
    profile = effort_model.get("profile", DOMAIN_PROFILES["standard"])

    team = ctx_raw.get("team", {})
    total_dev_cap = team.get("total_dev_capacity", 2)  # devs (BE+FE)
    if total_dev_cap == 0:
        total_dev_cap = 2

    tl_cfg = ctx_raw.get("timeline", {})
    sprint_weeks = tl_cfg.get("sprint_length_weeks", 2)
    buffer_pct = tl_cfg.get("buffer_percentage", profile.get("buffer_pct", 15))
    try:
        start_date = date.fromisoformat(tl_cfg.get("start_date", date.today().isoformat()))
    except Exception:
        start_date = date.today()

    # Effort totals
    total_be = tl.get("total_be", 0)
    total_fe = tl.get("total_fe", 0)
    total_dev = total_be + total_fe

    # QC, BA, PM based on domain profile
    qc_days = round(total_dev * profile["qc_pct"], 1)
    ba_days = round(total_dev * profile["ba_pct"], 1)
    pm_days = round(total_dev * 0.05, 1)

    # Extra domain-specific tasks
    security_days = profile.get("security_extra_days", 1)
    doc_days = profile.get("doc_extra_days", 1)
    deploy_days = effort_model.get("deploy_overhead_days", profile["deploy_days"])
    uat_weeks = profile["uat_weeks"]

    # Total work incl. buffer
    buffer_days = round(total_dev * buffer_pct / 100, 1)
    grand_total = round(total_dev + qc_days + ba_days + pm_days
                        + security_days + doc_days + deploy_days + buffer_days, 1)

    # Calendar calculation
    sprint_days = sprint_weeks * 5  # working days per sprint
    # Daily throughput: total_dev_cap devs work in parallel
    dev_calendar_days = math.ceil(total_dev / total_dev_cap)
    total_calendar_days = (dev_calendar_days
                           + math.ceil(uat_weeks * 5)
                           + deploy_days + doc_days)
    total_calendar_weeks = math.ceil(total_calendar_days / 5)
    total_calendar_months = round(total_calendar_weeks / 4.3, 1)

    # Sprint count
    dev_sprints = math.ceil(dev_calendar_days / sprint_days)

    # Milestones
    def add_bdays(d: date, n: int) -> date:
        count = 0
        while count < n:
            d += timedelta(days=1)
            if d.weekday() < 5:
                count += 1
        return d

    m_kickoff   = start_date
    m_brd_done  = add_bdays(start_date, 10)      # 2 weeks
    m_dev_start = add_bdays(m_brd_done, 5)       # 1 week
    m_dev_done  = add_bdays(m_dev_start, dev_calendar_days)
    m_uat_start = add_bdays(m_dev_done, 5)        # 1 week buffer
    m_uat_done  = add_bdays(m_uat_start, uat_weeks * 5)
    m_golive    = add_bdays(m_uat_done, deploy_days)

    # Build sprint table
    sprints = []
    sprint_start = m_dev_start
    for i in range(1, dev_sprints + 1):
        sprint_end = add_bdays(sprint_start, sprint_days)
        sprints.append({
            "sprint": i,
            "start": sprint_start.isoformat(),
            "end": sprint_end.isoformat(),
            "capacity_md": total_dev_cap * sprint_days,
        })
        sprint_start = sprint_end

    result = {
        "effort_summary": {
            "total_be_md": total_be,
            "total_fe_md": total_fe,
            "total_dev_md": total_dev,
            "qc_md": qc_days,
            "ba_md": ba_days,
            "pm_md": pm_days,
            "security_md": security_days,
            "documentation_md": doc_days,
            "deployment_md": deploy_days,
            "buffer_md": buffer_days,
            "grand_total_md": grand_total,
        },
        "calendar": {
            "total_calendar_days": total_calendar_days,
            "total_calendar_weeks": total_calendar_weeks,
            "total_calendar_months": total_calendar_months,
            "dev_sprints": dev_sprints,
        },
        "milestones": {
            "kickoff":    m_kickoff.isoformat(),
            "brd_signed": m_brd_done.isoformat(),
            "dev_start":  m_dev_start.isoformat(),
            "dev_done":   m_dev_done.isoformat(),
            "uat_start":  m_uat_start.isoformat(),
            "uat_done":   m_uat_done.isoformat(),
            "go_live":    m_golive.isoformat(),
        },
        "sprints": sprints,
        "domain_notes": profile.get("notes", ""),
    }
    tl.update(result)
    write_json(TIMELINE_FILE, tl)

    lines = [
        "=== PROJECT TIMELINE COMPUTATION ===",
        f"Domain: {effort_model.get('domain', 'standard').upper()} | "
        f"Deploy: {effort_model.get('deployment_env', 'cloud')} | "
        f"Team: {total_dev_cap} devs",
        "",
        "EFFORT SUMMARY (man-days):",
        f"  Dev (BE+FE):   {total_dev:.1f} md  (BE:{total_be:.1f} FE:{total_fe:.1f})",
        f"  QC:            {qc_days:.1f} md  ({profile['qc_pct']*100:.0f}% of dev)",
        f"  BA:            {ba_days:.1f} md  ({profile['ba_pct']*100:.0f}% of dev)",
        f"  PM:            {pm_days:.1f} md  (5% of dev)",
        f"  Security:      {security_days:.1f} md  (domain-specific)",
        f"  Documentation: {doc_days:.1f} md",
        f"  Deployment:    {deploy_days:.1f} md",
        f"  Buffer ({buffer_pct:.0f}%): {buffer_days:.1f} md",
        f"  GRAND TOTAL:   {grand_total:.1f} man-days",
        "",
        "CALENDAR TIMELINE:",
        f"  Total duration: ~{total_calendar_months} months ({total_calendar_weeks} weeks)",
        f"  Dev sprints:    {dev_sprints} × {sprint_weeks}-week sprints",
        "",
        "MILESTONES:",
        f"  📋 Kickoff:        {m_kickoff}",
        f"  ✅ BRD signed:     {m_brd_done}",
        f"  🚀 Dev starts:     {m_dev_start}",
        f"  🔧 Dev complete:   {m_dev_done}",
        f"  🧪 UAT starts:     {m_uat_start}  ({uat_weeks} weeks UAT)",
        f"  ✅ UAT done:       {m_uat_done}",
        f"  🌟 Go-live:        {m_golive}",
        "",
        f"Domain note: {profile.get('notes', '')}",
    ]
    return "\n".join(lines)


@tool
def get_effort_model() -> str:
    """Return the current effort model (domain multipliers, team, timeline totals)."""
    effort_model = read_json(EFFORT_MODEL_FILE) or {}
    tl = read_json(TIMELINE_FILE) or {}
    if not effort_model:
        return "Effort model not set. Call set_domain_and_environment first."
    profile = effort_model.get("profile", {})
    lines = [
        f"Domain: {effort_model.get('domain', 'N/A')} | Env: {effort_model.get('deployment_env', 'N/A')}",
        f"BE multiplier: {profile.get('be_multiplier', 1.0)}x",
        f"Seniority factor: {effort_model.get('seniority_factor', 1.0)}x",
        f"QC %: {profile.get('qc_pct', 0.25)*100:.0f}% | BA %: {profile.get('ba_pct', 0.12)*100:.0f}%",
        f"UAT: {profile.get('uat_weeks', 2)} weeks | Buffer: {profile.get('buffer_pct', 10)}%",
    ]
    modules = tl.get("modules", [])
    if modules:
        lines.append(f"\nScored modules ({len(modules)}):")
        for m in modules:
            lines.append(f"  {m['name']} ({m['fr_id']}): BE={m['adjusted_be']}d FE={m['adjusted_fe']}d [score={m['complexity_score']}]")
        lines.append(f"  TOTAL: BE={tl.get('total_be',0)}d FE={tl.get('total_fe',0)}d")
    return "\n".join(lines)
