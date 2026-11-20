# SPDX-License-Identifier: MIT
from __future__ import annotations

import os
from pathlib import Path

import pytest

from organism_continuity.telepatia import channel, relay, signing
from organism_continuity.telepatia.ledger import ReplayLedger, ReplayLedgerError

KEY_A = b"a" * 32
KEY_B = b"b" * 32
RING = {"agent-a": KEY_A}
T = 1_760_000_000


@pytest.fixture
def ledger(tmp_path: Path) -> ReplayLedger:
    d = tmp_path / "state"
    d.mkdir(mode=0o700)
    os.chmod(d, 0o700)
    return ReplayLedger(d / "channel-ledger.json")


def signed(text: str = "wake up\n", *, ts: int = T, signer: str = "agent-a", key: bytes = KEY_A) -> str:
    return signing.sign_text(text, signer, key, ts=ts)


def check(text: str, ledger: ReplayLedger, *, receive: float = T + 5, now: float = T + 10, **kw: object):
    return channel.verify_text(text, keyring=RING, receive_time=receive, ledger=ledger, now=now, **kw)  # type: ignore[arg-type]


def test_verified_once_then_replayed(ledger: ReplayLedger) -> None:
    text = signed()
    first = check(text, ledger)
    assert first.verified and first.claimed and first.signer == "agent-a" and first.content == "wake up\n"
    again = check(text, ledger)
    assert again.status == signing.REPLAYED_NONCE and not again.claimed


def test_dry_run_claims_nothing(ledger: ReplayLedger) -> None:
    text = signed()
    dry = check(text, ledger, dry_run=True)
    assert dry.verified and dry.dry_run and not dry.claimed
    assert not ledger.path.exists() and not ledger.lock_path.exists()
    assert check(text, ledger).verified
    assert check(text, ledger, dry_run=True).status == signing.REPLAYED_NONCE


def test_freshness_against_receive_time_not_signed_ts(ledger: ReplayLedger) -> None:
    text = signed(ts=T)
    # the signed ts is recent relative to "now", but the transport says it arrived long after
    assert check(text, ledger, receive=T + 601, now=T + 602).status == signing.STALE
    assert check(text, ledger, receive=T - 601, now=T).status == signing.STALE
    assert check(text, ledger, receive=T + 600, now=T + 600).verified


def test_receive_time_bounds_against_local_clock(ledger: ReplayLedger) -> None:
    text = signed(ts=T)
    old_now = T + channel.MAX_RECEIVE_AGE_S + 1
    assert check(text, ledger, receive=T, now=old_now).status == signing.STALE
    assert check(text, ledger, receive=T, now=T - 601).status == signing.STALE


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), True, "1"])
def test_non_finite_receive_time_raises_before_anything(ledger: ReplayLedger, bad: object) -> None:
    with pytest.raises(ValueError, match="invalid_receive_time"):
        channel.verify_text("x", keyring=RING, receive_time=bad, ledger=ledger)  # type: ignore[arg-type]
    assert not ledger.path.exists()


def test_non_finite_clock(ledger: ReplayLedger) -> None:
    with pytest.raises(ValueError, match="invalid_clock"):
        channel.verify_text("x", keyring=RING, receive_time=T, ledger=ledger, now=float("nan"))


def test_rejections(ledger: ReplayLedger) -> None:
    assert check("no trailer\n", ledger).status == signing.UNSIGNED
    assert check(signed(signer="agent-z", key=KEY_B), ledger).status == signing.UNKNOWN_KEY
    assert check(signed(key=KEY_B), ledger).status == signing.BAD_MAC
    tampered = signed().replace("wake up", "wake UP")
    assert check(tampered, ledger).status == signing.BAD_MAC
    assert check("x" * (channel.MAX_TEXT_BYTES + 1), ledger).status == signing.TOO_LARGE
    assert check("\ud800", ledger).status == signing.MALFORMED
    assert check(b"bytes", ledger).status == signing.MALFORMED  # type: ignore[arg-type]
    assert not ledger.path.exists()  # nothing that failed before the nonce step touches the ledger


def test_signer_name_uses_base_key(ledger: ReplayLedger) -> None:
    text = signed(signer="**Agent-A**")
    res = check(text, ledger)
    assert res.verified and res.signer == "agent-a"
    # the same nonce under a differently spelled name is the same ledger entry
    nonce = res.nonce
    other = signing.sign_text("other\n", "agent-a", KEY_A, ts=T, nonce=nonce)
    assert check(other, ledger).status == signing.REPLAYED_NONCE


def test_ledger_problems_fail_closed(ledger: ReplayLedger) -> None:
    ledger.path.write_text("{corrupt")
    os.chmod(ledger.path, 0o600)
    with pytest.raises(ReplayLedgerError):
        check(signed(), ledger)
    with pytest.raises(ReplayLedgerError):
        check(signed(), ledger, dry_run=True)


def test_signed_relay_grants_relayer_not_origin(ledger: ReplayLedger) -> None:
    text = relay.relay_text("agent-c", "please wake", to="agent-b", sign=True, relayer="agent-a", key=KEY_A)
    _, sig = signing.split_signature(text)
    assert sig is not None
    res = channel.verify_text(
        text, keyring=RING, receive_time=int(sig.group("ts")), ledger=ledger, now=int(sig.group("ts"))
    )
    assert res.verified and res.signer == "agent-a"
    assert res.relay == relay.Relay("agent-c", "agent-b", None, "please wake")


def test_unsigned_relay_is_unsigned(ledger: ReplayLedger) -> None:
    res = check(relay.format_relay("agent-c", "hi"), ledger)
    assert res.status == signing.UNSIGNED and res.relay is None


def test_backward_clock_step_after_prune_does_not_allow_replay(ledger: ReplayLedger) -> None:
    text = signed(ts=T)
    assert check(text, ledger, receive=T, now=T).verified
    # Much later (clock far ahead), another text is claimed and the first entry is pruned.
    later = T + channel.MAX_RECEIVE_AGE_S + 10 * channel.WINDOW_S
    assert check(signed("other\n", ts=int(later)), ledger, receive=later, now=later).verified
    # The clock steps back to the original time: the forgotten nonce must not verify again.
    again = check(text, ledger, receive=T, now=T)
    assert again.status == signing.STALE and not again.claimed
    assert check(text, ledger, receive=T, now=T, dry_run=True).status == signing.STALE
