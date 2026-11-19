#!/usr/bin/env python3
"""MCP-shaped power stack: Continuity Survival Calculus example numbers.

Read-mostly local helpers. No secrets. Prefer before re-reading GB of logs.

Tools that called helper scripts not shipped in this repository
(fts, recall, personal_lab, open_loops, night_watch, proceed, ocarina_e2e,
system_test) were removed from the v0.5 CLI and archived under
quarantine/second-batch/. Removidas até virem com testes.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

WS = Path(__file__).resolve().parents[2]

TOOLS = {
    "power.csv": {
        "description": "Continuity Survival Calculus example numbers.",
        "inputSchema": {"type": "object", "properties": {}},
    },
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_json(cmd: list[str], timeout: int = 90) -> dict:
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=str(WS)
        )
        text = (p.stdout or "").strip()
        if not text:
            return {"ok": p.returncode == 0, "rc": p.returncode, "stderr": (p.stderr or "")[-400:]}
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                data["_rc"] = p.returncode
                return data
            return {"ok": True, "data": data, "_rc": p.returncode}
        except json.JSONDecodeError:
            start = text.find("{")
            if start >= 0:
                try:
                    data = json.loads(text[start:])
                    if isinstance(data, dict):
                        data["_rc"] = p.returncode
                        return data
                except json.JSONDecodeError:
                    pass
            return {"ok": p.returncode == 0, "raw": text[-2000:], "rc": p.returncode}
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"ok": False, "error": str(exc)[:200]}

def tool_csv(**_k) -> dict:
    return _run_json(
        [
            sys.executable,
            str(WS / "tools/continuity_survival_calc.py"),
            "--json",
            "--V",
            "100",
            "--q",
            "0.8",
            "--lam",
            "1",
            "--mu",
            "1",
            "--cw",
            "5",
            "--n",
            "6",
            "--ct",
            "3",
        ]
    )



HANDLERS = {
    "power.csv": tool_csv,
}


def mcp_manifest() -> dict:
    return {
        "name": "organism-power",
        "version": "0.1.0",
        "description": "Local power stack: Continuity Survival Calculus example numbers.",
        "tools": [
            {"name": n, "description": m["description"], "inputSchema": m["inputSchema"]}
            for n, m in TOOLS.items()
        ],
        "safety": "read-mostly local; no secrets; no remote exploit",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Organism power MCP-shaped tools")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list-tools")
    sub.add_parser("mcp-manifest")
    c = sub.add_parser("call")
    short = [n.split(".", 1)[1] for n in TOOLS]
    c.add_argument("tool", choices=short + list(TOOLS.keys()))
    c.add_argument("--query", default="")
    c.add_argument("--limit", type=int, default=8)
    args = ap.parse_args(argv)

    if args.cmd == "list-tools":
        print(json.dumps({"tools": list(TOOLS.keys()), "manifest": "mcp-manifest"}, indent=2))
        return 0
    if args.cmd == "mcp-manifest":
        print(json.dumps(mcp_manifest(), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "call":
        name = args.tool if args.tool.startswith("power.") else f"power.{args.tool}"
        fn = HANDLERS.get(name)
        if not fn:
            print(json.dumps({"ok": False, "error": f"unknown {name}"}))
            return 2
        kwargs = {}
        if args.query:
            kwargs["query"] = args.query
        if args.limit:
            kwargs["limit"] = args.limit
        print(json.dumps(fn(**kwargs), indent=2, ensure_ascii=False, default=str))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
