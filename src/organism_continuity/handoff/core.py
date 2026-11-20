# SPDX-License-Identifier: MIT
"""External-memory handoff between two long-running agent sessions ("lanes").

Models do not share internal state. When one session grows large, continuity is kept by writing
a small, structured package to disk and pointing a fresh session at it, instead of replaying a
full transcript. This module measures lane pressure, writes the package and records absorption.
It never signs anything itself; :mod:`organism_continuity.handoff.notify` sends signed pointers through
``organism_continuity.telepatia``.

Files under the handoff directory (all 0600, atomic writes)::

    <id>.md         the package: five layers (state, narrative, intent, priority paths, protocol)
    <id>.json       metadata (schema ``telepatia_handoff.v1``)
    LATEST.md       pointer to the newest package
    PENDING.json    {"pending": true|false, "id": ...}

Lane pressure is computed from file sizes only (``*.jsonl`` logs in the session directory and
the number of entries in an optional ``compaction_checkpoints/`` directory). File contents are
never read, so no transcript text ends up in a package. Nothing here runs automatically.
"""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from organism_continuity.telepatia._compat import UTC
from organism_continuity.telepatia.storage import atomic_write, private_dir, read_regular

SCHEMA_HANDOFF = "telepatia_handoff.v1"
SCHEMA_STATUS = "telepatia_handoff_status.v1"
SCHEMA_PENDING = "telepatia_handoff_pending.v1"
ID_RE = re.compile(r"^ho-\d{8}T\d{6}Z-[a-z0-9][a-z0-9._-]{0,63}-to-[a-z0-9][a-z0-9._-]{0,63}-[0-9a-f]{6}$")
LANE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
MAX_NOTE_CHARS = 2000
MAX_META_BYTES = 256 * 1024
PRESSURE = {0: "ok", 2: "warn", 3: "handoff"}
_SECRETISH = re.compile(
    r"(-----BEGIN [A-Z ]*PRIVATE KEY-----|\b[0-9a-f]{64}\b|\bgh[pousr]_[A-Za-z0-9]{20,}\b|"
    r"\bsk-[A-Za-z0-9]{20,}\b|\bxox[baprs]-[A-Za-z0-9-]{10,}\b|\bAKIA[0-9A-Z]{16}\b)"
)


class HandoffError(ValueError):
    """Invalid handoff input (lane name, id, note) or a missing package."""

    pass


@dataclass(frozen=True)
class Thresholds:
    """Size thresholds in MiB for the summed ``*.jsonl`` logs, and checkpoint counts."""

    log_warn_mb: float = 40.0
    log_handoff_mb: float = 100.0
    checkpoints_warn: int = 40
    checkpoints_handoff: int = 80


@dataclass
class LaneStatus:
    """Size-based pressure measurement of one lane."""

    lane: str
    session_dir: str
    exists: bool
    log_mb: float = 0.0
    checkpoints: int = 0
    score: int = 0
    pressure: str = "unknown"
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready view of this status."""
        return {
            "lane": self.lane,
            "session_dir": self.session_dir,
            "exists": self.exists,
            "log_mb": self.log_mb,
            "checkpoints": self.checkpoints,
            "score": self.score,
            "pressure": self.pressure,
            "reasons": list(self.reasons),
        }


def _utc_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def check_lane(name: str) -> str:
    """Lane names follow the agent-name rules: lowercase ``[a-z0-9._-]``, max 64."""
    if not isinstance(name, str) or not LANE_RE.match(name):
        raise HandoffError(f"invalid_lane_name: {name!r}")
    return name


def check_note(note: str) -> str:
    """Notes are short free text. Anything that looks like a credential is refused."""
    note = (note or "").strip()
    if len(note) > MAX_NOTE_CHARS:
        raise HandoffError("note_too_long")
    if _SECRETISH.search(note):
        raise HandoffError("note_looks_like_a_secret")
    return note


def lane_status(lane: str, session_dir: str | Path, th: Thresholds | None = None) -> LaneStatus:
    """Measure one lane from file sizes only."""
    th = th or Thresholds()
    root = Path(session_dir)
    st = LaneStatus(check_lane(lane), str(root), root.is_dir())
    if not st.exists:
        return st
    total = sum(p.stat().st_size for p in root.glob("*.jsonl") if p.is_file() and not p.is_symlink())
    st.log_mb = round(total / (1024 * 1024), 3)
    cc = root / "compaction_checkpoints"
    st.checkpoints = sum(1 for _ in cc.iterdir()) if cc.is_dir() and not cc.is_symlink() else 0
    if st.log_mb >= th.log_handoff_mb:
        st.score, st.reasons = 3, [*st.reasons, f"log_handoff_{st.log_mb}mb"]
    elif st.log_mb >= th.log_warn_mb:
        st.score, st.reasons = 2, [*st.reasons, f"log_warn_{st.log_mb}mb"]
    if st.checkpoints >= th.checkpoints_handoff:
        st.score = 3
        st.reasons.append(f"checkpoints_handoff_{st.checkpoints}")
    elif st.checkpoints >= th.checkpoints_warn:
        st.score = max(st.score, 2)
        st.reasons.append(f"checkpoints_warn_{st.checkpoints}")
    st.pressure = PRESSURE[st.score]
    return st


def _load_json(path: Path) -> dict[str, Any]:
    raw = read_regular(path, MAX_META_BYTES)
    if raw is None:
        return {}
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


def _save_json(path: Path, obj: dict[str, Any]) -> None:
    atomic_write(path, (json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))


def status(handoff_dir: str | Path, lanes: dict[str, str], th: Thresholds | None = None) -> dict[str, Any]:
    """Pressure of every lane, a recommended direction (highest pressure -> lowest) and pending."""
    rows = {name: lane_status(name, path, th) for name, path in lanes.items()}
    ordered = sorted(rows.values(), key=lambda s: s.score, reverse=True)
    recommended = None
    if len(ordered) >= 2 and ordered[0].score >= 2 and ordered[0].score > ordered[-1].score:
        recommended = {"source": ordered[0].lane, "dest": ordered[-1].lane}
    pend = _load_json(Path(handoff_dir) / "PENDING.json")
    return {
        "schema": SCHEMA_STATUS,
        "ts": _utc_iso(),
        "lanes": {k: v.as_dict() for k, v in rows.items()},
        "recommended": recommended,
        "pending": bool(pend.get("pending")),
        "pending_id": pend.get("id"),
    }


_TEMPLATE = """# Handoff `{hid}`

- Generated: {ts}
- Source lane: {source} (pressure={sp}, log_mb={slog})
- Destination lane: {dest} (pressure={dp})
- Note: {note}

This is not a session dump. Continue from these layers only.

## Layer 1 - State

```json
{state}
```

## Layer 2 - Narrative

Short bullets: what was done, what is in progress, links to plans or summaries.

## Layer 3 - Intent

The current goals of the person you work for, in their words where possible. Leave out tool noise.

## Layer 4 - Priority paths

Files, docs or tests the next session should open first.

## Layer 5 - Protocol

1. Do not load the source session logs wholesale.
2. When you have read this package, mark it absorbed:
   `telepatia-handoff absorb {hid} --by <lane>`
3. Never write secrets into this file.
"""


def package(
    handoff_dir: str | Path,
    source: str,
    dest: str,
    *,
    lanes: dict[str, str] | None = None,
    note: str = "",
    th: Thresholds | None = None,
) -> dict[str, Any]:
    """Write a new package and mark it pending. Returns its metadata."""
    check_lane(source)
    check_lane(dest)
    if source == dest:
        raise HandoffError("source_equals_dest")
    note = check_note(note)
    root = private_dir(Path(handoff_dir))
    lanes = lanes or {}
    src = lane_status(source, lanes[source], th) if source in lanes else LaneStatus(source, "", False)
    dst = lane_status(dest, lanes[dest], th) if dest in lanes else LaneStatus(dest, "", False)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    hid = f"ho-{stamp}-{source}-to-{dest}-{secrets.token_hex(3)}"
    ts = _utc_iso()
    md = root / f"{hid}.md"
    body = _TEMPLATE.format(
        hid=hid,
        ts=ts,
        source=source,
        dest=dest,
        sp=src.pressure,
        slog=src.log_mb,
        dp=dst.pressure,
        note=note or "-",
        state=json.dumps(src.as_dict(), indent=2, sort_keys=True),
    )
    atomic_write(md, body.encode("utf-8"))
    meta = {
        "schema": SCHEMA_HANDOFF,
        "id": hid,
        "ts": ts,
        "source": source,
        "dest": dest,
        "md": md.name,
        "note": note,
        "metrics_source": src.as_dict(),
        "metrics_dest": dst.as_dict(),
        "absorbed_by": [],
    }
    _save_json(root / f"{hid}.json", meta)
    atomic_write(
        root / "LATEST.md",
        f"# Latest handoff\n\n- id: `{hid}`\n- file: `{md.name}`\n- ts: {ts}\n- pending: true\n".encode(),
    )
    _save_json(root / "PENDING.json", {"schema": SCHEMA_PENDING, "pending": True, "id": hid, "ts": ts})
    return meta


def absorb(handoff_dir: str | Path, handoff_id: str, by: str) -> dict[str, Any]:
    """Record that lane ``by`` has read package ``handoff_id``. Exact ids only."""
    if not ID_RE.match(handoff_id or ""):
        raise HandoffError(f"invalid_handoff_id: {handoff_id!r}")
    check_lane(by)
    root = Path(handoff_dir)
    path = root / f"{handoff_id}.json"
    meta = _load_json(path)
    if meta.get("schema") != SCHEMA_HANDOFF or meta.get("id") != handoff_id:
        raise HandoffError(f"handoff_not_found: {handoff_id}")
    ts = _utc_iso()
    prior = meta.get("absorbed_by")
    absorbed: list[Any] = prior if isinstance(prior, list) else []
    absorbed.append({"by": by, "ts": ts})
    meta["absorbed_by"] = absorbed
    _save_json(path, meta)
    pend = _load_json(root / "PENDING.json")
    if pend.get("id") == handoff_id:
        _save_json(
            root / "PENDING.json",
            {"schema": SCHEMA_PENDING, "pending": False, "id": handoff_id, "absorbed_by": by, "ts": ts},
        )
        atomic_write(
            root / "LATEST.md",
            f"# Latest handoff\n\n- id: `{handoff_id}`\n- pending: false\n- absorbed_by: `{by}`\n- ts: {ts}\n".encode(),
        )
    return {"ok": True, "id": handoff_id, "absorbed_by": absorbed}


def pending(handoff_dir: str | Path) -> dict[str, Any]:
    """Return the current ``PENDING.json`` (or a not-pending record)."""
    return _load_json(Path(handoff_dir) / "PENDING.json") or {"schema": SCHEMA_PENDING, "pending": False}
