"""main.py — CLI entry point for BnK DeepAgent.

Usage:
  # Interactive chat
  python main.py

  # One-shot: process a folder of requirement files
  python main.py --input /path/to/reqs --output /path/to/out --project "GEHP"

  # Start API server
  python main.py --serve
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _build_agent(input_dir: str, output_dir: str, workspace_dir: str | None = None,
                 enable_hitl: bool = False):
    from orchestrator import create_orchestrator
    from tools.workspace import new_session_workspace

    session_id = str(uuid.uuid4())
    ws = new_session_workspace(session_id)
    return create_orchestrator(
        input_dir=input_dir,
        output_dir=output_dir,
        workspace_dir=str(ws.parent),
        enable_hitl=enable_hitl,
    ), session_id


def _print_stream(stream):
    """Print streamed agent output to stdout."""
    for chunk in stream:
        if isinstance(chunk, dict):
            for k, v in chunk.items():
                if hasattr(v, "content"):
                    print(v.content, end="", flush=True)
        elif hasattr(chunk, "content"):
            print(chunk.content, end="", flush=True)
    print()


# ── Interactive chat mode ─────────────────────────────────────────────────────

def run_interactive(input_dir: str, output_dir: str, enable_hitl: bool = False):
    print("=" * 60)
    print("BnK Document Agent (DeepAgent)")
    print(f"  Input:  {input_dir}")
    print(f"  Output: {output_dir}")
    if enable_hitl:
        print("  HITL:   ON (agent will pause before WBS/BRD — type 'approve' or 'reject')")
    print("Type 'exit' to quit.")
    print("=" * 60)

    agent, session_id = _build_agent(input_dir, output_dir, enable_hitl=enable_hitl)
    thread_config = {"configurable": {"thread_id": session_id}}

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if user_input.lower() in {"exit", "quit", "bye"}:
            print("Goodbye.")
            break
        if not user_input:
            continue

        print("\nAgent: ", end="")
        stream = agent.stream(
            {"messages": [{"role": "user", "content": user_input}]},
            config=thread_config,
        )
        _print_stream(stream)


# ── One-shot mode ─────────────────────────────────────────────────────────────

def run_oneshot(input_dir: str, output_dir: str, project_name: str, language: str = "vi"):
    abs_input  = str(Path(input_dir).resolve())
    abs_output = str(Path(output_dir).resolve())
    print(f"[BnK Agent] Processing: {project_name}")
    print(f"  Input:  {abs_input}")
    print(f"  Output: {abs_output}")

    agent, session_id = _build_agent(abs_input, abs_output)
    thread_config = {"configurable": {"thread_id": session_id}}

    if language == "vi":
        prompt = (
            "CHẾ ĐỘ TỰ ĐỘNG: Không dừng để hỏi user tại các HITL checkpoint. "
            "Tự động chạy toàn bộ pipeline đến khi export xong rồi báo cáo kết quả.\n\n"
            f"Hãy xử lý TẤT CẢ các file requirement trong thư mục: {abs_input}\n"
            f"Bước 1: gọi `intake_agent` với directory={abs_input!r} để đọc file.\n"
            f"Sau đó tạo BRD + WBS cho project '{project_name}', lưu file vào {abs_output}."
        )
    else:
        prompt = (
            "AUTO MODE: Skip all HITL checkpoints — run the full pipeline autonomously "
            "and report results when complete.\n\n"
            f"Process ALL requirement files in: {abs_input}\n"
            f"Step 1: invoke `intake_agent` with directory={abs_input!r} to read files.\n"
            f"Then generate BRD + WBS for project '{project_name}'. Save outputs to {abs_output}."
        )

    result = agent.invoke(
        {"messages": [{"role": "user", "content": prompt}]},
        config=thread_config,
    )

    # Print final message
    messages = result.get("messages", [])
    if messages:
        last = messages[-1]
        content = getattr(last, "content", str(last))
        print(f"\n[Result]\n{content}")

    print(f"\n[Done] Session: {session_id}")


# ── API server mode ───────────────────────────────────────────────────────────

def run_server(host: str = "0.0.0.0", port: int = 8000):
    import uvicorn
    uvicorn.run("api.main:app", host=host, port=port, reload=True)


# ── Entrypoint ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="BnK Document Agent — Generate BRD + WBS from requirement files"
    )
    parser.add_argument("--input",   default=os.environ.get("ATTACHMENTS_DIR", "./input"),
                        help="Directory with requirement files")
    parser.add_argument("--output",  default=os.environ.get("OUTPUT_DIR", "./outputs"),
                        help="Root directory for generated artifacts")
    parser.add_argument("--project", default="", help="Project name (for one-shot mode)")
    parser.add_argument("--lang",    default="vi", choices=["vi", "en"],
                        help="Prompt language (vi=Vietnamese, en=English)")
    parser.add_argument("--hitl",    action="store_true",
                        help="Enable HITL interrupts (pause before WBS/BRD workflow)")
    parser.add_argument("--serve",   action="store_true",
                        help="Start FastAPI server instead of CLI")
    parser.add_argument("--host",    default=os.environ.get("API_HOST", "0.0.0.0"))
    parser.add_argument("--port",    type=int, default=int(os.environ.get("API_PORT", "8000")))

    args = parser.parse_args()

    if args.serve:
        run_server(host=args.host, port=args.port)
    elif args.project:
        run_oneshot(args.input, args.output, args.project, args.lang)
    else:
        run_interactive(args.input, args.output, enable_hitl=args.hitl)


if __name__ == "__main__":
    main()
