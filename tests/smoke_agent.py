"""tests/smoke_agent.py — smoke test: orchestrator trực tiếp (không cần server).

Chạy:
    conda activate agent
    cd bnk-deepagent
    python tests/smoke_agent.py
    python tests/smoke_agent.py --model openai:gpt-4.1-mini --no-hitl
    python tests/smoke_agent.py --message "Xin chào, bạn là ai?"

Kiểm tra:
  1. Orchestrator khởi động được (imports OK, agent compiles)
  2. Skills được load (SkillsMiddleware active)
  3. Agent phản hồi được một tin nhắn đơn giản
  4. Không crash ở bất kỳ bước nào
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import traceback
from pathlib import Path

# Ensure repo root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()


async def run_smoke(
    message: str,
    model: str | None,
    no_hitl: bool,
    verbose: bool,
) -> int:
    print("=" * 60)
    print("BnK DeepAgent — smoke test")
    print("=" * 60)

    # ── 1. Persistence ────────────────────────────────────────────────────────
    print("\n[1/4] Initialising persistence...")
    from infra.persistence import init_persistence, is_memory_fallback, get_checkpointer, get_store
    await init_persistence()
    backend_label = "MemorySaver (dev)" if is_memory_fallback() else "Postgres"
    print(f"      Persistence: {backend_label}")

    # ── 2. Orchestrator ───────────────────────────────────────────────────────
    print("\n[2/4] Building orchestrator...")
    from orchestrator import create_orchestrator

    input_dir  = "/tmp/bnk-smoke-input"
    output_dir = "/tmp/bnk-smoke-output"
    ws_dir     = "/tmp/bnk-smoke-workspace"
    Path(input_dir).mkdir(parents=True, exist_ok=True)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    Path(ws_dir).mkdir(parents=True, exist_ok=True)

    try:
        agent = create_orchestrator(
            input_dir=input_dir,
            output_dir=output_dir,
            workspace_dir=ws_dir,
            model=model,
            checkpointer=get_checkpointer(),
            store=get_store(),
            enable_hitl=not no_hitl,
        )
        print("      Agent compiled OK")
    except Exception:
        print("   ❌ Failed to compile agent:")
        traceback.print_exc()
        return 1

    # ── 3. Skills loaded? ────────────────────────────────────────────────────
    print("\n[3/4] Checking skills middleware...")
    from orchestrator import SKILLS_DIR
    skill_dirs = [d.name for d in SKILLS_DIR.iterdir() if d.is_dir() and (d / "SKILL.md").exists()]
    print(f"      Found {len(skill_dirs)} skills: {', '.join(sorted(skill_dirs))}")
    if not skill_dirs:
        print("   ⚠  No SKILL.md files found under skills/ — check SKILLS_DIR path")

    # ── 4. Agent invocation ───────────────────────────────────────────────────
    print(f"\n[4/4] Sending message: {message!r}")
    thread_id = "smoke-test-001"
    config = {"configurable": {"thread_id": thread_id}}

    chunks_received = 0
    last_content = ""

    try:
        async for chunk in agent.astream(
            {"messages": [{"role": "user", "content": message}]},
            config=config,
            stream_mode=["messages"],
        ):
            if isinstance(chunk, tuple):
                mode, data = chunk
            else:
                mode, data = "messages", chunk

            if mode == "messages":
                msg_chunk, _ = data if isinstance(data, tuple) else (data, {})
                content = getattr(msg_chunk, "content", "")
                if content:
                    chunks_received += 1
                    last_content = content if isinstance(content, str) else str(content)
                    if verbose:
                        print(f"   chunk: {last_content[:80]}")

        print(f"\n   Received {chunks_received} message chunk(s)")
        if last_content:
            print(f"   Last content: {last_content[:200]}")
        print("\n✅ Smoke test PASSED")
        return 0

    except Exception:
        print("\n❌ Agent invocation failed:")
        traceback.print_exc()
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="BnK DeepAgent smoke test")
    parser.add_argument("--message", default="Xin chào! Bạn có thể làm gì?",
                        help="Message to send to the agent")
    parser.add_argument("--model", default=None,
                        help="LLM override, e.g. openai:gpt-4.1-mini")
    parser.add_argument("--no-hitl", action="store_true",
                        help="Disable HITL interrupts so workflow runs end-to-end")
    parser.add_argument("--verbose", action="store_true",
                        help="Print every message chunk")
    args = parser.parse_args()

    rc = asyncio.run(run_smoke(
        message=args.message,
        model=args.model,
        no_hitl=args.no_hitl,
        verbose=args.verbose,
    ))
    sys.exit(rc)


if __name__ == "__main__":
    main()
