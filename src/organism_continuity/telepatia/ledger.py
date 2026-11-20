# SPDX-License-Identifier: MIT
"""One-shot replay ledger for signed texts that arrive over a non-spool transport.

The spool reader keeps its own nonce store (``inbox``). Texts that arrive elsewhere (for example
comments fetched from a code-hosting service, or wake requests handed over by another process)
need the same guarantee: a signed text is acted upon at most once. This ledger records each
accepted ``<base_key>:<nonce>`` with the epoch after which the signature can no longer pass the
freshness check, so a replay inside that horizon is refused.

File format (a regular ``0600`` file in a directory that only its owner can write)::

    {"v": 1, "nonces": {"<base_key>:<nonce>": <expiry epoch>, ...}, "watermark": <epoch>}

``watermark`` (optional; ledgers written by 0.5.1 have none) is the highest prune horizon ever used: every
entry whose expiry was below it may have been forgotten. Verifiers refuse a text whose own
expiry is below the watermark, so a backward clock step after a prune cannot re-admit a
forgotten nonce.

It **fails closed**: a ledger that is a symlink, not a regular file, owned by someone else,
readable or writable by group/other, larger than ``MAX_LEDGER_BYTES``, not valid JSON (including
pathologically nested JSON) or not of the exact shape above raises :class:`ReplayLedgerError`,
and the caller must not act on the text. A missing file is an empty ledger.

Writes are atomic (tmp + fsync + rename) and the whole check-then-claim runs under an exclusive
``flock``. A read-only transaction (``write=False``, used by dry runs) takes a shared lock,
creates nothing and never saves.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import json
import math
import os
import stat
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from organism_continuity.telepatia.storage import atomic_write

LEDGER_VERSION = 1
MAX_LEDGER_BYTES = 4 * 1024 * 1024
#: An entry is kept this long past its expiry. Verifiers refuse receive times older than this
#: (``channel.MAX_RECEIVE_AGE_S``), so an entry pruned after it can no longer match a replay.
KEEP_AFTER_EXPIRY_S = 7 * 24 * 3600


class ReplayLedgerError(RuntimeError):
    """The ledger is unsafe, unreadable, corrupt or could not be saved. Fail closed."""


def ledger_key(signer_key: str, nonce: str) -> str:
    """Ledger entry key (same shape as the spool nonce store)."""
    return f"{signer_key}:{nonce}"


def _check_parent(parent: Path) -> None:
    try:
        st = os.lstat(parent)  # lstat: a symlinked parent directory is refused, not followed
    except FileNotFoundError as exc:
        raise ReplayLedgerError(f"ledger_parent_missing: {parent}") from exc
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise ReplayLedgerError(f"ledger_parent_not_a_directory: {parent}")
    if st.st_uid != os.getuid() or st.st_mode & 0o022:
        raise ReplayLedgerError(f"ledger_parent_not_private: {parent}")


def _open_private(path: Path, flags: int) -> int:
    try:
        fd = os.open(str(path), flags | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0), 0o600)
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            raise FileNotFoundError(str(path)) from exc
        raise ReplayLedgerError(f"ledger_unsafe: {path} ({errno.errorcode.get(exc.errno or 0, exc)})") from exc
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
        os.close(fd)
        raise ReplayLedgerError(f"ledger_not_private_regular_file: {path}")
    return fd


def _valid_expiry(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _load(path: Path) -> tuple[dict[str, float], float]:
    try:
        fd = _open_private(path, os.O_RDONLY)
    except FileNotFoundError:
        return {}, -math.inf
    with os.fdopen(fd, "rb") as stream:
        if os.fstat(stream.fileno()).st_size > MAX_LEDGER_BYTES:
            raise ReplayLedgerError(f"ledger_too_large: {path}")
        raw = stream.read(MAX_LEDGER_BYTES + 1)
    if len(raw) > MAX_LEDGER_BYTES:
        raise ReplayLedgerError(f"ledger_too_large: {path}")
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise ReplayLedgerError(f"ledger_corrupt: {path}") from exc
    records = obj.get("nonces") if isinstance(obj, dict) else None
    if (
        not isinstance(obj, dict)
        or obj.get("v") != LEDGER_VERSION
        or set(obj) - {"watermark"} != {"v", "nonces"}
        or ("watermark" in obj and not _valid_expiry(obj["watermark"]))
        or not isinstance(records, dict)
        or not all(isinstance(k, str) and _valid_expiry(v) for k, v in records.items())
    ):
        raise ReplayLedgerError(f"ledger_corrupt: {path}")
    watermark = float(obj["watermark"]) if "watermark" in obj else -math.inf
    return {k: float(v) for k, v in records.items()}, watermark


@dataclass
class LedgerView:
    """The ledger contents inside one transaction."""

    records: dict[str, float]
    writable: bool
    watermark: float = -math.inf
    dirty: bool = False
    claimed: list[str] = field(default_factory=list)

    def seen(self, key: str) -> bool:
        """True when ``key`` was already claimed and has not been pruned."""
        return key in self.records

    def forgotten(self, expires_at: float) -> bool:
        """True when an entry expiring at ``expires_at`` may already have been pruned."""
        return expires_at < self.watermark

    def claim(self, key: str, expires_at: float) -> None:
        """Record ``key`` as used until ``expires_at`` (saved when the transaction ends)."""
        if not self.writable:
            raise ReplayLedgerError("ledger_read_only")
        if not _valid_expiry(expires_at):
            raise ReplayLedgerError("ledger_invalid_expiry")
        self.records[key] = float(expires_at)
        self.claimed.append(key)
        self.dirty = True


class ReplayLedger:
    """A replay ledger stored at ``path``. Use :meth:`transaction` for every check or claim."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self.lock_path = self.path.with_name(self.path.name + ".lock")

    @contextlib.contextmanager
    def transaction(self, *, write: bool = True, clock: float | None = None) -> Iterator[LedgerView]:
        """Lock, load, yield a :class:`LedgerView`, then (when ``write``) prune and save.

        Pruning uses the local ``clock`` (default ``time.time()``), never a transport-supplied
        time, and drops only entries more than ``KEEP_AFTER_EXPIRY_S`` past their expiry. The
        prune horizon is saved as ``watermark`` and never decreases.
        Errors raised inside the block propagate and nothing is saved.
        """
        clock = time.time() if clock is None else clock
        if not math.isfinite(clock):
            raise ReplayLedgerError("ledger_invalid_clock")
        _check_parent(self.path.parent)
        if write:
            lock_fd = _open_private(self.lock_path, os.O_RDWR | os.O_CREAT)
        else:
            try:
                lock_fd = _open_private(self.lock_path, os.O_RDONLY)
            except FileNotFoundError:
                lock_fd = -1  # nothing was ever written; a read-only view creates nothing
        try:
            if lock_fd >= 0:
                fcntl.flock(lock_fd, fcntl.LOCK_EX if write else fcntl.LOCK_SH)
            records, watermark = _load(self.path)
            view = LedgerView(records, writable=write, watermark=watermark)
            yield view
            if write and view.dirty:
                # never lower the watermark, even if the clock stepped back
                horizon = max(clock - KEEP_AFTER_EXPIRY_S, watermark)
                kept = {k: v for k, v in view.records.items() if v >= horizon}
                payload = {"v": LEDGER_VERSION, "nonces": kept, "watermark": horizon}
                data = (json.dumps(payload, sort_keys=True) + "\n").encode()
                if len(data) > MAX_LEDGER_BYTES:
                    raise ReplayLedgerError(f"ledger_full: {self.path}")
                try:
                    atomic_write(self.path, data)
                except OSError as exc:
                    raise ReplayLedgerError(f"ledger_save_failed: {self.path}") from exc
        finally:
            if lock_fd >= 0:
                with contextlib.suppress(OSError):
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
