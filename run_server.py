#!/usr/bin/env python3
"""Entry point for running the MCP web server with guarded stdio input."""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from io import TextIOWrapper
from typing import AsyncIterator, Literal

import anyio
import anyio.lowlevel
import mcp.types as mcp_types
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp.shared.message import SessionMessage

from mcp_web_server.server import mcp

logger = logging.getLogger("mcp_web_server.run_server")
InvalidInputPolicy = Literal["ignore", "warn", "strict"]


class InvalidJSONRPCLineError(ValueError):
    """Raised when strict mode rejects malformed JSON-RPC input."""


def _resolve_invalid_input_policy() -> InvalidInputPolicy:
    """
    Resolve malformed-input policy from env.

    MCP_STDIN_INVALID_INPUT_POLICY supports:
    - ignore: drop malformed lines silently
    - warn: drop malformed lines and log warning (default)
    - strict: fail fast on malformed lines
    """
    raw = os.getenv("MCP_STDIN_INVALID_INPUT_POLICY", "warn").strip().lower()
    if raw in {"ignore", "warn", "strict"}:
        return raw
    logger.warning(
        "Unknown MCP_STDIN_INVALID_INPUT_POLICY=%r, fallback to 'warn'.",
        raw,
    )
    return "warn"


def _parse_jsonrpc_line(
    line: str, invalid_policy: InvalidInputPolicy = "warn"
) -> mcp_types.JSONRPCMessage | None:
    """Parse one JSON-RPC line, returning None for ignorable input."""
    if not line.strip():
        return None
    try:
        return mcp_types.JSONRPCMessage.model_validate_json(line)
    except Exception as exc:
        if invalid_policy == "ignore":
            return None
        if invalid_policy == "warn":
            logger.warning("Ignore invalid JSON-RPC line from stdin: %s", exc)
            return None
        raise InvalidJSONRPCLineError(f"Invalid JSON-RPC line: {exc}") from exc
    return None


def _build_strict_input_hint(line: str) -> str:
    """Build an actionable error hint for strict mode."""
    preview = line.strip()
    if len(preview) > 120:
        preview = preview[:117] + "..."
    return (
        "Malformed JSON-RPC input received in strict mode. "
        "Check client/proxy stdin writes. "
        f"Line preview: {preview!r}"
    )


@asynccontextmanager
async def _safe_stdio_server(
    stdin: anyio.AsyncFile[str] | None = None,
    stdout: anyio.AsyncFile[str] | None = None,
) -> AsyncIterator[
    tuple[MemoryObjectReceiveStream[SessionMessage], MemoryObjectSendStream[SessionMessage]]
]:
    """
    Stdio transport with defensive input handling.

    - Ignore blank lines.
    - Ignore malformed JSON-RPC lines instead of surfacing internal errors.
    """
    invalid_policy = _resolve_invalid_input_policy()
    if stdin is None:
        stdin = anyio.wrap_file(TextIOWrapper(sys.stdin.buffer, encoding="utf-8"))
    if stdout is None:
        stdout = anyio.wrap_file(TextIOWrapper(sys.stdout.buffer, encoding="utf-8"))

    read_stream_writer, read_stream = anyio.create_memory_object_stream[SessionMessage](0)
    write_stream, write_stream_reader = anyio.create_memory_object_stream[SessionMessage](0)

    async def stdin_reader() -> None:
        last_line = ""
        try:
            async with read_stream_writer:
                async for line in stdin:
                    last_line = line
                    message = _parse_jsonrpc_line(line, invalid_policy=invalid_policy)
                    if message is None:
                        continue
                    await read_stream_writer.send(SessionMessage(message))
        except InvalidJSONRPCLineError:
            logger.error(_build_strict_input_hint(last_line))
            raise
        except anyio.ClosedResourceError:  # pragma: no cover
            await anyio.lowlevel.checkpoint()

    async def stdout_writer() -> None:
        try:
            async with write_stream_reader:
                async for session_message in write_stream_reader:
                    json_line = session_message.message.model_dump_json(
                        by_alias=True, exclude_none=True
                    )
                    await stdout.write(json_line + "\n")
                    await stdout.flush()
        except anyio.ClosedResourceError:  # pragma: no cover
            await anyio.lowlevel.checkpoint()

    async with anyio.create_task_group() as tg:
        tg.start_soon(stdin_reader)
        tg.start_soon(stdout_writer)
        yield read_stream, write_stream


async def _run_stdio_with_guard() -> None:
    async with _safe_stdio_server() as (read_stream, write_stream):
        await mcp._mcp_server.run(  # noqa: SLF001 - FastMCP does not expose this hook publicly.
            read_stream,
            write_stream,
            mcp._mcp_server.create_initialization_options(),
        )


def main() -> None:
    anyio.run(_run_stdio_with_guard)


if __name__ == "__main__":
    main()
