"""tests/smoke_api.py — smoke test: API server end-to-end qua HTTP.

Yêu cầu: server đang chạy trên cổng 8000.
    conda activate agent
    python main.py --serve          # terminal 1
    python tests/smoke_api.py       # terminal 2

Kiểm tra:
  1. GET  /health           → status ok
  2. POST /api/threads      → tạo thread thành công
  3. GET  /api/threads/{id} → metadata trả về đúng
  4. POST /api/threads/{id}/runs/stream → nhận SSE events
  5. DELETE /api/threads/{id} → xoá thread
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import urllib.error
from typing import Any

BASE = "http://localhost:8000"


def req(method: str, path: str, body: dict | None = None) -> tuple[int, Any]:
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if data else {}
    rq = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(rq, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    except Exception as e:
        return 0, {"error": str(e)}


def stream_run(thread_id: str, message: str) -> list[dict]:
    """POST to /runs/stream and collect SSE events (non-streaming, reads full body)."""
    url = f"{BASE}/api/threads/{thread_id}/runs/stream"
    data = json.dumps({"message": message, "on_disconnect": "continue"}).encode()
    rq = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    events: list[dict] = []
    try:
        with urllib.request.urlopen(rq, timeout=120) as resp:
            for raw_line in resp:
                line = raw_line.decode().strip()
                if line.startswith("data:"):
                    try:
                        events.append(json.loads(line[5:].strip()))
                    except json.JSONDecodeError:
                        pass
    except urllib.error.HTTPError as e:
        events.append({"error": f"HTTP {e.code}: {e.read().decode()}"})
    except Exception as e:
        events.append({"error": str(e)})
    return events


def check(label: str, condition: bool, detail: str = "") -> bool:
    status = "✅" if condition else "❌"
    print(f"  {status} {label}" + (f"  — {detail}" if detail else ""))
    return condition


def main() -> None:
    parser = argparse.ArgumentParser(description="BnK API smoke test")
    parser.add_argument("--base", default=BASE, help="Server base URL")
    parser.add_argument("--message", default="Xin chào! Bạn có thể làm gì?")
    args = parser.parse_args()

    global BASE
    BASE = args.base

    all_ok = True
    print("=" * 60)
    print("BnK DeepAgent — API smoke test")
    print(f"Target: {BASE}")
    print("=" * 60)

    # ── 1. Health ─────────────────────────────────────────────────────────────
    print("\n[1/5] Health check")
    status, body = req("GET", "/health")
    ok = check("GET /health → 200", status == 200, str(body))
    ok &= check("status == ok", body.get("status") == "ok")
    all_ok &= ok

    # ── 2. Create thread ──────────────────────────────────────────────────────
    print("\n[2/5] Create thread")
    status, body = req("POST", "/api/threads", {
        "project_name": "smoke-test",
        "language": "vi",
    })
    ok = check("POST /api/threads → 200", status == 200, str(body))
    thread_id = body.get("thread_id", "")
    ok &= check("thread_id present", bool(thread_id), thread_id)
    all_ok &= ok

    if not thread_id:
        print("\n❌ Cannot proceed without thread_id")
        sys.exit(1)

    # ── 3. Get thread ─────────────────────────────────────────────────────────
    print(f"\n[3/5] Get thread {thread_id[:8]}...")
    status, body = req("GET", f"/api/threads/{thread_id}")
    ok = check("GET /api/threads/{id} → 200", status == 200)
    ok &= check("project_name matches", body.get("project_name") == "smoke-test")
    ok &= check("status field present", "status" in body, body.get("status", "missing"))
    all_ok &= ok

    # ── 4. Stream run ─────────────────────────────────────────────────────────
    print(f"\n[4/5] Stream run — message: {args.message!r}")
    events = stream_run(thread_id, args.message)
    event_types = [e.get("type") or list(e.keys())[0] if e else "" for e in events]
    print(f"      Received {len(events)} SSE event(s)")

    has_error = any("error" in e for e in events)
    has_messages = bool(events)
    ok = check("At least one SSE event received", has_messages, f"events: {len(events)}")
    ok &= check("No error events", not has_error,
                next((str(e) for e in events if "error" in e), ""))
    all_ok &= ok

    # ── 5. Delete thread ──────────────────────────────────────────────────────
    print(f"\n[5/5] Delete thread {thread_id[:8]}...")
    status, body = req("DELETE", f"/api/threads/{thread_id}")
    ok = check("DELETE /api/threads/{id} → 200", status == 200)
    all_ok &= ok

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    if all_ok:
        print("✅  All checks passed")
    else:
        print("❌  Some checks FAILED — see above")
    print("=" * 60)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
