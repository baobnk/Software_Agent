"""End-to-end test: upload EC_Carpet.md → WBS Excel.

Usage:
    conda activate agent
    python test_ec_carpet.py
"""
import json
import sys
import textwrap
import requests

BASE = "http://localhost:8000"
FILE = "/mnt/f/code/agent/WBS_Agent/REQUIREMENT/EC_Carpet.md"
W    = 70  # wrap width for agent messages

# ── Colour helpers ────────────────────────────────────────────────────────────
def c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m"

def hdr(text: str) -> None:
    print(f"\n{c('1;36', '▶')} {c('1', text)}")

def ok(text: str) -> None:
    print(f"  {c('32', '✓')} {text}")

def info(text: str) -> None:
    print(f"  {c('34', '·')} {text}")

def warn(text: str) -> None:
    print(f"  {c('33', '⚠')} {text}")

def err(text: str) -> None:
    print(f"  {c('31', '✗')} {text}")

def tool_start(name: str) -> None:
    print(f"  {c('35', '⚙')} {c('35', name)}")

def tool_done(result: str) -> None:
    snippet = result.replace("\n", " ").strip()[:100]
    print(f"     └─ {c('90', snippet)}")

def hitl_box(tool: str, question: str) -> None:
    bar = c("1;35", "═" * 58)
    print(f"\n  {bar}")
    print(f"  {c('1;35', '  HITL CHECKPOINT')}")
    print(f"  {c('35', f'  Tool : {tool}')}")
    print(f"  {c('35', '  ─' * 29)}")
    for line in textwrap.wrap(question, W - 4):
        print(f"  {c('37', '  ' + line)}")
    print(f"  {bar}\n")


# ── SSE parser ────────────────────────────────────────────────────────────────
def sse_events(resp):
    """Yield (event_name, parsed_dict) from an SSE response."""
    event = ""
    for raw in resp.iter_lines(decode_unicode=True):
        if raw.startswith("event:"):
            event = raw[6:].strip()
        elif raw.startswith("data:"):
            try:
                yield event, json.loads(raw[5:].strip())
            except Exception:
                pass
        elif raw == "":
            event = ""


# ── Stream consumer ───────────────────────────────────────────────────────────
def consume(resp, label: str = "") -> dict | None:
    """Stream events, print nicely, return hitl payload if HITL fires."""
    resp.raise_for_status()
    msg_buf: dict[str, str] = {}   # id → accumulated content
    hitl_data = None

    for ev, data in sse_events(resp):
        if ev == "metadata":
            info(f"run_id = {data.get('run_id','?')[:12]}…")

        elif ev == "messages":
            mid  = data.get("id", "_")
            raw  = data.get("content", "")
            text = (
                "".join(
                    p.get("text", "") if isinstance(p, dict) else str(p)
                    for p in raw
                )
                if isinstance(raw, list) else str(raw)
            )
            if data.get("delta"):
                msg_buf[mid] = msg_buf.get(mid, "") + text
            else:
                msg_buf[mid] = text

        elif ev == "tool_calls":
            # Flush any accumulated message first
            for mid, content in list(msg_buf.items()):
                if content.strip():
                    for line in textwrap.wrap(content.strip(), W):
                        print(f"  {c('37', line)}")
                msg_buf[mid] = ""
            name = data.get("name") or data.get("tool") or "?"
            tool_start(name)

        elif ev == "tool_results":
            tool_done(data.get("content", ""))

        elif ev == "hitl":
            # Flush messages
            for content in msg_buf.values():
                if content.strip():
                    for line in textwrap.wrap(content.strip(), W):
                        print(f"  {c('37', line)}")
            hitl_box(data.get("tool", "?"), data.get("question", ""))
            hitl_data = data

        elif ev == "error":
            msg = data.get("message", "Unknown error")
            for line in msg.splitlines():
                err(line)

        elif ev == "end":
            # Flush remaining message content
            for content in msg_buf.values():
                if content.strip():
                    for line in textwrap.wrap(content.strip(), W):
                        print(f"  {c('37', line)}")
            ok("Run complete")

    return hitl_data


# ── Main ──────────────────────────────────────────────────────────────────────

# 1. Create thread
hdr("Creating thread")
r = requests.post(f"{BASE}/api/threads", json={"project_name": "EC_Carpet", "language": "vi"})
r.raise_for_status()
tid = r.json()["thread_id"]
ok(f"thread_id = {tid}")

# 2. Upload file
hdr("Uploading EC_Carpet.md")
with open(FILE, "rb") as f:
    r = requests.post(
        f"{BASE}/api/threads/{tid}/uploads",
        files=[("files", ("EC_Carpet.md", f, "text/markdown"))],
    )
r.raise_for_status()
ok(f"saved → {r.json()['uploaded'][0]}")

# 3. First run — skip solution, go straight to WBS
MSG = (
    "skip solution. "
    "Đọc file yêu cầu trong /input/ và gọi ngay run_wbs_workflow "
    "để tạo WBS Excel. Project code: EC_CARPET, ngôn ngữ: tiếng Việt."
)
hdr("Starting run (skip solution → WBS)")
info(f"message: {MSG[:80]}…")

with requests.post(
    f"{BASE}/api/threads/{tid}/runs/stream",
    json={"message": MSG},
    stream=True, timeout=300,
) as resp:
    hitl = consume(resp, "run")

# 4. Interactive HITL rounds
def hitl_prompt(tool: str) -> tuple[str, str | None]:
    """Ask user for approve / reject / custom feedback. Returns (decision, feedback)."""
    bar = c("1;33", "─" * 58)
    print(f"\n  {bar}")
    print(f"  {c('1;33', '  Nhập phản hồi của bạn:')}")
    print(f"  {c('33',   '  [Enter]         → approve (tiếp tục)')}")
    print(f"  {c('33',   '  r / reject       → từ chối')}")
    print(f"  {c('33',   '  <text bất kỳ>   → approve kèm ghi chú cho agent')}")
    print(f"  {bar}")
    try:
        raw = input(f"  {c('1;37', '▶ ')}").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return "approve", None

    if raw.lower() in ("r", "reject"):
        try:
            msg = input(f"  {c('33', 'Lý do từ chối: ')}").strip()
        except (EOFError, KeyboardInterrupt):
            msg = "User rejected"
        return "reject", msg or "User rejected"
    elif raw:
        return "approve", raw
    else:
        return "approve", None


round_n = 0
while hitl:
    round_n += 1
    tool = hitl.get("tool", "?")
    hdr(f"HITL #{round_n}: {tool}")

    decision, feedback = hitl_prompt(tool)
    payload: dict = {"decision": decision}
    if feedback:
        payload["edited_args"] = {"feedback": feedback}

    info(f"decision={decision}" + (f'  feedback="{feedback[:60]}…"' if feedback and len(feedback) > 60 else (f'  feedback="{feedback}"' if feedback else "")))

    with requests.post(
        f"{BASE}/api/threads/{tid}/runs/resume",
        json=payload,
        stream=True, timeout=300,
    ) as resp:
        try:
            hitl = consume(resp, f"resume-{round_n}")
        except requests.HTTPError as e:
            err(str(e))
            break

    if round_n >= 10:
        warn("Too many HITL rounds — stopping")
        break

# 5. List outputs
hdr("Output files")
r = requests.get(f"{BASE}/api/threads/{tid}/outputs")
if r.ok:
    artifacts = r.json().get("artifacts", r.json().get("files", []))
    if artifacts:
        for f in artifacts:
            name = f.get("name", f) if isinstance(f, dict) else f
            size = f" ({f['size_kb']} KB)" if isinstance(f, dict) and "size_kb" in f else ""
            ok(f"{name}{size}")
    else:
        warn("No output files yet")
else:
    warn(f"Could not list outputs ({r.status_code})")

print(f"\n{c('1;32', '✓ Done')}  thread = {tid}\n")
