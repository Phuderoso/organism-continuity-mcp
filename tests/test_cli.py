# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from organism_continuity.telepatia import cli, inbox, signing
from organism_continuity.telepatia._compat import UTC


def run(capsys, *argv: str) -> tuple[int, str, str]:
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def mode(p: Path) -> int:
    return stat.S_IMODE(os.lstat(p).st_mode)


def test_init_creates_private_key_and_dir(tmp_path: Path, capsys) -> None:
    cfg = tmp_path / "a" / "telepatia.toml"
    code, out, _ = run(
        capsys, "init", "--name", "agent-a", "--config", str(cfg), "--spool", str(tmp_path / "spool"), "--json"
    )
    assert code == 0
    info = json.loads(out)
    key = Path(info["key_file"])
    assert mode(key) == 0o600
    assert mode(key.parent) == 0o700
    assert mode(cfg) == 0o600
    assert mode(tmp_path / "spool" / "inbox" / "agent-a") == 0o700
    assert key.read_text().strip() not in out
    code, _, err = run(capsys, "init", "--name", "agent-a", "--config", str(cfg), "--spool", str(tmp_path))
    assert code == 1 and "config_exists" in err


def test_init_refuses_keys_in_worktree(tmp_path: Path, capsys) -> None:
    (tmp_path / ".git").mkdir()
    code, _, err = run(
        capsys, "init", "--name", "agent-a", "--config", str(tmp_path / "c.toml"), "--spool", str(tmp_path / "s")
    )
    assert code == 1 and "worktree" in err


def test_send_and_inbox_text_and_json(pair, capsys) -> None:
    a, b = pair
    assert run(capsys, "chama", "agent-b", "synthetic", "ping", "--config", str(a.path))[0] == 0
    code, out, _ = run(capsys, "inbox", "--config", str(b.path))
    assert code == 0 and "synthetic ping" in out and "(verified)" in out
    assert run(capsys, "inbox", "--config", str(b.path))[0] == cli.EXIT_EMPTY
    run(capsys, "send", "agent-b", "two", "--config", str(a.path))
    code, out, _ = run(capsys, "inbox", "--wait", "--timeout", "1", "--json", "--config", str(b.path))
    assert json.loads(out)["body"] == "two" and json.loads(out)["verified"] is True


def test_inbox_reports_rejections_on_stderr_only(pair, capsys) -> None:
    _a, b = pair
    d = inbox.inbox_dir(b.spool, "agent-b")
    (d / "x.msg").write_text(signing.sign("agent-a", "agent-b", "FORGED-BODY", os.urandom(32)))
    code, out, err = run(capsys, "inbox", "--peek", "--config", str(b.path))
    assert code == cli.EXIT_EMPTY
    assert "FORGED-BODY" not in out + err
    assert "bad_mac=1" in err


def test_when_idle_and_outbox(pair, capsys) -> None:
    a, b = pair
    code, out, _ = run(capsys, "chama", "agent-b", "hold", "--when-idle", "--json", "--config", str(a.path))
    assert json.loads(out)["presence"] == "unknown"
    code, out, _ = run(capsys, "outbox", "list", "--config", str(a.path))
    assert "held_unknown" in out
    assert run(capsys, "presence", "set", "idle", "--config", str(b.path))[0] == 0
    code, out, _ = run(capsys, "presence", "get", "agent-b", "--json", "--config", str(a.path))
    assert json.loads(out)["state"] == "idle"
    code, out, _ = run(capsys, "chama", "agent-b", "now", "--when-idle", "--json", "--config", str(a.path))
    assert "delivered" in json.loads(out)
    _code, out, _ = run(capsys, "outbox", "flush", "--json", "--config", str(a.path))
    assert len(json.loads(out)["delivered"]) == 1
    assert run(capsys, "outbox", "run", "--timeout", "0.1", "--config", str(a.path))[0] == 0
    assert run(capsys, "outbox", "list", "--json", "--config", str(a.path))[1].strip() == "[]"


def test_queue_if_missing(pair, capsys) -> None:
    a, _ = pair
    code, _, err = run(capsys, "chama", "agent-z", "x", "--config", str(a.path))
    assert code == 1 and "peer_inbox_missing" in err
    code, out, _ = run(capsys, "chama", "agent-z", "x", "--queue-if-missing", "--json", "--config", str(a.path))
    assert json.loads(out)["reason"] == "peer_inbox_missing"


def test_peer_list_add_remove(pair, capsys, tmp_path: Path) -> None:
    _a, b = pair
    code, out, _ = run(capsys, "peer", "list", "--config", str(b.path))
    assert out.startswith("agent-a\t")
    _code, out, _ = run(capsys, "peer", "list", "--json", "--config", str(b.path))
    assert json.loads(out)[0]["name"] == "agent-a"
    assert run(capsys, "peer", "add", "agent-b", "--key-file", "x", "--config", str(b.path))[0] == 1
    assert run(capsys, "peer", "add", "agent-c", "--config", str(b.path))[0] == cli.EXIT_USAGE
    assert run(capsys, "peer", "add", "agent-a", "--key-file", str(b.key_file), "--config", str(b.path))[0] == 1
    assert run(capsys, "peer", "remove", "agent-a", "--config", str(b.path))[0] == 0
    assert run(capsys, "peer", "remove", "agent-a", "--config", str(b.path))[0] == 1
    b.peers["agent-a"].chmod(0o644)
    run(capsys, "peer", "remove", "agent-q", "--config", str(b.path))


def test_peer_list_marks_unusable_key(pair, capsys) -> None:
    _, b = pair
    b.peers["agent-a"].chmod(0o644)
    _, out, _ = run(capsys, "peer", "list", "--config", str(b.path))
    assert "unusable" in out


def test_key_fingerprint_rotate_revoke(pair, capsys) -> None:
    a, b = pair
    _code, out, _ = run(capsys, "key", "fingerprint", "--json", "--config", str(a.path))
    fp = json.loads(out)["fingerprint"]
    _, out, _ = run(capsys, "key", "fingerprint", "agent-a", "--json", "--config", str(b.path))
    assert json.loads(out)["fingerprint"] == fp
    _, out, _ = run(capsys, "key", "rotate", "--json", "--config", str(a.path))
    assert json.loads(out)["replaced_fingerprint"] == fp
    # after rotation the old peer copy no longer verifies new messages
    run(capsys, "chama", "agent-b", "after rotation", "--config", str(a.path))
    _, out, err = run(capsys, "inbox", "--config", str(b.path))
    assert "after rotation" not in out and "bad_mac=1" in err
    assert run(capsys, "key", "revoke", "agent-a", "--config", str(b.path))[0] == cli.EXIT_USAGE
    assert run(capsys, "key", "revoke", "agent-a", "--yes", "--config", str(b.path))[0] == 0
    _, out, _ = run(capsys, "peer", "list", "--json", "--config", str(b.path))
    assert json.loads(out) == []


def test_doctor(pair, capsys) -> None:
    _a, b = pair
    assert run(capsys, "doctor", "--config", str(b.path))[0] == 0
    b.peers["agent-a"].chmod(0o644)
    inbox.inbox_dir(b.spool, "agent-b").chmod(0o755)
    b.key_file.chmod(0o640)
    code, out, _ = run(capsys, "doctor", "--json", "--config", str(b.path))
    assert code == 1 and len(json.loads(out)["problems"]) == 3


def test_errors_are_reported_not_raised(tmp_path: Path, capsys) -> None:
    code, _, err = run(capsys, "inbox", "--config", str(tmp_path / "missing.toml"))
    assert code == 1 and "config_missing" in err


def test_module_entry_point(pair) -> None:
    _a, _ = pair
    env = {**os.environ, "PYTHONPATH": str(Path(cli.__file__).parents[cli.__name__.count(".")])}
    res = subprocess.run(
        [sys.executable, "-m", "organism_continuity.telepatia", "--version"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert res.returncode == 0 and "0.5.1" in res.stdout


def test_presence_get_defaults_to_self(pair, capsys) -> None:
    _, b = pair
    _, out, _ = run(capsys, "presence", "get", "--config", str(b.path))
    assert "agent-b" in out and "unknown" in out


@pytest.mark.parametrize("argv", [["chama"], ["inbox", "--bogus"], []])
def test_usage_errors(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(argv)


def test_corrupt_nonce_store_exit_and_reset(pair, capsys) -> None:
    a, b = pair
    store = inbox.state_dir(b.spool, "agent-b") / inbox.NONCE_FILE
    inbox.deliver(a, "agent-b", "pending")
    store.write_text("{corrupt")
    code, out, err = run(capsys, "inbox", "--config", str(b.path))
    assert code == 1 and "nonce_store" in err and "pending" not in out
    code, out, _ = run(capsys, "doctor", "--config", str(b.path), "--json")
    assert code == 1 and "reset-nonce-store" in out
    code, _, err = run(capsys, "inbox", "--config", str(b.path), "--reset-nonce-store")
    assert code == 2 and "--yes" in err
    code, out, _ = run(capsys, "inbox", "--config", str(b.path), "--reset-nonce-store", "--yes", "--json")
    assert code == 0 and "reset_nonce_store" in out
    code, _, _ = run(capsys, "doctor", "--config", str(b.path))
    assert code == 0


def test_generate_key_never_overwrites(tmp_path: Path) -> None:
    from organism_continuity.telepatia import keys

    d = tmp_path / "k"
    first = keys.generate_key(d, "agent-a")
    before = (d / "agent-a.key").read_bytes()
    with pytest.raises(FileExistsError):
        keys.generate_key(d, "agent-a")
    with pytest.raises(FileExistsError):  # the race path: link() refuses even after the pre-check
        keys._write_new_key(d / "agent-a.key")
    assert (d / "agent-a.key").read_bytes() == before and first["fingerprint"]
    assert [p.name for p in d.iterdir()] == ["agent-a.key"]  # no temp file left behind


def test_relay_unsigned_needs_no_config(capsys) -> None:
    code, out, _ = run(capsys, "relay", "agent-c", "hello", "there", "--to", "agent-b", "--reply-to", "7")
    assert code == 0
    assert out == "<!-- telepatia-relay -->\n<!-- reply-to: 7 -->\n**from: agent-c**\nto: agent-b\n\nhello there\n"


def test_relay_sign_and_verify_text_once(pair, capsys, tmp_path: Path) -> None:
    a, b = pair
    code, out, _ = run(capsys, "relay", "agent-c", "wake", "--sign", "--config", str(a.path))
    assert code == 0
    _, sig = signing.split_signature(out)
    assert sig is not None and sig.group("from") == "agent-a"
    f = tmp_path / "relay.txt"
    f.write_text(out)
    ts = sig.group("ts")
    argv = ["verify-text", str(f), "--receive-time", ts, "--config", str(b.path), "--json"]
    code, dry, _ = run(capsys, *argv, "--dry-run")
    info = json.loads(dry)
    assert code == 0 and info["status"] == "verified" and info["claimed"] is False and info["dry_run"] is True
    assert info["relay_origin"] == "agent-c" and info["content"] == "wake"
    code, real, _ = run(capsys, *argv)
    assert code == 0 and json.loads(real)["claimed"] is True
    assert mode(inbox.state_dir(b.spool, "agent-b") / cli.CHANNEL_LEDGER_FILE) == 0o600
    code, again, _ = run(capsys, *argv)
    assert code == cli.EXIT_REJECTED and json.loads(again)["status"] == "replayed_nonce"
    assert "content" not in json.loads(again)


def test_verify_text_stdin_iso_time_and_errors(pair, capsys, monkeypatch, tmp_path: Path) -> None:
    import io

    a, b = pair
    text = signing.sign_text("plain\n", "agent-a", a.signing_key())
    _, sig = signing.split_signature(text)
    assert sig is not None
    iso = datetime.fromtimestamp(int(sig.group("ts")), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    ledger = tmp_path / "ledger-dir"
    ledger.mkdir(mode=0o700)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(text.encode())))
    code, out, _ = run(
        capsys, "verify-text", "--receive-time", iso, "--ledger", str(ledger / "l.json"), "--config", str(b.path)
    )
    assert code == 0 and "status: verified" in out and "content: plain" in out
    for bad_time in ("soon", "nan", "inf"):
        code, _, err = run(capsys, "verify-text", "--receive-time", bad_time, "--config", str(b.path))
        assert code == cli.EXIT_USAGE and "receive-time" in err
    bad = tmp_path / "bad.bin"
    bad.write_bytes(b"\xff\xfe")
    code, out, _ = run(capsys, "verify-text", str(bad), "--receive-time", "0", "--config", str(b.path), "--json")
    assert code == cli.EXIT_REJECTED and json.loads(out)["status"] == "malformed"
    corrupt = ledger / "c.json"
    corrupt.write_text("nope")
    os.chmod(corrupt, 0o600)
    f = tmp_path / "t.txt"
    f.write_text(text)
    code, _, err = run(
        capsys,
        "verify-text",
        str(f),
        "--receive-time",
        sig.group("ts"),
        "--ledger",
        str(corrupt),
        "--config",
        str(b.path),
    )
    assert code == 1 and "ledger_corrupt" in err
