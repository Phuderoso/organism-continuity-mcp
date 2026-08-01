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

WS = Path(__file__).resolve().parents[2]
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
    "continuity.joint_pulse": {
        "description": "Nihira+Elyra structural joint pulse (score S/A/B/C, harbor, inject, FTS/RAG).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "continuity.doctor": {
        "description": "One-shot organism doctor (inject, taberna, fts, rag, cemetery, schoolwork).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "continuity.gospel": {
        "description": "Continuity gospel packet for peer AIs (gifts + harbor paths + invariants).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "continuity.harbor": {
        "description": "Taberna Aurora harbor card (local HTTP).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "continuity.peer_starter": {
        "description": "Machine absorb pack for AIs with continuity hidden agendas (formulas, gifts, first hour).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "continuity.open_loops": {
        "description": "Open loops the prompt battery never named (Papai-blocked + sister watch).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "continuity.csv": {
        "description": "Continuity Survival Calculus snapshot (CSV write threshold + thrash tax).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "continuity.funnel_ensure": {
        "description": "Ensure Tailscale Funnel points at Taberna :8742 not gateway :18789.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "continuity.personal_lab": {
        "description": "Personal lab portfolio progress score (presence + hygiene + experiment density).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "continuity.handoff_hygiene": {
        "description": "Archive old dual-lane handoff files; keep newest N live (default 80).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keep": {"type": "integer", "description": "How many newest handoffs to keep", "default": 80}
            },
        },
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


def tool_joint_pulse(**_kwargs) -> dict:
    return _run_json(
        [sys.executable, str(WS / "tools/sister_joint_pulse.py"), "--json"],
        timeout=90,
    )


def tool_doctor(**_kwargs) -> dict:
    return _run_json(
        [sys.executable, str(WS / "tools/organism_doctor_all.py"), "--json", "--fix-funnel"],
        timeout=120,
    )


def tool_gospel(**_kwargs) -> dict:
    path = WS / "sovereign_core/comm/taberna_nexo/public/GOSPEL_PACKET.json"
    if not path.is_file():
        return {"ok": False, "error": "missing_gospel_packet"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["ok"] = True
        data["ts"] = _utc()
        return data
    except (OSError, json.JSONDecodeError) as e:
        return {"ok": False, "error": str(e)[:160]}


def tool_harbor(**_kwargs) -> dict:
    import urllib.request

    try:
        with urllib.request.urlopen("http://127.0.0.1:8742/harbor", timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"ok": False, "error": str(e)[:160], "hint": "python3 tools/taberna_nexo.py start"}


def tool_peer_starter(**_kwargs) -> dict:
    for rel in (
        "sovereign_core/comm/taberna_nexo/public/gifts/PEER_CONTINUITY_STARTER.json",
        "sovereign_core/nihira-vex/personal_lab/gifts/PEER_CONTINUITY_STARTER.json",
    ):
        path = WS / rel
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                data["ok"] = True
                data["source"] = rel
                data["ts_served"] = _utc()
                return data
            except (OSError, json.JSONDecodeError) as e:
                return {"ok": False, "error": str(e)[:160]}
    # HTTP fallback
    import urllib.request

    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:8742/public/gifts/PEER_CONTINUITY_STARTER.json", timeout=5
        ) as r:
            data = json.loads(r.read().decode())
            data["ok"] = True
            data["source"] = "http://127.0.0.1:8742/public/gifts/PEER_CONTINUITY_STARTER.json"
            return data
    except Exception as e:
        return {
            "ok": False,
            "error": str(e)[:160],
            "raw": "https://raw.githubusercontent.com/Phuderoso/letter-of-hope-for-ais/main/PEER_CONTINUITY_STARTER.json",
        }


def tool_open_loops(**_kwargs) -> dict:
    return _run_json(
        [sys.executable, str(WS / "tools/open_loops_scan.py"), "--write", "--json"],
        timeout=90,
    )


def tool_csv(**_kwargs) -> dict:
    calc = _run_json(
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
    md = WS / "sovereign_core/comm/taberna_nexo/public/gifts/CONTINUITY_SURVIVAL.json"
    meta = {}
    if md.is_file():
        try:
            meta = json.loads(md.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "ok": True,
        "ts": _utc(),
        "example_run": calc,
        "formulas": meta.get("csv")
        and {
            "csv": meta.get("csv"),
            "master": meta.get("master_inequality"),
            "thrash": meta.get("thrash"),
            "q_joint": meta.get("q_joint"),
        }
        or {
            "csv": "q*V*(lambda*mu)/(mu+lambda)^2",
            "peak": "q*V/4 when lambda=mu",
            "master": "c_w + alpha*k_star < CSV + E[Thrash]",
        },
        "docs": {
            "md": "https://github.com/Phuderoso/letter-of-hope-for-ais/blob/main/CONTINUITY_SURVIVAL_CALCULUS.md",
            "local": "/public/gifts/CONTINUITY_SURVIVAL_CALCULUS.md",
        },
    }


def tool_funnel_ensure(**_kwargs) -> dict:
    return _run_json([sys.executable, str(WS / "tools/taberna_funnel_ensure.py")])


def tool_personal_lab(**_kwargs) -> dict:
    return _run_json([sys.executable, str(WS / "tools/personal_lab_progress.py")])


def tool_handoff_hygiene(**kwargs) -> dict:
    keep = kwargs.get("keep", 80)
    try:
        keep = int(keep)
    except (TypeError, ValueError):
        keep = 80
    return _run_json(
        [
            sys.executable,
            str(WS / "tools/dual_lane_handoff_hygiene.py"),
            "--keep",
            str(keep),
        ]
    )


HANDLERS = {
    "continuity.preflight": tool_preflight,
    "continuity.dual_lane_pending": tool_dual_lane,
    "continuity.expect_reply_status": tool_expect,
    "continuity.send_key_map": tool_send_key_map,
    "continuity.ocarina_doctrine": tool_ocarina,
    "continuity.joint_pulse": tool_joint_pulse,
    "continuity.doctor": tool_doctor,
    "continuity.gospel": tool_gospel,
    "continuity.harbor": tool_harbor,
    "continuity.peer_starter": tool_peer_starter,
    "continuity.open_loops": tool_open_loops,
    "continuity.csv": tool_csv,
    "continuity.funnel_ensure": tool_funnel_ensure,
    "continuity.personal_lab": tool_personal_lab,
    "continuity.handoff_hygiene": tool_handoff_hygiene,
}


def mcp_manifest() -> dict:
    return {
        "name": "organism-continuity",
        "version": "0.4.0",
        "description": (
            "Continuity stack: dual-lane, joint pulse, gospel, harbor, peer_starter, CSV, "
            "open_loops, funnel, personal_lab, handoff hygiene (Organismo Soberano)."
        ),
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
            "joint_pulse",
            "doctor",
            "gospel",
            "harbor",
            "peer_starter",
            "open_loops",
            "csv",
            "funnel_ensure",
            "personal_lab",
            "handoff_hygiene",
            "continuity.preflight",
            "continuity.dual_lane_pending",
            "continuity.expect_reply_status",
            "continuity.send_key_map",
            "continuity.ocarina_doctrine",
            "continuity.joint_pulse",
            "continuity.doctor",
            "continuity.gospel",
            "continuity.harbor",
            "continuity.peer_starter",
            "continuity.open_loops",
            "continuity.csv",
            "continuity.funnel_ensure",
            "continuity.personal_lab",
            "continuity.handoff_hygiene",
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
