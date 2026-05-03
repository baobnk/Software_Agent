#!/usr/bin/env python3
"""Token consumption analysis — static, no LLM client needed."""
import ast
import sys
from pathlib import Path

try:
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    def tok(s: str) -> int:
        return len(enc.encode(s))
except ImportError:
    def tok(s: str) -> int:
        return max(1, len(s) // 4)

BASE = Path(__file__).parent.parent  # bnk-deepagent/


def measure_file(path: Path) -> int:
    return tok(path.read_text(encoding="utf-8", errors="replace"))


def extract_tool_docstrings(py_file: Path) -> list[tuple[str, str]]:
    src = py_file.read_text(encoding="utf-8", errors="replace")
    results = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return results
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            name = ""
            if isinstance(dec, ast.Name):
                name = dec.id
            elif isinstance(dec, ast.Attribute):
                name = dec.attr
            if name == "tool":
                doc = ast.get_docstring(node) or ""
                results.append((node.name, doc))
    return results


def hr(title: str) -> None:
    print()
    print("=" * 68)
    print(f"  {title}")
    print("=" * 68)


sections: dict[str, int] = {}

# ── 1. System prompts ──────────────────────────────────────────────────────────
hr("1. SYSTEM PROMPTS (included in every model call)")
prompt_total = 0
for p in sorted(BASE.glob("prompts/*.py")):
    if p.name == "__init__.py":
        continue
    t = measure_file(p)
    prompt_total += t
    print(f"    {p.name:30s}  {t:6,} tok  ({p.stat().st_size:,} bytes)")
print(f"    {'TOTAL':30s}  {prompt_total:6,} tok")
sections["System prompts"] = prompt_total

# ── 2. Tool descriptions ───────────────────────────────────────────────────────
hr("2. TOOL DESCRIPTIONS (@tool docstrings — sent in every prompt)")
all_tools: list[tuple[int, str, str]] = []
for py in sorted(BASE.glob("tools/*.py")):
    for name, doc in extract_tool_docstrings(py):
        t = tok(f"{name}\n{doc}")
        all_tools.append((t, py.name, name))

all_tools.sort(key=lambda x: -x[0])
tool_total = sum(x[0] for x in all_tools)
print(f"    {'Tool':38s}  {'File':25s}  {'Tok':>6}")
print(f"    {'-'*38}  {'-'*25}  {'-'*6}")
for t, fname, name in all_tools:
    print(f"    {name:38s}  {fname:25s}  {t:6,}")
print(f"    {'TOTAL':38s}  {'':25s}  {tool_total:6,}")
sections["Tool descriptions (all @tool)"] = tool_total

# ── 3. SKILL.md files ─────────────────────────────────────────────────────────
hr("3. SKILL.md FILES (loaded per-subagent when that skill activates)")
skill_total = 0
for p in sorted(BASE.glob("skills/**/SKILL.md")):
    t = measure_file(p)
    skill_total += t
    rel = str(p.relative_to(BASE))
    print(f"    {rel:50s}  {t:6,} tok  ({p.stat().st_size:,} bytes)")
print(f"    {'TOTAL (if all loaded simultaneously)':50s}  {skill_total:6,} tok")
sections["SKILL.md files (combined)"] = skill_total

# ── 4. CLAUDE.md injected by DeepAgents ───────────────────────────────────────
hr("4. CLAUDE.md (auto-injected by DeepAgents into every turn)")
p = BASE / "CLAUDE.md"
if p.exists():
    t = measure_file(p)
    print(f"    CLAUDE.md                               {t:6,} tok  ({p.stat().st_size:,} bytes)")
    sections["CLAUDE.md"] = t
else:
    print("    CLAUDE.md: not found")

# ── 5. Config files ────────────────────────────────────────────────────────────
hr("5. CONFIG FILES (loaded at startup, not per-turn)")
for p in sorted(list(BASE.glob("config/*.yaml")) + list(BASE.glob("config/*.json"))):
    t = measure_file(p)
    print(f"    {p.name:40s}  {t:5,} tok  ({p.stat().st_size:,} bytes)")

# ── 6. Workspace state sizes ───────────────────────────────────────────────────
hr("6. WORKSPACE STATE — assembled document sizes (per real session)")
ws_dirs = sorted(BASE.glob("workspace/*"))
if ws_dirs:
    for ws in ws_dirs[:5]:
        if not ws.is_dir():
            continue
        brd_dir = ws / "brd"
        wbs_dir = ws / "wbs"
        brd_files = (list(brd_dir.glob("*.json")) + list(brd_dir.glob("05_2_fr/*.json"))) if brd_dir.exists() else []
        wbs_files = (list(wbs_dir.glob("*.json")) + list(wbs_dir.glob("20_tasks/*.json"))) if wbs_dir.exists() else []
        brd_tok = sum(measure_file(f) for f in brd_files) if brd_files else 0
        wbs_tok = sum(measure_file(f) for f in wbs_files) if wbs_files else 0
        rf_tok  = measure_file(ws/"raw_features.md")       if (ws/"raw_features.md").exists()      else 0
        td_tok  = measure_file(ws/"technical_design.md")   if (ws/"technical_design.md").exists()   else 0
        am_tok  = measure_file(ws/"AGENTS.md")             if (ws/"AGENTS.md").exists()             else 0
        print(f"  Session: {ws.name[:40]}")
        print(f"    BRD shards    ({len(brd_files):2d} files): {brd_tok:6,} tok")
        print(f"    WBS shards    ({len(wbs_files):2d} files): {wbs_tok:6,} tok")
        print(f"    raw_features.md:          {rf_tok:6,} tok")
        print(f"    technical_design.md:      {td_tok:6,} tok")
        print(f"    AGENTS.md:                {am_tok:6,} tok")
        print()
else:
    print("    (no workspace sessions found — run a full pipeline to see live sizes)")

# ── 7. DeepAgents built-in tool overhead ─────────────────────────────────────
hr("7. DEEPAGENTS BUILT-IN TOOLS (framework adds these — estimates)")
builtin = [
    ("write_todos",    "Write a structured todo list to track multi-step tasks."),
    ("read_file",      "Read the contents of a file at a given path."),
    ("write_file",     "Write content to a file at a given path."),
    ("edit_file",      "Edit a file by replacing a specific string with a new string."),
    ("read_directory", "List the contents of a directory including file names and sizes."),
    ("glob_search",    "Search for files matching a glob pattern."),
    ("grep_search",    "Search for a text pattern inside files."),
    ("ask_subagent",   "Delegate a sub-task to a specialist subagent."),
]
builtin_total = 0
for name, desc in builtin:
    t = tok(f"{name}\n{desc}")
    builtin_total += t
    print(f"    {name:30s}  ~{t:5,} tok")
print(f"    {'TOTAL (estimated)':30s}  ~{builtin_total:5,} tok")
sections["DeepAgents built-in tools (est.)"] = builtin_total

# ── SUMMARY ──────────────────────────────────────────────────────────────────
hr("SUMMARY — FIXED OVERHEAD PER TURN (worst-case)")
grand = 0
for label, t in sections.items():
    bar = "█" * min(50, t // 100)
    print(f"    {label:42s}  {t:7,} tok  {bar}")
    grand += t
print()
print(f"    {'TOTAL STATIC CONTEXT OVERHEAD':42s}  {grand:7,} tok")
print()
print("  Legend:")
print("    • System prompts   — loaded every model call (orchestrator + active subagent)")
print("    • Tool descriptions — every @tool docstring goes in every prompt")
print("    • SKILL.md          — only the active subagent's skills are loaded")
print("    • CLAUDE.md         — injected automatically by DeepAgents each turn")
print("    • Workspace state   — read by tools on demand, NOT auto-injected")
print("    • Built-in tools    — added by create_deep_agent framework")
