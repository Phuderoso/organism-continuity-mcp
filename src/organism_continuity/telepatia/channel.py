# SPDX-License-Identifier: MIT
"""Verify ``telepatia-sig v=1`` texts from a non-spool transport, once, against receive time.

The spool reader (``inbox``) measures freshness against file mtimes and keeps its own nonce
store. This module is the same check for texts carried by any other transport, for example
comments on a code-hosting service, wake requests or relayed texts (``relay``):

1. ``receive_time`` is the time the transport assigned (for example the server's creation time
   of a comment). It must be a finite number; the signed ``ts`` is never used as the clock.
2. The trailer grammar is the general one (``docs/PROTOCOL.md`` section 2); content may be any
   text. The key is looked up by ``base_key(from)``; the MAC is compared in constant time.
3. ``|receive_time - ts|`` must not exceed ``WINDOW_S`` (600 s), and ``receive_time`` must be
   neither older than ``MAX_RECEIVE_AGE_S`` nor more than ``WINDOW_S`` ahead of the local clock.
4. The nonce is claimed in a :class:`~organism_continuity.telepatia.ledger.ReplayLedger` under
   one lock; a nonce already there is ``replayed_nonce``. A ledger problem raises
   :class:`~organism_continuity.telepatia.ledger.ReplayLedgerError` (fail closed).

``dry_run=True`` performs every check against a read-only view of the ledger and claims nothing,
so the same text still verifies (once) later.

Callers that defer acting on a verified text (for example because the recipient is busy) should
verify with ``dry_run=True`` first and verify for real only when they act, so a deferred text does
not burn its nonce.
"""

from __future__ import annotations

import hmac
import math
import time
from dataclasses import dataclass

from organism_continuity.telepatia import relay as relay_mod
from organism_continuity.telepatia import signing
from organism_continuity.telepatia.ledger import KEEP_AFTER_EXPIRY_S, ReplayLedger, ledger_key

WINDOW_S = signing.WINDOW_S
MAX_TEXT_BYTES = signing.MAX_MESSAGE_BYTES
MAX_RECEIVE_AGE_S = KEEP_AFTER_EXPIRY_S


@dataclass(frozen=True)
class ChannelCheck:
    """Outcome of :func:`verify_text`."""

    status: str
    signer: str = ""
    ts: int | None = None
    nonce: str = ""
    content: str = ""
    relay: relay_mod.Relay | None = None
    claimed: bool = False
    dry_run: bool = False

    @property
    def verified(self) -> bool:
        """True only for status ``verified``."""
        return self.status == signing.VERIFIED


def _finite(value: float, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"invalid_{what}")
    return float(value)


def verify_text(
    text: str,
    *,
    keyring: dict[str, bytes],
    receive_time: float,
    ledger: ReplayLedger,
    dry_run: bool = False,
    now: float | None = None,
) -> ChannelCheck:
    """Verify ``text`` once. See the module docstring for the order of checks."""
    receive_time = _finite(receive_time, "receive_time")
    now = _finite(time.time() if now is None else now, "clock")
    if not isinstance(text, str):
        return ChannelCheck(signing.MALFORMED, dry_run=dry_run)
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        return ChannelCheck(signing.MALFORMED, dry_run=dry_run)
    if size > MAX_TEXT_BYTES:
        return ChannelCheck(signing.TOO_LARGE, dry_run=dry_run)
    content, sig = signing.split_signature(text)
    if sig is None:
        return ChannelCheck(signing.UNSIGNED, dry_run=dry_run)
    signer = signing.base_key(sig.group("from"))
    ts, nonce = int(sig.group("ts")), sig.group("nonce")
    parsed_relay = relay_mod.parse_relay(content)

    def result(status: str, *, claimed: bool = False) -> ChannelCheck:
        return ChannelCheck(status, signer, ts, nonce, content, parsed_relay, claimed, dry_run)

    key = keyring.get(signer)
    if key is None:
        return result(signing.UNKNOWN_KEY)
    expected = signing.compute_mac(key, sig.group("from"), ts, nonce, content)
    if not hmac.compare_digest(expected, sig.group("mac")):
        return result(signing.BAD_MAC)
    if abs(receive_time - ts) > WINDOW_S or now - receive_time > MAX_RECEIVE_AGE_S or receive_time - now > WINDOW_S:
        return result(signing.STALE)
    entry = ledger_key(signer, nonce)
    with ledger.transaction(write=not dry_run, clock=now) as view:
        if view.seen(entry):
            return result(signing.REPLAYED_NONCE)
        if not dry_run:
            view.claim(entry, ts + WINDOW_S)
    return result(signing.VERIFIED, claimed=not dry_run)
