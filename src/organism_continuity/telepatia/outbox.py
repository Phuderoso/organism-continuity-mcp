# SPDX-License-Identifier: MIT
"""Persistent outbox: hold a message until the peer is idle, survive restarts.

``chama --when-idle`` puts a message here when the peer is not idle (or its inbox does not
exist yet). The queue is one JSON file per sender::

    <spool>/queue/<sender>/outbox.json      0600, atomic writes, flock on outbox.lock

What is stored: ``message_id``, ``to``, ``body``, ``state``, ``attempts``, ``reason`` and
timestamps. What is NEVER stored: keys, MACs, nonces or any other secret. A held message is
signed only at the moment it is delivered, so a restart simply re-signs.

Delivery is retried on events only:

* ``flush`` is called by the sender on its own events (for example at the end of a turn);
* ``run`` blocks on the presence directory and flushes whenever a presence file changes.

A message held longer than ``HOLD_MAX_S`` is delivered anyway on the next flush: an inbox is
passive, so delivery never interrupts anyone; holding only avoids nagging a busy peer.

A corrupt or unreadable state file is never deleted: it is renamed ``outbox.json.corrupt-<ts>``
and the queue starts empty.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from organism_continuity.telepatia import inbox, presence
from organism_continuity.telepatia.config import Config
from organism_continuity.telepatia.events import DirWatch
from organism_continuity.telepatia.keys import check_name
from organism_continuity.telepatia.storage import atomic_write, locked, private_dir, read_regular

STATE_VERSION = 1
MAX_STATE_BYTES = 1024 * 1024
HOLD_MAX_S = 1800.0
MAX_COMPLETED = 200
PENDING = "pending"
DELIVERED = "delivered"

PENDING_FIELDS = ("message_id", "to", "body", "state", "attempts", "reason", "enqueued_at", "updated_at")
COMPLETED_FIELDS = ("message_id", "to", "state", "reason", "settled_at", "body_sha256")
SECRET_FIELDS = frozenset({"key", "mac", "nonce", "secret", "token", "signature", "hmac_key"})


def queue_dir(spool: Path, name: str) -> Path:
    """Outbox directory of sender ``name`` under ``spool``."""
    return Path(spool) / "queue" / check_name(name)


@dataclass
class FlushReport:
    """Result of one flush: delivered message ids and held ids with their reason."""

    delivered: list[str]
    held: dict[str, str]


class Outbox:
    """Persistent, lock-protected outbox of one sender."""

    def __init__(self, cfg: Config, *, log: Callable[[str], None] | None = None) -> None:
        self.cfg = cfg
        self.dir = queue_dir(cfg.spool, cfg.name)
        self.path = self.dir / "outbox.json"
        self.lock = self.dir / "outbox.lock"
        self._log = log or (lambda m: None)

    # --- persistence -------------------------------------------------------------------

    def _ensure(self) -> None:
        private_dir(Path(self.cfg.spool) / "queue")
        private_dir(self.dir)

    def _quarantine(self, reason: str, now: float) -> None:
        dest = Path(f"{self.path}.corrupt-{int(now)}")
        if dest.exists():
            dest = Path(f"{self.path}.corrupt-{int(now)}-{os.getpid()}")
        with contextlib.suppress(OSError):
            os.rename(self.path, dest)
        self._log(f"outbox_state_corrupt reason={reason} renamed={dest.name}")

    @staticmethod
    def _valid(rec: object, fields: tuple[str, ...]) -> bool:
        if not isinstance(rec, dict) or any(k in SECRET_FIELDS for k in rec):
            return False
        mid = rec.get("message_id")
        return (
            isinstance(mid, str)
            and bool(mid)
            and isinstance(rec.get("state"), str)
            and all(isinstance(k, str) for k in rec)
            and set(rec) <= set(fields)
        )

    def _load(self, now: float) -> dict[str, list[dict[str, Any]]]:
        empty: dict[str, list[dict[str, Any]]] = {"pending": [], "completed": []}
        if not os.path.lexists(self.path):
            return empty
        raw = read_regular(self.path, MAX_STATE_BYTES)
        if raw is None:
            self._quarantine("not_regular_or_too_large", now)
            return empty
        try:
            obj = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            self._quarantine("invalid_json", now)
            return empty
        if (
            not isinstance(obj, dict)
            or obj.get("v") != STATE_VERSION
            or any(k in SECRET_FIELDS for k in obj)
            or not isinstance(obj.get("pending"), list)
            or not isinstance(obj.get("completed"), list)
            or not all(self._valid(r, PENDING_FIELDS) for r in obj["pending"])
            or not all(self._valid(r, COMPLETED_FIELDS) for r in obj["completed"])
        ):
            self._quarantine("schema_invalid", now)
            return empty
        return {"pending": obj["pending"], "completed": obj["completed"]}

    def _save(self, state: dict[str, list[dict[str, Any]]]) -> None:
        payload = {
            "v": STATE_VERSION,
            "pending": [{k: r[k] for k in PENDING_FIELDS if k in r} for r in state["pending"]],
            "completed": [{k: r[k] for k in COMPLETED_FIELDS if k in r} for r in state["completed"][-MAX_COMPLETED:]],
        }
        data = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        if len(data) > MAX_STATE_BYTES:
            raise RuntimeError("outbox_state_too_large")
        atomic_write(self.path, data)

    # --- API ---------------------------------------------------------------------------

    def pending(self) -> list[dict[str, Any]]:
        """Return the held messages (copies)."""
        self._ensure()
        with locked(self.lock):
            return list(self._load(time.time())["pending"])

    def enqueue(self, to: str, body: str, *, now: float | None = None, reason: str = "") -> str:
        """Hold a message for ``to``; returns its message id. The body is stored unsigned."""
        check_name(to)
        if not isinstance(body, str) or not body.strip():
            raise ValueError("empty_body")
        now = time.time() if now is None else now
        self._ensure()
        mid = secrets.token_hex(8)
        with locked(self.lock):
            state = self._load(now)
            state["pending"].append(
                {
                    "message_id": mid,
                    "to": to,
                    "body": body,
                    "state": PENDING,
                    "attempts": 0,
                    "reason": reason,
                    "enqueued_at": now,
                    "updated_at": now,
                }
            )
            self._save(state)
        return mid

    def flush(self, *, now: float | None = None, hold_max_s: float = HOLD_MAX_S) -> FlushReport:
        """Deliver every held message whose peer is idle or whose hold expired."""
        now = time.time() if now is None else now
        self._ensure()
        report = FlushReport([], {})
        with locked(self.lock):
            state = self._load(now)
            keep = []
            for rec in state["pending"]:
                pres = presence.read_presence(self.cfg.spool, rec["to"], now=now)
                overdue = now - float(rec.get("enqueued_at") or now) >= hold_max_s
                if pres.state != presence.IDLE and not overdue:
                    rec.update(attempts=int(rec.get("attempts") or 0) + 1, reason=f"held_{pres.state}", updated_at=now)
                    report.held[rec["message_id"]] = rec["reason"]
                    keep.append(rec)
                    continue
                try:
                    inbox.deliver(self.cfg, rec["to"], rec["body"], now=now)
                except inbox.PeerInboxMissing:
                    rec.update(attempts=int(rec.get("attempts") or 0) + 1, reason="peer_inbox_missing", updated_at=now)
                    report.held[rec["message_id"]] = rec["reason"]
                    keep.append(rec)
                    continue
                state["completed"].append(
                    {
                        "message_id": rec["message_id"],
                        "to": rec["to"],
                        "state": DELIVERED,
                        "reason": "idle" if pres.state == presence.IDLE else "hold_expired",
                        "settled_at": now,
                        "body_sha256": hashlib.sha256(rec["body"].encode("utf-8")).hexdigest(),
                    }
                )
                report.delivered.append(rec["message_id"])
            state["pending"] = keep
            self._save(state)
        return report

    def run(self, *, timeout: float | None = None) -> FlushReport:
        """Flush, then block on presence-file events and flush again, until the queue is empty."""
        pdir = private_dir(presence.presence_dir(self.cfg.spool))
        deadline = None if timeout is None else time.monotonic() + timeout
        total = FlushReport([], {})
        with DirWatch(pdir) as watch:
            while True:
                rep = self.flush()
                total.delivered.extend(rep.delivered)
                total.held = rep.held
                if not rep.held:
                    return total
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return total
                watch.wait(remaining)
