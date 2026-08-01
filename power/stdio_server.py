#!/usr/bin/env python3
"""Minimal MCP stdio server for organism-power tools (no pip SDK)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from server import HANDLERS, TOOLS, mcp_manifest  # noqa: E402


def _read_message() -> dict | None:
    header = b""
    while True:
        ch = sys.stdin.buffer.read(1)
        if not ch:
            return None
        header += ch
        if header.endswith(b"\r\n\r\n"):
            break
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


def _call_tool(name: str, arguments: dict | None) -> dict:
    fn = HANDLERS.get(name)
    if not fn:
        return {"ok": False, "error": f"unknown tool {name}"}
    args = arguments or {}
    try:
        return fn(**args)
    except TypeError:
        return fn()


def main() -> int:
    while True:
        msg = _read_message()
        if msg is None:
            break
        mid = msg.get("id")
        method = msg.get("method")
        if method == "initialize":
            _write_message(
                {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "organism-power", "version": "0.1.0"},
                    },
                }
            )
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            _write_message({"jsonrpc": "2.0", "id": mid, "result": {"tools": _tool_list()}})
        elif method == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name") or ""
            result = _call_tool(name, params.get("arguments"))
            text = json.dumps(result, ensure_ascii=False, default=str)
            _write_message(
                {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "result": {
                        "content": [{"type": "text", "text": text}],
                        "isError": not bool(result.get("ok", True)),
                    },
                }
            )
        elif method == "ping":
            _write_message({"jsonrpc": "2.0", "id": mid, "result": {}})
        else:
            if mid is not None:
                _write_message(
                    {
                        "jsonrpc": "2.0",
                        "id": mid,
                        "error": {"code": -32601, "message": f"Method not found: {method}"},
                    }
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
