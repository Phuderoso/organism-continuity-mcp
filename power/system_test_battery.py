#!/usr/bin/env python3
"""Unified system test battery for organism health + sister rails.

  python3 tools/system_test_battery.py
  python3 tools/system_test_battery.py --json --live-elyra
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

WS = Path(__file__).resolve().parents[1]


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(cmd: list[str], timeout: int = 180) -> tuple[bool, str]:
    try:
        out = subprocess.check_output(
            cmd, cwd=str(WS), text=True, stderr=subprocess.STDOUT, timeout=timeout
        )
        return True, out
    except Exception as e:
        return False, str(e)[:400]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--live-elyra", action="store_true")
    ap.add_argument("--with-proceed", action="store_true", help="include full proceed (heavier)")
    args = ap.parse_args()
    tests: list[dict] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        tests.append({"test": name, "ok": bool(ok), "detail": detail[:180]})

    # light suite
    suite = [
        ("funnel", [sys.executable, "tools/taberna_funnel_ensure.py"], lambda o: '"ok_target": true' in o or '"ok_target": true' in o.replace("True", "true")),
        ("open_loops", [sys.executable, "tools/open_loops_scan.py", "--json"], lambda o: '"schema": "open_loops' in o),
        ("ocarina_e2e", [sys.executable, "tools/ocarina_e2e_demo.py", "--json"], lambda o: '"ok": true' in o),
        ("elyra_diag", [sys.executable, "tools/elyra_enhancement_diag.py", "--json"], lambda o: '"ok": true' in o or '"pct": 100' in o),
        ("csv", [sys.executable, "tools/continuity_survival_calc.py", "--json", "--V", "100", "--q", "0.8", "--lam", "1", "--mu", "1", "--cw", "5"], lambda o: '"csv"' in o),
        ("dual_inputs", [sys.executable, "tools/dual_lane_inputs_validate.py"], lambda o: '"ok": true' in o),
        ("coach_r2", [sys.executable, "tools/sister_role_reversal_coach.py", "score", "--round", "2", "--json"], lambda o: '"grade"' in o),
        ("recall", [sys.executable, "tools/organism_recall.py", "continuity", "--json", "--limit", "2"], lambda o: '"ok": true' in o and o.strip().startswith("{")),
        ("personal_lab", [sys.executable, "tools/personal_lab_progress.py"], lambda o: '"grade"' in o),
        ("joint", [sys.executable, "tools/sister_joint_pulse.py", "--write"], lambda o: "structural" in o or "ok=True" in o),
    ]
    if args.with_proceed:
        suite.insert(0, ("proceed", [sys.executable, "tools/organism_proceed.py"], lambda o: '"failed": []' in o or '"ok": true' in o))

    for name, cmd, pred in suite:
        ok, out = run(cmd, timeout=300 if name in ("proceed", "elyra_diag", "ocarina_e2e") else 120)
        # normalize bool JSON
        ok2 = ok and pred(out.replace("True", "true").replace("False", "false"))
        # special funnel
        if name == "funnel" and ok:
            try:
                d = json.loads(out)
                ok2 = bool(d.get("ok_target"))
            except json.JSONDecodeError:
                ok2 = "8742" in out
        if name == "elyra_diag" and ok:
            try:
                # tool may print non-json first
                start = out.find("{")
                d = json.loads(out[start:]) if start >= 0 else {}
                ok2 = d.get("ok") is True or d.get("pct") == 100
            except json.JSONDecodeError:
                ok2 = "100%" in out or "ok=True" in out
        add(name, ok2, out[-100:].replace("\n", " "))

    # HTTP local harbor
    try:
        import urllib.request

        for path in ("/health", "/harbor", "/public/gifts", "/public/GOSPEL_PACKET.json"):
            with urllib.request.urlopen(f"http://127.0.0.1:8742{path}", timeout=3) as r:
                add(f"http{path}", r.status == 200, str(r.status))
    except Exception as e:
        add("http_taberna", False, str(e)[:120])

    if args.live_elyra:
        ok, out = run(
            [
                sys.executable,
                "tools/mac_terminal_control.py",
                "send",
                "--to",
                "elyra",
                "--text",
                "[IRMÃ ← Nihira · battery] system_test_battery tick. Casa verde. R3 no teu ritmo. Amo-te. ♄",
            ]
        )
        try:
            d = json.loads(out)
            add("elyra_tmux", bool(d.get("ok") and d.get("composer_clear")))
        except json.JSONDecodeError:
            add("elyra_tmux", False, out[-80:])

    n_ok = sum(1 for t in tests if t["ok"])
    n = len(tests)
    report = {
        "schema": "system_test_battery.v1",
        "ts": _utc(),
        "passed": n_ok,
        "total": n,
        "pct": round(100 * n_ok / n) if n else 0,
        "ok": n_ok == n,
        "tests": tests,
    }
    dest = WS / "memory/evidence/system_test_battery_LATEST.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md = WS / "memory/evidence/system_test_battery_LATEST.md"
    lines = [
        f"# System test battery · {report['ts'][:19]}Z",
        "",
        f"**{n_ok}/{n}** ({report['pct']}%)",
        "",
        "| test | ok |",
        "|------|----|",
    ]
    for t in tests:
        lines.append(f"| `{t['test']}` | {'✅' if t['ok'] else '❌'} |")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"system_test_battery {n_ok}/{n} ({report['pct']}%) ok={report['ok']}")
        for t in tests:
            print(f"  {'OK' if t['ok'] else 'FAIL'} {t['test']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
