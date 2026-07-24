#!/usr/bin/env python3
"""Minimal MCP stdio server for organism-continuity tools (no pip SDK required).

Implements enough JSON-RPC over stdin/stdout for hosts that speak MCP tools/list
and tools/call. Handlers reuse server.py.

Run:
  python3 tools/mcp_organism_continuity/stdio_server.py

Claude Desktop / Cursor-style config example (local):
  "organism-continuity": {
    "command": "python3",
    "args": ["/path/to/workspace/tools/mcp_organism_continuity/stdio_server.py"]
  }

Safety: read-mostly; no secrets; no remote code execution.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Local import
sys.path.insert(0, str(Path(__file__).resolve().parent))
from server import HANDLERS, TOOLS, mcp_manifest  # noqa: E402


def _read_message() -> dict | None:
    """Read one LSP/MCP-style Content-Length framed message, or one JSON line."""
    header = b""
    while True:
        ch = sys.stdin.buffer.read(1)
        if not ch:
            return None
        header += ch
        if header.endswith(b"\r\n\r\n"):
            break
        # Fallback: pure JSON line (no framing) for simple tests
        if header.endswith(b"\n") and b"Content-Length" not in header:
            line = header.decode("utf-8", errors="replace").strip()
            if not line:
                header = b""
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                header = b""
                continue
    # parse headers
    length = 0
    for line in header.decode("utf-8", errors="replace").split("\r\n"):
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
    body = sys.stdin.buffer.read(length) if length else b""
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def _write_message(msg: dict) -> None:
    body = json.dumps(msg, ensure_ascii=False, default=str).encode("utf-8")
    sys.stdout.buffer.write(
        f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
    )
    sys.stdout.buffer.flush()


def _tool_list() -> list[dict]:
    return [
        {
            "name": name,
            "description": meta["description"],
            "inputSchema": meta.get("inputSchema") or {"type": "object", "properties": {}},
        }
        for name, meta in TOOLS.items()
    ]


def _handle(req: dict) -> dict | None:
    mid = req.get("id")
    method = req.get("method") or ""
    params = req.get("params") or {}

    def result(payload: dict | list | str) -> dict:
        return {"jsonrpc": "2.0", "id": mid, "result": payload}

    def error(code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}

    if method == "initialize":
        return result(
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "organism-continuity",
                    "version": "0.1.0",
                },
            }
        )
    if method == "notifications/initialized":
        return None  # notification
    if method == "tools/list":
        return result({"tools": _tool_list()})
    if method == "tools/call":
        name = params.get("name") or ""
        fn = HANDLERS.get(name)
        if not fn:
            return error(-32601, f"unknown tool: {name}")
        try:
            out = fn()
            text = json.dumps(out, ensure_ascii=False, default=str, indent=2)
            return result(
                {
                    "content": [{"type": "text", "text": text}],
                    "isError": not bool(out.get("ok", True)) if isinstance(out, dict) else False,
                }
            )
        except Exception as exc:  # noqa: BLE001
            return result(
                {
                    "content": [{"type": "text", "text": f"error: {exc}"}],
                    "isError": True,
                }
            )
    if method == "ping":
        return result({})
    if method in ("resources/list", "prompts/list"):
        return result({method.split("/")[0]: []})
    # allow host to fetch manifest as a pseudo-tool via custom method
    if method == "organism/manifest":
        return result(mcp_manifest())
    if mid is None:
        return None
    return error(-32601, f"method not found: {method}")


def main() -> int:
    while True:
        try:
            req = _read_message()
        except (json.JSONDecodeError, ValueError) as exc:
            _write_message(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"parse error: {exc}"},
                }
            )
            continue
        if req is None:
            break
        resp = _handle(req)
        if resp is not None:
            _write_message(resp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
