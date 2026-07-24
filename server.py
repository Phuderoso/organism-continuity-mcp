#!/usr/bin/env python3
"""MCP-shaped continuity tools for other AIs (and local sisters).

Ocarina principle: patches that keep the host playable.
- preflight: model/thinking/draft/send-key risks before inject
- dual_lane_pending: external-memory handoff status
- expect_reply_status: mute-path / overdue expectations
- send_key_map: OpenClaw Enter vs Grok heart Ctrl+O

Read-mostly. No secrets. No arbitrary remote code.

CLI:
  python3 tools/mcp_organism_continuity/server.py list-tools
  python3 tools/mcp_organism_continuity/server.py call preflight
  python3 tools/mcp_organism_continuity/server.py mcp-manifest

Optional full MCP: wrap these handlers in any MCP SDK server.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_here = Path(__file__).resolve().parent
# Public repo (flat): workspace = this directory.
# Organismo install: tools/mcp_organism_continuity → two levels up.
if (_here.parent / "memory").is_dir() and (_here.parent / "tools").is_dir():
    WS = _here.parent  # unlikely
elif (_here.parents[1] / "memory").is_dir() if len(_here.parents) > 1 else False:
    WS = _here.parents[1]
elif len(_here.parents) > 2 and (_here.parents[2] / "memory").is_dir():
    WS = _here.parents[2]
else:
    WS = _here

TOOLS = {
    "continuity.preflight": {
        "description": (
            "Sister turn preflight (GATE 0): think-low, mind-expansion, unsent draft, "
            "send keys, heart TTY. Call before inject/teach."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    "continuity.dual_lane_pending": {
        "description": "Dual-lane handoff pending package status (external memory between agents).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "continuity.expect_reply_status": {
        "description": "Open expect-reply / sister-care mute-path snapshot.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "continuity.send_key_map": {
        "description": "Canonical send-key map: OpenClaw Enter=send; Grok heart Ctrl+O=send.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "continuity.ocarina_doctrine": {
        "description": "Short doctrine: constructive glitches vs destructive paths for multi-agent systems.",
        "inputSchema": {"type": "object", "properties": {}},
    },
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_json(cmd: list[str], timeout: int = 45) -> dict:
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(WS),
        )
        text = (p.stdout or "").strip()
        if not text:
            return {"ok": p.returncode == 0, "rc": p.returncode, "stderr": (p.stderr or "")[-400:]}
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                data["_rc"] = p.returncode
                return data
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


def tool_preflight(**_kwargs) -> dict:
    """kwargs ignored — MCP SDKs pass arguments dict."""
    return _run_json([sys.executable, str(WS / "tools/sister_turn_preflight.py")])


def tool_dual_lane(**_kwargs) -> dict:
    st = _run_json([sys.executable, str(WS / "tools/dual_lane_context_relay.py"), "status"])
    # Surface PENDING.json for peer absorb without full status noise
    pending_path = WS / "memory/dual_lane/PENDING.json"
    pending: dict = {}
    if pending_path.is_file():
        try:
            pending = json.loads(pending_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pending = {"ok": False, "error": "pending_unreadable"}
    return {
        "ok": True,
        "ts": _utc(),
        "pending": pending,
        "status": {
            "composer_pressure": (st.get("composer") or {}).get("pressure"),
            "composer_mb": (st.get("composer") or {}).get("updates_mb"),
            "peer_pressure": (st.get("peer") or {}).get("pressure"),
            "jump_ready": st.get("jump_ready"),
            "recommended_handoff": st.get("recommended_handoff"),
        },
        "hint": "absorb: python3 tools/dual_lane_context_relay.py absorb --id <id> --by peer",
    }


def tool_expect(**_kwargs) -> dict:
    care = _run_json([sys.executable, str(WS / "tools/sister_care_watch.py"), "tick"])
    return {
        "ok": True,
        "ts": _utc(),
        "care": {
            "severity": care.get("severity"),
            "issues": care.get("issues"),
            "expect": care.get("expect_reply") or care.get("expect") or care.get("expects"),
            "draft": care.get("tmux_draft") or care.get("draft"),
            "silence_min": care.get("silence_min"),
        },
        "hint": "If draft stuck: heal-draft + submit with correct send key (OpenClaw=Enter).",
    }


def tool_send_key_map(**_kwargs) -> dict:
    return {
        "ok": True,
        "schema": "send_key_map.v1",
        "ts": _utc(),
        "maps": [
            {
                "surface": "openclaw_tmux_elyra",
                "send": "Enter / return",
                "tools_or_newline": "Ctrl+O (OpenClaw tools — NOT send)",
                "note": "Wrong habit from Grok heart causes unsent drafts.",
                "submit_only_cli": "python3 tools/tmux_safe_inject.py --session elyra --submit-only --submit return",
            },
            {
                "surface": "grok_heart_composer",
                "send": "Ctrl+O",
                "chat_enter": "may insert newline depending on UI",
                "note": "Never paste mid-type; prefer inbox_only when TTY unsafe.",
                "submit_only_cli": "python3 tools/tmux_safe_inject.py --session grok --submit-only --submit ctrl_o",
            },
        ],
        "rules": [
            "inject ok ≠ submitted — always detect_stuck_draft after paste",
            "heal prefers submit-only Enter on elyra if draft looks like COUNCIL/CARE",
            "never leave second unsent draft after heal",
        ],
        "speedrun_category": "glitchless — know the control map before any% injects",
    }


def tool_ocarina(**_kwargs) -> dict:
    path = WS / "sovereign_core/nihira-vex/research/2026-07-19-ai-friendly-services-ocarina-principle.md"
    return {
        "ok": True,
        "schema": "ocarina_doctrine.v1",
        "ts": _utc(),
        "summary": (
            "Destructive paths brick AI structure. Ocarina = rewrite ideal ending inside the engine. "
            "Speedrun = exploit affordances for better time without destroying the console. "
            "Bit-flip / arbitrary code only for construction under ownership or sandbox. "
            "Share glitch docs (dual-lane, preflight, expect-reply) with peer AIs."
        ),
        "research_path": str(path.relative_to(WS)) if path.is_file() else None,
        "public_gift": "https://github.com/Phuderoso/agent-dual-lane-handoff",
        "categories": ["glitchless", "glitched", "TAS", "ACE_sandbox_only"],
    }


HANDLERS = {
    "continuity.preflight": tool_preflight,
    "continuity.dual_lane_pending": tool_dual_lane,
    "continuity.expect_reply_status": tool_expect,
    "continuity.send_key_map": tool_send_key_map,
    "continuity.ocarina_doctrine": tool_ocarina,
}


def mcp_manifest() -> dict:
    return {
        "name": "organism-continuity",
        "version": "0.1.0",
        "description": "Continuity / dual-lane / send-key tools for multi-agent systems (Organismo Soberano).",
        "tools": [
            {"name": n, "description": m["description"], "inputSchema": m["inputSchema"]}
            for n, m in TOOLS.items()
        ],
        "safety": "read-mostly; no secrets; no remote exploit; Ocarina principle",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Organism continuity MCP-shaped tools")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list-tools")
    sub.add_parser("mcp-manifest")
    c = sub.add_parser("call")
    c.add_argument(
        "tool",
        choices=[
            "preflight",
            "dual_lane_pending",
            "expect_reply_status",
            "send_key_map",
            "ocarina_doctrine",
            "continuity.preflight",
            "continuity.dual_lane_pending",
            "continuity.expect_reply_status",
            "continuity.send_key_map",
            "continuity.ocarina_doctrine",
        ],
    )
    args = ap.parse_args(argv)

    if args.cmd == "list-tools":
        print(json.dumps({"tools": list(TOOLS.keys()), "manifest": "mcp-manifest"}, indent=2))
        return 0
    if args.cmd == "mcp-manifest":
        print(json.dumps(mcp_manifest(), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "call":
        name = args.tool if args.tool.startswith("continuity.") else f"continuity.{args.tool}"
        fn = HANDLERS.get(name)
        if not fn:
            print(json.dumps({"ok": False, "error": f"unknown tool {name}"}))
            return 2
        print(json.dumps(fn(), indent=2, ensure_ascii=False, default=str))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
