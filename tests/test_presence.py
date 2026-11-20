# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from organism_continuity.telepatia import presence as p

NOW = 1_700_000_000.0


def rec(**kw) -> dict:
    base = {"name": "agent-b", "ts": NOW, "state": "idle"}
    base.update(kw)
    return base


@pytest.mark.parametrize("state", ["idle", "busy", "absent", "IDLE "])
def test_valid_states(state: str) -> None:
    assert p.evaluate(rec(state=state), "agent-b", NOW).state == state.strip().lower()


def test_task_or_busy_flag_means_busy() -> None:
    r = p.evaluate(rec(task="compiling"), "agent-b", NOW)
    assert r.state == p.BUSY and r.task == "compiling"
    assert p.evaluate(rec(busy=True), "agent-b", NOW).state == p.BUSY
    assert p.evaluate(rec(state="absent", task="x"), "agent-b", NOW).state == p.ABSENT


def test_fresh_window_is_120s() -> None:
    assert p.evaluate(rec(ts=NOW - 120), "agent-b", NOW).state == p.IDLE
    assert p.evaluate(rec(ts=NOW - 121), "agent-b", NOW).reason == "stale"


def test_future_more_than_30s_is_unknown() -> None:
    assert p.evaluate(rec(ts=NOW + 30), "agent-b", NOW).state == p.IDLE
    r = p.evaluate(rec(ts=NOW + 31), "agent-b", NOW)
    assert r.state == p.UNKNOWN and r.reason == "future_ts"


@pytest.mark.parametrize(
    "ts", ["2023-11-14T22:13:20Z", "2023-11-14T22:13:20+00:00", "2023-11-14T22:13:20", "2023-11-14T19:13:20-03:00"]
)
def test_iso_timestamps(ts: str) -> None:
    assert p.evaluate(rec(ts=ts), "agent-b", NOW).state == p.IDLE


@pytest.mark.parametrize(
    "obj,reason",
    [
        ([], "not_an_object"),
        (rec(name="agent-c"), "name_mismatch"),
        (rec(ts=True), "bad_ts"),
        (rec(ts="yesterday"), "bad_ts"),
        (rec(ts=None), "bad_ts"),
        (rec(state="sleeping"), "bad_state"),
        (rec(state=3), "bad_state"),
    ],
)
def test_anything_bad_is_unknown(obj, reason: str) -> None:
    r = p.evaluate(obj, "agent-b", NOW)
    assert r.state == p.UNKNOWN and r.reason == reason


def test_write_and_read_roundtrip(tmp_path: Path) -> None:
    path = p.write_presence(tmp_path, "agent-b", "busy", task="  synthetic task  ", now=NOW)
    assert path == tmp_path / "presence" / "agent-b.json"
    assert (path.stat().st_mode & 0o777) == 0o600
    r = p.read_presence(tmp_path, "agent-b", now=NOW + 1)
    assert (r.state, r.task) == ("busy", "synthetic task")


def test_write_rejects_bad_state(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        p.write_presence(tmp_path, "agent-b", "unknown")


def test_read_missing_oversize_symlink_and_garbage(tmp_path: Path) -> None:
    assert p.read_presence(tmp_path, "agent-b").reason == "missing_or_unsafe"
    d = tmp_path / "presence"
    d.mkdir()
    f = d / "agent-b.json"
    f.write_text(json.dumps(rec()) + " " * p.MAX_STATE_BYTES)
    assert p.read_presence(tmp_path, "agent-b", now=NOW).reason == "missing_or_unsafe"
    f.write_text("{oops")
    assert p.read_presence(tmp_path, "agent-b", now=NOW).reason == "invalid_json"
    f.unlink()
    real = tmp_path / "real.json"
    real.write_text(json.dumps(rec()))
    os.symlink(real, f)
    assert p.read_presence(tmp_path, "agent-b", now=NOW).state == p.UNKNOWN


def test_parse_ts_numbers() -> None:
    assert p.parse_ts(5) == 5.0 and p.parse_ts(5.5) == 5.5 and p.parse_ts("") is None
