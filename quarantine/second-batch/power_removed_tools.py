"""Archived v0.4 power MCP tools, out of the v0.5 package.

These handlers called helper scripts that are not shipped in this
repository. They are kept here for a later batch, once they can land
with tests. Not imported by power/server.py.

Removidas até virem com testes.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]


def _run_json(cmd: list[str], timeout: int = 90) -> dict:
    try:
        p = subprocess.run(
            cmd, check=False, capture_output=True, text=True, timeout=timeout, cwd=str(WS)
        )
        text = (p.stdout or "").strip()
        if not text:
            return {"ok": p.returncode == 0, "rc": p.returncode, "stderr": (p.stderr or "")[-400:]}
        import json
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


REMOVED_TOOLS = [
    "power.fts_status",     # tools/organism_fts.py
    "power.fts_search",     # tools/organism_fts.py
    "power.recall",         # tools/organism_recall.py
    "power.personal_lab",   # tools/personal_lab_progress.py
    "power.open_loops",     # tools/open_loops_scan.py --write
    "power.night_watch",    # tools/night_watch_pass.py
    "power.proceed",        # tools/organism_proceed.py
    "power.ocarina_e2e",    # tools/ocarina_e2e_demo.py
    "power.system_test",    # tools/system_test_battery.py (also lives beside this file)
]

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
