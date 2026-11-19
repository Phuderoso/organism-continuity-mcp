# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
from pathlib import Path

import pytest

import organism_continuity.handoff as handoff
from organism_continuity.handoff import cli
from organism_continuity.telepatia import inbox


def lane(tmp: Path, name: str, mb: float = 0, checkpoints: int = 0) -> Path:
    d = tmp / name
    d.mkdir()
    (d / "session.jsonl").write_bytes(b"x" * int(mb * 1024 * 1024))
    if checkpoints:
        cc = d / "compaction_checkpoints"
        cc.mkdir()
        for i in range(checkpoints):
            (cc / f"{i}.json").write_text("{}")
    return d


def test_lane_pressure_levels(tmp_path: Path) -> None:
    th = handoff.Thresholds(log_warn_mb=1, log_handoff_mb=2, checkpoints_warn=2, checkpoints_handoff=4)
    assert handoff.lane_status("a", lane(tmp_path, "a", 0.1), th).pressure == "ok"
    assert handoff.lane_status("b", lane(tmp_path, "b", 1.5), th).pressure == "warn"
    assert handoff.lane_status("c", lane(tmp_path, "c", 2.5), th).pressure == "handoff"
    assert handoff.lane_status("d", lane(tmp_path, "d", 0, checkpoints=4), th).pressure == "handoff"
    assert handoff.lane_status("e", lane(tmp_path, "e", 0, checkpoints=2), th).pressure == "warn"
    assert handoff.lane_status("f", tmp_path / "missing", th).pressure == "unknown"


def test_status_recommends_high_to_low(tmp_path: Path) -> None:
    th = handoff.Thresholds(log_warn_mb=1, log_handoff_mb=2)
    lanes = {"long": str(lane(tmp_path, "long", 2.5)), "fresh": str(lane(tmp_path, "fresh"))}
    st = handoff.status(tmp_path / "h", lanes, th)
    assert st["recommended"] == {"source": "long", "dest": "fresh"}
    assert st["pending"] is False
    calm = handoff.status(tmp_path / "h", {"fresh": lanes["fresh"]}, th)
    assert calm["recommended"] is None


def test_package_and_absorb(tmp_path: Path) -> None:
    lanes = {"long": str(lane(tmp_path, "long", 0.01)), "fresh": str(lane(tmp_path, "fresh"))}
    hdir = tmp_path / "handoffs"
    meta = handoff.package(hdir, "long", "fresh", lanes=lanes, note="synthetic: refactor half done")
    assert handoff.ID_RE.match(meta["id"])
    md = (hdir / meta["md"]).read_text()
    assert "Layer 5 - Protocol" in md and "synthetic: refactor half done" in md
    assert (hdir / meta["md"]).stat().st_mode & 0o777 == 0o600
    assert handoff.pending(hdir)["pending"] is True
    out = handoff.absorb(hdir, meta["id"], "fresh")
    assert out["ok"] and out["absorbed_by"][0]["by"] == "fresh"
    assert handoff.pending(hdir)["pending"] is False
    assert "pending: false" in (hdir / "LATEST.md").read_text()


def test_package_never_reads_log_contents(tmp_path: Path) -> None:
    d = lane(tmp_path, "long")
    (d / "session.jsonl").write_text('{"text": "PRIVATE-TRANSCRIPT-LINE"}\n')
    meta = handoff.package(tmp_path / "h", "long", "fresh", lanes={"long": str(d)})
    assert "PRIVATE-TRANSCRIPT-LINE" not in (tmp_path / "h" / meta["md"]).read_text()


@pytest.mark.parametrize(
    "note",
    ["key " + "ab" * 32, "-----BEGIN RSA PRIVATE KEY-----", "ghp_" + "a" * 30, "x" * (handoff.MAX_NOTE_CHARS + 1)],
)
def test_notes_that_look_like_secrets_are_refused(tmp_path: Path, note: str) -> None:
    with pytest.raises(handoff.HandoffError):
        handoff.package(tmp_path, "long", "fresh", note=note)


def test_bad_ids_and_lanes(tmp_path: Path) -> None:
    with pytest.raises(handoff.HandoffError):
        handoff.absorb(tmp_path, "../../etc/passwd", "fresh")
    with pytest.raises(handoff.HandoffError, match="not_found"):
        handoff.absorb(tmp_path, "ho-20260101T000000Z-a-to-b-abcdef", "fresh")
    with pytest.raises(handoff.HandoffError):
        handoff.package(tmp_path, "Long Lane", "fresh")
    with pytest.raises(handoff.HandoffError):
        handoff.package(tmp_path, "same", "same")


def test_absorb_older_package_keeps_newer_pending(tmp_path: Path) -> None:
    first = handoff.package(tmp_path, "a", "b")
    second = handoff.package(tmp_path, "a", "b")
    handoff.absorb(tmp_path, first["id"], "b")
    assert handoff.pending(tmp_path)["id"] == second["id"]
    assert handoff.pending(tmp_path)["pending"] is True


def test_cli_handoff_with_notify(pair, capsys, tmp_path: Path) -> None:
    a, b = pair
    long_dir = lane(tmp_path, "long", 0.01)
    code = cli.main(
        [
            "package",
            "--source",
            "long",
            "--dest",
            "fresh",
            "--lane",
            f"long={long_dir}",
            "--notify",
            "agent-b",
            "--config",
            str(a.path),
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["notified"]["to"] == "agent-b"
    msg = inbox.read_verified(b).messages[0]
    assert out["id"] in msg.body
    assert cli.main(["pending", "--config", str(a.path)]) == 0
    assert json.loads(capsys.readouterr().out)["pending"] is True
    assert cli.main(["absorb", out["id"], "--by", "fresh", "--config", str(a.path)]) == 0
    capsys.readouterr()
    assert cli.main(["status", "--lane", f"long={long_dir}", "--config", str(a.path)]) == 0
    assert "long" in json.loads(capsys.readouterr().out)["lanes"]


def test_cli_handoff_config_table_and_dir(tmp_path: Path, capsys, pair) -> None:
    a, _ = pair
    capsys.readouterr()
    long_dir = lane(tmp_path, "long", 0.01)
    with open(a.path, "a", encoding="utf-8") as fh:
        fh.write(
            f'\n[handoff]\ndir = "handoffs-here"\n[handoff.lanes]\nlong = "{long_dir}"\n'
            "[handoff.thresholds]\nlog_warn_mb = 0.001\n"
        )
    assert cli.main(["status", "--config", str(a.path)]) == 0
    st = json.loads(capsys.readouterr().out)
    assert st["lanes"]["long"]["pressure"] == "warn"
    assert cli.main(["package", "--source", "long", "--dest", "fresh", "--config", str(a.path)]) == 0
    capsys.readouterr()
    assert (a.path.parent / "handoffs-here" / "PENDING.json").exists()


def test_cli_handoff_errors(tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEPATIA_CONFIG", str(tmp_path / "none.toml"))
    assert cli.main(["status"]) == 1
    assert cli.main(["status", "--dir", str(tmp_path / "h"), "--lane", "bad"]) == 1
    assert cli.main(["package", "--dir", str(tmp_path / "h")]) == cli.EXIT_USAGE
    assert cli.main(["absorb", "--dir", str(tmp_path / "h")]) == cli.EXIT_USAGE
    assert (
        cli.main(["package", "--dir", str(tmp_path / "h"), "--source", "a", "--dest", "b", "--notify", "agent-b"]) == 1
    )
    assert cli.main(["pending", "--dir", str(tmp_path / "h")]) == 0


def test_signing_is_imported_from_telepatia_not_copied() -> None:
    import inspect
    from pathlib import Path as P

    import organism_continuity.handoff.notify as notify_mod
    import organism_continuity.telepatia.inbox as kit_inbox
    import organism_continuity.telepatia.signing as kit_signing

    assert notify_mod.inbox is kit_inbox and notify_mod.signing is kit_signing
    pkg = P(inspect.getfile(handoff)).parent
    for src in pkg.glob("*.py"):
        text = src.read_text()
        for marker in ("import hmac", "hashlib", "compare_digest", "telepatia-sig/v1"):
            assert marker not in text, (src.name, marker)


def test_notify_message_verifies_with_telepatia_signing(pair, tmp_path: Path) -> None:
    from organism_continuity.handoff.notify import notify

    a, b = pair
    msg = notify(a, "agent-b", "ho-x", tmp_path / "ho-x.md")
    got = inbox.read_verified(b).messages
    assert [m.id for m in got] == [msg.id] and got[0].sender == "agent-a"


def test_module_entry_point_and_version(tmp_path: Path) -> None:
    import os
    import subprocess
    import sys

    root = Path(cli.__file__).parents[cli.__name__.count(".")]
    env = {**os.environ, "PYTHONPATH": str(root)}
    res = subprocess.run(
        [sys.executable, "-m", "organism_continuity.handoff", "pending", "--dir", str(tmp_path / "h")],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert res.returncode == 0 and json.loads(res.stdout)["pending"] is False
    with pytest.raises(SystemExit):
        cli.main(["--version"])
