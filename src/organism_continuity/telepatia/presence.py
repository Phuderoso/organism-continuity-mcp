# SPDX-License-Identifier: MIT
"""Presence: is an agent idle, busy, absent, or unknown right now?

Contract (one small JSON file per agent, written only by that agent)::

    <spool>/presence/<name>.json
    {"name": "agent-b", "ts": 1760000000, "state": "idle", "task": ""}

* ``ts`` is epoch seconds or ISO-8601 (``Z`` or an offset; a naive time is read as UTC).
* ``state`` is ``idle`` | ``busy`` | ``absent``. A non-empty ``task`` or ``"busy": true`` also
  means busy (unless the state is ``absent``).
* A record is fresh when it is at most ``MAX_AGE_S`` (120 s) old. A ``ts`` more than
  ``FUTURE_SKEW_S`` (30 s) in the future is not trusted.
* Files larger than 4096 bytes, symlinks, special files, invalid JSON, a wrong ``name``,
  an unknown ``state``, a stale or future ``ts``: all of these read as ``unknown``.

Presence is advisory. It never grants authority to anyone; it only lets a sender decide to
hold a message (see ``outbox``) instead of delivering it while the peer is busy.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from organism_continuity.telepatia._compat import UTC
from organism_continuity.telepatia.keys import check_name
from organism_continuity.telepatia.storage import atomic_write, private_dir, read_regular

IDLE = "idle"
BUSY = "busy"
ABSENT = "absent"
UNKNOWN = "unknown"
STATES = (IDLE, BUSY, ABSENT)

MAX_AGE_S = 120.0
FUTURE_SKEW_S = 30.0
MAX_STATE_BYTES = 4096
MAX_TASK_CHARS = 200


@dataclass(frozen=True)
class Presence:
    """Result of a presence read: state, reason, task (when busy) and age."""

    state: str
    reason: str = ""
    task: str = ""
    age_s: float | None = None


def presence_dir(spool: Path) -> Path:
    """Directory holding every agent's presence file."""
    return Path(spool) / "presence"


def presence_path(spool: Path, name: str) -> Path:
    """Presence file of ``name``."""
    return presence_dir(spool) / f"{check_name(name)}.json"


def parse_ts(raw: object) -> float | None:
    """Epoch number or ISO-8601 string to epoch seconds; None when invalid."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str) and raw.strip():
        text = raw.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.timestamp()
    return None


def evaluate(
    obj: object, name: str, now: float, *, max_age_s: float = MAX_AGE_S, future_skew_s: float = FUTURE_SKEW_S
) -> Presence:
    """Pure contract check of one decoded record."""
    if not isinstance(obj, dict):
        return Presence(UNKNOWN, "not_an_object")
    if obj.get("name") != name:
        return Presence(UNKNOWN, "name_mismatch")
    ts = parse_ts(obj.get("ts"))
    if ts is None:
        return Presence(UNKNOWN, "bad_ts")
    age = now - ts
    if age < -future_skew_s:
        return Presence(UNKNOWN, "future_ts")
    if age > max_age_s:
        return Presence(UNKNOWN, "stale")
    state = obj.get("state")
    state = state.strip().lower() if isinstance(state, str) else ""
    raw_task = obj.get("task")
    task = raw_task.strip()[:MAX_TASK_CHARS] if isinstance(raw_task, str) else ""
    if state != ABSENT and (obj.get("busy") is True or task):
        state = BUSY
    if state not in STATES:
        return Presence(UNKNOWN, "bad_state")
    return Presence(state, "fresh", task if state == BUSY else "", max(age, 0.0))


def read_presence(spool: Path, name: str, *, now: float | None = None) -> Presence:
    """Read and evaluate an agent's presence file; any problem yields ``unknown``."""
    now = time.time() if now is None else now
    raw = read_regular(presence_path(spool, name), MAX_STATE_BYTES)
    if raw is None:
        return Presence(UNKNOWN, "missing_or_unsafe")
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return Presence(UNKNOWN, "invalid_json")
    return evaluate(obj, name, now)


def write_presence(spool: Path, name: str, state: str, *, task: str = "", now: float | None = None) -> Path:
    """Atomically publish our own presence. Call it on events (turn start/end), not on a timer."""
    if state not in STATES:
        raise ValueError(f"bad_state: {state}")
    rec = {
        "name": check_name(name),
        "ts": int(time.time() if now is None else now),
        "state": state,
        "task": (task or "").strip()[:MAX_TASK_CHARS],
    }
    data = (json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    if len(data) > MAX_STATE_BYTES:
        raise ValueError("presence_record_too_large")
    private_dir(presence_dir(spool))
    return atomic_write(presence_path(spool, name), data)
