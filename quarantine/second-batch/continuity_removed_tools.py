"""Archived v0.4 continuity MCP tools, out of the v0.5 package.

These handlers called helper scripts that are not shipped in this
repository (and, in the doctor/funnel cases, could change a Tailscale
Funnel). They are kept here for a later batch, once they can land with
tests. Not imported by server.py.

Removidas até virem com testes.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone

try:
    from datetime import UTC
except ImportError:  # Python 3.10
    UTC = timezone.utc
from pathlib import Path

# Same workspace-root convention as the live server: two parents up
# from this file would be wrong once archived, so keep the original
# assumption documented: WS is the host workspace, not this repo root.
WS = Path(__file__).resolve().parents[2]


def _utc() -> str:
    return datetime.now(UTC).isoformat()


def _run_json(cmd: list[str], timeout: int = 45) -> dict:
    try:
        p = subprocess.run(
            cmd,
            check=False,
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

REMOVED_TOOLS = [
    "continuity.preflight",           # tools/sister_turn_preflight.py
    "continuity.dual_lane_pending",   # tools/dual_lane_context_relay.py
    "continuity.expect_reply_status", # tools/sister_care_watch.py
    "continuity.joint_pulse",         # tools/sister_joint_pulse.py
    "continuity.doctor",              # tools/organism_doctor_all.py --json --fix-funnel
    "continuity.open_loops",          # tools/open_loops_scan.py --write
    "continuity.funnel_ensure",       # tools/harbor_funnel_ensure.py (Tailscale Funnel)
    "continuity.personal_lab",        # tools/personal_lab_progress.py
    "continuity.handoff_hygiene",     # tools/dual_lane_handoff_hygiene.py
]


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
        "hint": "If draft stuck: heal-draft + submit with correct send key (agent-a terminal=Enter).",
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

def tool_open_loops(**_kwargs) -> dict:
    return _run_json(
        [sys.executable, str(WS / "tools/open_loops_scan.py"), "--write", "--json"],
        timeout=90,
    )

def tool_funnel_ensure(**_kwargs) -> dict:
    return _run_json([sys.executable, str(WS / "tools/harbor_funnel_ensure.py")])


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
