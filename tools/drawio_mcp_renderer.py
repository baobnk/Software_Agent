"""Draw.io MCP-based PNG renderer — direct tool calls, no ReAct agent.

Uses: mcp.client.stdio → ClientSession → direct call_tool() in order:
  1. start_session  (required — starts embedded HTTP server + browser tab)
  2. create_new_diagram
  3. export_diagram (drawio)
  4. export_diagram (png)
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import os
from pathlib import Path

from loguru import logger as _log

_log = _log.bind(ctx="drawio_mcp")

_MCP_COMMAND = "node"
_MCP_ARGS    = [
    str(Path(__file__).parent.parent / "node_modules" /
        "@next-ai-drawio" / "mcp-server" / "dist" / "index.js")
]


async def _export_async(xml: str, drawio_path: Path, png_path: Path) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server = StdioServerParameters(
        command=_MCP_COMMAND,
        args=_MCP_ARGS,
        env=dict(os.environ),
    )
    _log.info(f"Starting MCP server: {_MCP_COMMAND} {' '.join(_MCP_ARGS)}")

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            _log.debug("MCP session initialized")

            _log.info("Calling start_session...")
            r0 = await session.call_tool("start_session", {})
            _log.info(f"start_session: {str(r0.content)[:120]}")

            _log.info("Calling create_new_diagram...")
            r1 = await session.call_tool("create_new_diagram", {"xml": xml})
            _log.info(f"create_new_diagram: {str(r1.content)[:120]}")

            _log.info(f"Calling export_diagram → {drawio_path.name} (drawio)...")
            r2 = await session.call_tool(
                "export_diagram",
                {"path": str(drawio_path), "format": "drawio"},
            )
            _log.info(f"export drawio: {str(r2.content)[:120]}")

            _log.info(f"Calling export_diagram → {png_path.name} (png)...")
            r3 = await session.call_tool(
                "export_diagram",
                {"path": str(png_path), "format": "png"},
            )
            _log.info(f"export png: {str(r3.content)[:120]}")


def _unwrap_exception(exc: BaseException) -> str:
    """Return the real error message, unwrapping ExceptionGroup/TaskGroup wrappers."""
    if hasattr(exc, "exceptions") and exc.exceptions:  # type: ignore[union-attr]
        parts = [_unwrap_exception(e) for e in exc.exceptions]  # type: ignore[union-attr]
        return " | ".join(parts)
    cause = exc.__cause__ or exc.__context__
    if cause and str(cause) and str(cause) != str(exc):
        return f"{exc}: caused by → {_unwrap_exception(cause)}"
    return str(exc)


def _run_in_thread(coro) -> None:
    """Run coroutine in a fresh event loop on a worker thread — safe even inside FastAPI."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        future.result()


def render_to_png_via_mcp(
    xml: str,
    drawio_path: Path,
    png_path: Path,
) -> str | None:
    """Export mxGraph XML to .drawio + .png via the drawio MCP server.

    Returns None on success, error message string on failure.
    """
    _log.info(f"[MCP] export start → {png_path.name}")
    try:
        _run_in_thread(_export_async(xml, drawio_path, png_path))
    except Exception as exc:
        real_err = _unwrap_exception(exc)
        _log.warning(f"[MCP] export failed (real cause): {real_err}")
        return real_err

    if not png_path.exists():
        msg = "MCP agent completed but PNG file not found on disk"
        _log.warning(f"[MCP] {msg}")
        return msg

    _log.success(f"[MCP] export OK → {png_path}  ({png_path.stat().st_size:,} bytes)")
    return None
