"""Long-term memory tools — Tier 3 (LangGraph Store).

These tools wrap `infra.persistence.get_store()` with explicit, typed schemas
so the agent never calls raw `store.put`. Every memory write goes through one
of these tools and lands in a documented namespace (see CLAUDE.md §15).

Namespaces used here:
  ("users",    user_id, "preferences")              — durable user prefs
  ("projects", project_id, "decisions")             — solution-design decisions

Adding a new tool? Update the namespace table in CLAUDE.md §15 first.
"""
from __future__ import annotations

from langchain_core.tools import tool

from infra.persistence import get_store


# ── User preferences ─────────────────────────────────────────────────────────

@tool
def save_user_preference(user_id: str, key: str, value: str) -> str:
    """Persist a durable user preference that should follow the user across
    sessions (e.g. preferred language, default OUTPUT_DIR, default model).

    Args:
        user_id: Stable identifier for the user (email, UUID, or login).
        key:     Preference name. Use snake_case. Examples: "language",
                 "default_model", "default_output_dir".
        value:   Preference value as a string.

    Returns:
        Confirmation message.
    """
    if not user_id or not key:
        return "ERROR: user_id and key are required."
    store = get_store()
    store.put(
        ("users", user_id, "preferences"),
        key,
        {"value": value},
    )
    return f"Saved preference {key}={value!r} for user {user_id}."


@tool
def recall_user_preferences(user_id: str) -> str:
    """Read all stored preferences for a user. Returns a formatted list, or
    a 'no preferences' message if none exist.

    Args:
        user_id: Stable identifier for the user.
    """
    if not user_id:
        return "ERROR: user_id is required."
    store = get_store()
    items = store.search(("users", user_id, "preferences"))
    if not items:
        return f"No preferences stored for user {user_id}."
    lines = [f"- {item.key}: {item.value.get('value', '')}" for item in items]
    return f"Preferences for {user_id}:\n" + "\n".join(lines)


# ── Project decisions ────────────────────────────────────────────────────────

@tool
def save_project_decision(
    project_id: str,
    decision: str,
    rationale: str = "",
) -> str:
    """Log an architecture, scope, or technology decision made during solution
    design. Decisions persist across sessions so future BRD/WBS work can
    reference them and avoid re-litigating.

    Args:
        project_id: Project identifier (BnK code or slug, e.g. "BNK-GEHP").
        decision:   Concise statement of what was decided (≤ 200 chars).
                    Example: "Use PostgreSQL instead of MongoDB for transactions".
        rationale:  Why this decision was made. Optional but recommended.

    Returns:
        Confirmation message.
    """
    if not project_id or not decision:
        return "ERROR: project_id and decision are required."
    store = get_store()
    key = decision[:80].strip()
    store.put(
        ("projects", project_id, "decisions"),
        key,
        {"decision": decision, "rationale": rationale},
    )
    return f"Logged decision for {project_id}: {key}"


@tool
def recall_project_decisions(project_id: str) -> str:
    """List all decisions previously logged for this project. Use at the start
    of a new session to learn what has already been agreed.

    Args:
        project_id: Project identifier.
    """
    if not project_id:
        return "ERROR: project_id is required."
    store = get_store()
    items = store.search(("projects", project_id, "decisions"))
    if not items:
        return f"No decisions logged for project {project_id}."
    lines = []
    for item in items:
        v = item.value
        line = f"- {v.get('decision', item.key)}"
        if v.get("rationale"):
            line += f"\n  Rationale: {v['rationale']}"
        lines.append(line)
    return f"Decisions for {project_id}:\n" + "\n".join(lines)


__all__ = [
    "save_user_preference",
    "recall_user_preferences",
    "save_project_decision",
    "recall_project_decisions",
]
