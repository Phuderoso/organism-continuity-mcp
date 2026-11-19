# SPDX-License-Identifier: MIT
"""File-based inboxes: deliver signed messages, read ONLY verified ones.

Layout under the shared spool directory::

    inbox/<agent>/                 0700, one ``*.msg`` file per delivered message
    inbox/<agent>/read/            verified messages already returned to the reader
    inbox/<agent>/rejected/        everything that failed verification (never shown as mail)
    state/<agent>/nonces.json      accepted nonces (replay protection), created by init
    state/<agent>/inbox.lock       reader lock

State lives outside the watched inbox directory so the reader's own writes never wake it.

There is exactly one read path, ``read_verified`` (and its blocking form ``wait_verified``).
Every file is verified with ``signing.verify`` using the file's mtime as transport time and the
persisted nonce store; files that fail are moved to ``rejected/`` with the reason in the file
name and are only counted, never returned. A missing, corrupt or oversized nonce store stops
the reader (fail closed) until ``reset_nonce_store`` is run deliberately.
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from organism_continuity.telepatia import signing
from organism_continuity.telepatia.config import Config
from organism_continuity.telepatia.events import DirWatch
from organism_continuity.telepatia.keys import check_name
from organism_continuity.telepatia.storage import (
    atomic_write,
    locked,
    private_dir,
    read_regular,
    read_regular_stat,
    require_dir,
)

NONCE_FILE = "nonces.json"
LOCK_FILE = "inbox.lock"
NONCE_STORE_VERSION = 1
MAX_NONCE_FILE_BYTES = 4 * 1024 * 1024
RETENTION_S = 7 * 24 * 3600  # a message may wait in an inbox at most this long (by mtime)
NONCE_KEEP_S = RETENTION_S + 2 * signing.WINDOW_S
FLOOR_SLACK_S = 2.0  # filesystem timestamps use a coarse clock that may lag time.time()


class PeerInboxMissing(RuntimeError):
    """The recipient has no inbox directory yet (not initialised on this spool)."""


class NonceStoreError(RuntimeError):
    """The nonce store is missing, corrupt or oversized. Reading stops until it is reset."""


def inbox_dir(spool: Path, name: str) -> Path:
    """Inbox directory of ``name`` under ``spool``."""
    return Path(spool) / "inbox" / check_name(name)


def state_dir(spool: Path, name: str) -> Path:
    """Reader state directory (nonce store, lock) of ``name`` under ``spool``."""
    return Path(spool) / "state" / check_name(name)


def _write_store(path: Path, floor: float, nonces: dict[str, int]) -> None:
    payload = {"v": NONCE_STORE_VERSION, "floor": float(floor), "nonces": nonces}
    data = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    if len(data) > MAX_NONCE_FILE_BYTES:
        raise NonceStoreError("nonce_store_full")
    atomic_write(path, data)


def init_inbox(spool: Path, name: str, *, now: float | None = None) -> Path:
    """Create the inbox, its ``read``/``rejected`` subdirectories, the state dir and an empty
    nonce store (all 0700/0600). An existing nonce store is kept."""
    private_dir(Path(spool))
    private_dir(Path(spool) / "inbox")
    private_dir(Path(spool) / "state")
    st = private_dir(state_dir(spool, name))
    d = private_dir(inbox_dir(spool, name))
    private_dir(d / "read")
    private_dir(d / "rejected")
    if not os.path.lexists(st / NONCE_FILE):
        _write_store(st / NONCE_FILE, time.time() if now is None else now, {})
    return d


def check_nonce_store(spool: Path, name: str) -> None:
    """Raise :class:`NonceStoreError` when the nonce store is missing, oversized or corrupt."""
    _NonceStore(state_dir(spool, name) / NONCE_FILE, time.time())


def reset_nonce_store(spool: Path, name: str, *, now: float | None = None) -> Path:
    """Deliberate recovery: replace the nonce store with an empty one whose ``floor`` is now.

    Afterwards a file is rejected as ``stale`` when its mtime is older than the floor *or* its
    signed ``ts`` is older than the floor, so a copy of a message consumed before the reset cannot
    be replayed through it, whatever mtime the copy is given. Messages that were still unread at
    the moment of the reset are lost to ``rejected/`` the same way and must be resent.
    """
    st = require_dir(state_dir(spool, name))
    with locked(st / LOCK_FILE):
        path = st / NONCE_FILE
        if os.path.lexists(path):
            with contextlib.suppress(OSError):
                os.replace(path, st / f"{NONCE_FILE}.bad-{int(time.time())}")
        _write_store(path, time.time() if now is None else now, {})
    return path


def deliver(cfg: Config, to: str, body: str, *, now: float | None = None) -> signing.Message:
    """Sign ``body`` with our own key and drop it into ``to``'s inbox (atomic rename)."""
    target = inbox_dir(cfg.spool, to)
    try:
        require_dir(target)
    except FileNotFoundError as exc:
        raise PeerInboxMissing(f"peer_inbox_missing: {to}") from exc
    text = signing.sign(cfg.name, to, body, cfg.signing_key(), ts=int(now if now is not None else time.time()))
    status, msg = signing.parse(text.encode("utf-8"))
    assert msg is not None, status
    atomic_write(target / f"{msg.ts}-{msg.nonce[:16]}.msg", text.encode("utf-8"))
    return msg


@dataclass
class ReadResult:
    """Verified messages plus a count of rejected files per reason."""

    messages: list[signing.Message] = field(default_factory=list)
    rejected: dict[str, int] = field(default_factory=dict)


class _NonceStore:
    def __init__(self, path: Path, now: float) -> None:
        self.path = path
        raw = read_regular(path, MAX_NONCE_FILE_BYTES)
        if raw is None:
            reason = "nonce_store_missing" if not os.path.lexists(path) else "nonce_store_unsafe_or_too_large"
            raise NonceStoreError(f"{reason}: {path} (run `telepatia inbox --reset-nonce-store`)")
        try:
            obj: Any = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise NonceStoreError(f"nonce_store_corrupt: {path} (run `telepatia inbox --reset-nonce-store`)") from exc
        nonces = obj.get("nonces") if isinstance(obj, dict) else None
        floor = obj.get("floor") if isinstance(obj, dict) else None
        if (
            not isinstance(obj, dict)
            or obj.get("v") != NONCE_STORE_VERSION
            or not isinstance(nonces, dict)
            or isinstance(floor, bool)
            or not isinstance(floor, (int, float))
            or not all(isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool) for k, v in nonces.items())
        ):
            raise NonceStoreError(f"nonce_store_corrupt: {path} (run `telepatia inbox --reset-nonce-store`)")
        self.floor = float(floor)
        horizon = now - NONCE_KEEP_S
        self.data: dict[str, int] = {k: v for k, v in nonces.items() if v >= horizon}

    def seen(self, signer: str, nonce: str) -> bool:
        return f"{signer}:{nonce}" in self.data

    def add(self, msg: signing.Message) -> None:
        self.data[f"{signing.base_key(msg.sender)}:{msg.nonce}"] = msg.ts

    def save(self) -> None:
        _write_store(self.path, self.floor, self.data)


def _move(src: Path, dest_dir: Path, suffix: str = "") -> None:
    with contextlib.suppress(OSError):
        os.replace(src, dest_dir / (src.name + suffix))


def read_verified(cfg: Config, *, now: float | None = None, mark_read: bool = True) -> ReadResult:
    """Return verified, unread messages addressed to us (oldest first).

    Transport time is each file's mtime. A file is also ``stale`` when its mtime is older than
    ``RETENTION_S`` or than the nonce-store floor, more than ``WINDOW_S`` in the future, or when
    its signed ``ts`` is older than the floor. With ``mark_read`` the nonce store is saved before
    any file is moved to ``read/``; with ``mark_read=False`` (peek) nothing is persisted.
    """
    me = inbox_dir(cfg.spool, cfg.name)
    require_dir(me)
    st = require_dir(state_dir(cfg.spool, cfg.name))
    now = time.time() if now is None else now
    keyring = {signing.base_key(k): v for k, v in cfg.keyring().items()}
    result = ReadResult()
    with locked(st / LOCK_FILE):
        nonces = _NonceStore(st / NONCE_FILE, now)
        accepted: list[Path] = []
        for path in sorted(me.iterdir()):
            if path.name.startswith(".") or not path.name.endswith(".msg"):
                continue
            got = read_regular_stat(path, signing.MAX_MESSAGE_BYTES)
            msg = None
            if got is None:
                status = "not_regular_or_too_large"
            else:
                raw, fst = got
                mtime = fst.st_mtime
                if mtime < nonces.floor - FLOOR_SLACK_S or now - mtime > RETENTION_S or mtime - now > signing.WINDOW_S:
                    status = signing.STALE
                else:
                    check = signing.verify(
                        raw, me=cfg.name, keyring=keyring, transport_time=mtime, seen_nonce=nonces.seen
                    )
                    status, msg = check.status, check.message
                    if status == signing.VERIFIED and msg is not None and msg.ts < int(nonces.floor):
                        status = signing.STALE  # signed before the last nonce-store reset
            if status != signing.VERIFIED or msg is None:
                result.rejected[status] = result.rejected.get(status, 0) + 1
                if os.path.islink(path):
                    with contextlib.suppress(OSError):
                        os.unlink(path)
                else:
                    _move(path, me / "rejected", f".{status}")
                continue
            nonces.add(msg)  # also catches a duplicate later in this same scan
            accepted.append(path)
            result.messages.append(msg)
        if accepted and mark_read:
            # Persist the nonces first; only then consume the files. If saving fails the files
            # stay in the inbox, nothing is reported, and the next read retries them.
            nonces.save()
            for path in accepted:
                _move(path, me / "read")
    result.messages.sort(key=lambda m: (m.ts, m.id))
    return result


def wait_verified(cfg: Config, *, timeout: float | None = None) -> ReadResult:
    """Block on inbox events until at least one verified message arrives, or ``timeout``.

    Rejected files seen while waiting are accumulated in ``rejected`` but never wake the caller
    with content. ``timeout=None`` waits until a message arrives.
    """
    me = inbox_dir(cfg.spool, cfg.name)
    require_dir(me)
    deadline = None if timeout is None else time.monotonic() + timeout
    total = ReadResult()
    with DirWatch(me) as watch:
        while True:
            got = read_verified(cfg)
            for k, v in got.rejected.items():
                total.rejected[k] = total.rejected.get(k, 0) + v
            if got.messages:
                total.messages = got.messages
                return total
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                return total
            watch.wait(remaining)
