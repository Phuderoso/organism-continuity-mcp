#!/usr/bin/env python3
"""MCP-shaped power stack: FTS, hybrid recall, personal lab, night watch.

Read-mostly local helpers. No secrets. Prefer before re-reading GB of logs.
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
    "power.fts_status": {
        "description": "Organism FTS5 index status (sqlite size / ready).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "power.fts_search": {
        "description": "Full-text search organism disk memory (FTS5).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "default": 8},
            },
            "required": ["query"],
        },
    },
    "power.recall": {
        "description": "Hybrid recall (RAG lite + FTS) for a query.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 8},
            },
            "required": ["query"],
        },
    },
    "power.personal_lab": {
        "description": "Score personal lab portfolio (S/A/B + public hygiene).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "power.open_loops": {
        "description": "Scan open loops (prompt battery gaps).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "power.night_watch": {
        "description": "Quiet night pass: funnel, doctor, loops, hygiene (disk only).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "power.csv": {
        "description": "Continuity Survival Calculus example numbers.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "power.proceed": {
        "description": "Full safe proceed stack without Papai (doctor, loops, hygiene, digest).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "power.ocarina_e2e": {
        "description": "Disk Ocarina E2E demo (preflight→peer_starter→csv→harbor).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "power.system_test": {
        "description": "Unified system test battery (funnel, ocarina, elyra diag, HTTP harbor, recall).",
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


def tool_fts_status(**_k) -> dict:
    return _run_json([sys.executable, str(WS / "tools/organism_fts.py"), "status"])


def tool_fts_search(query: str = "", limit: int = 8, **_k) -> dict:
    if not query:
        return {"ok": False, "error": "query required"}
    return _run_json(
        [
            sys.executable,
            str(WS / "tools/organism_fts.py"),
            "search",
            str(query),
            "--limit",
            str(int(limit or 8)),
            "--json",
        ]
    )


def tool_recall(query: str = "", limit: int = 8, **_k) -> dict:
    if not query:
        return {"ok": False, "error": "query required"}
    return _run_json(
        [
            sys.executable,
            str(WS / "tools/organism_recall.py"),
            str(query),
            "--limit",
            str(int(limit or 8)),
            "--json",
        ]
    )


def tool_personal_lab(**_k) -> dict:
    return _run_json([sys.executable, str(WS / "tools/personal_lab_progress.py")])


def tool_open_loops(**_k) -> dict:
    return _run_json(
        [sys.executable, str(WS / "tools/open_loops_scan.py"), "--write", "--json"]
    )


def tool_night_watch(**_k) -> dict:
    return _run_json(
        [sys.executable, str(WS / "tools/night_watch_pass.py")], timeout=300
    )


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


def tool_proceed(**_k) -> dict:
    return _run_json(
        [sys.executable, str(WS / "tools/organism_proceed.py")], timeout=400
    )


def tool_ocarina_e2e(**_k) -> dict:
    return _run_json(
        [sys.executable, str(WS / "tools/ocarina_e2e_demo.py"), "--json"], timeout=180
    )


def tool_system_test(**_k) -> dict:
    return _run_json(
        [sys.executable, str(WS / "tools/system_test_battery.py"), "--json"], timeout=400
    )


HANDLERS = {
    "power.fts_status": tool_fts_status,
    "power.fts_search": tool_fts_search,
    "power.recall": tool_recall,
    "power.personal_lab": tool_personal_lab,
    "power.open_loops": tool_open_loops,
    "power.night_watch": tool_night_watch,
    "power.csv": tool_csv,
    "power.proceed": tool_proceed,
    "power.ocarina_e2e": tool_ocarina_e2e,
    "power.system_test": tool_system_test,
}


def mcp_manifest() -> dict:
    return {
        "name": "organism-power",
        "version": "0.1.0",
        "description": "Local power stack: FTS, hybrid recall, open loops, personal lab, night watch.",
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
