# SPDX-License-Identifier: MIT
from __future__ import annotations

import inspect
import json
import secrets
from pathlib import Path
from typing import Any

import pytest

from organism_continuity.telepatia import signing

VECTORS: dict[str, Any] = json.loads((Path(__file__).parent / "vectors" / "telepatia-sig-v1.json").read_text())
TEST_KEY = bytes.fromhex(VECTORS["test_key_hex"])
RING = {"agent-a": TEST_KEY}
NOW = 1_700_000_000


def never(_s: str, _n: str) -> bool:
    return False


def check(text: str, *, transport_time: float = NOW, seen=never, me: str = "agent-b", ring=None) -> str:
    return signing.verify(
        text.encode("utf-8"),
        me=me,
        keyring=RING if ring is None else ring,
        transport_time=transport_time,
        seen_nonce=seen,
    ).status


# --- interop vectors -------------------------------------------------------------------------


@pytest.mark.parametrize("vec", VECTORS["positive"], ids=lambda v: v["signer"] + "-" + str(v["ts"]))
def test_positive_vectors_byte_for_byte(vec: dict[str, Any]) -> None:
    signed = signing.sign_text(vec["input_text"], vec["signer"], TEST_KEY, ts=vec["ts"], nonce=vec["nonce"])
    assert signed == vec["signed_text"]
    content, sig = signing.split_signature(signed)
    assert content == vec["content"] and sig is not None
    assert signing.base_key(vec["signer"]) == vec["base_key"]
    assert signing.canonical_bytes(vec["signer"], vec["ts"], vec["nonce"], content).decode() == vec["canonical"]
    assert signing.compute_mac(TEST_KEY, vec["signer"], vec["ts"], vec["nonce"], content) == vec["mac"]
    assert sig.group("mac") == vec["mac"]


def test_first_vector_verifies_as_spool_message() -> None:
    assert check(VECTORS["positive"][0]["signed_text"]) == signing.VERIFIED


@pytest.mark.parametrize("vec", VECTORS["negative"], ids=lambda v: v["reason"] + ":" + v.get("note", "")[:30])
def test_negative_vectors(vec: dict[str, Any]) -> None:
    seen = (lambda _s, _n: True) if vec.get("seen") else never
    t = vec.get("transport_time", VECTORS["default_transport_time"])
    assert check(vec["text"], transport_time=t, seen=seen) == vec["reason"]


def test_every_reason_has_a_negative_vector() -> None:
    covered = {v["reason"] for v in VECTORS["negative"]}
    assert covered >= set(signing.REJECT_REASONS) - {signing.TOO_LARGE}


# --- canonical form details ------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,key",
    [
        ("agent-a", "agent-a"),
        ("  Agent   A  ", "agent a"),
        ("*Agent*", "agent"),
        ("`'x'`", "x"),
        ("Name [tag]", "name"),
        ("Name[t]", "name"),
        ("A\tB", "a b"),
        ("STRASSE", "strasse"),
        ("Stra\u00dfe", "strasse"),
    ],
)
def test_base_key_rules(raw: str, key: str) -> None:
    assert signing.base_key(raw) == key


def test_content_gets_exactly_one_newline_and_trailer_is_replaced() -> None:
    once = signing.sign_text("abc", "agent-a", TEST_KEY, ts=NOW, nonce="0" * 16)
    assert once.startswith("abc\n<!-- telepatia-sig v=1 ") and once.endswith("-->\n")
    again = signing.sign_text(once, "agent-a", TEST_KEY, ts=NOW, nonce="0" * 16)
    assert again == once


def test_only_last_nonempty_line_is_a_trailer() -> None:
    signed = VECTORS["positive"][0]["signed_text"]
    assert check(signed + "\n\n") == signing.VERIFIED
    assert check(signed + "trailing text\n") == signing.UNSIGNED


def test_window_uses_transport_time_not_signed_ts() -> None:
    old = signing.sign("agent-a", "agent-b", "thirty days old", TEST_KEY, ts=NOW - 30 * 86400, nonce="5" * 32)
    # a verifier that took the time from the body itself would accept this; transport time refuses it
    assert check(old, transport_time=NOW) == signing.STALE
    assert check(old, transport_time=NOW - 30 * 86400 + signing.WINDOW_S) == signing.VERIFIED
    assert check(old, transport_time=NOW - 30 * 86400 - signing.WINDOW_S) == signing.VERIFIED
    assert check(old, transport_time=NOW - 30 * 86400 - signing.WINDOW_S - 1) == signing.STALE


def test_verify_requires_transport_time_and_nonce_store() -> None:
    params = inspect.signature(signing.verify).parameters
    assert params["transport_time"].default is inspect.Parameter.empty
    assert params["seen_nonce"].default is inspect.Parameter.empty


def test_replay_consulted_only_after_mac() -> None:
    calls: list[str] = []

    def seen(_s: str, n: str) -> bool:
        calls.append(n)
        return True

    forged = signing.sign("agent-a", "agent-b", "x", secrets.token_bytes(32), ts=NOW)
    assert check(forged, seen=seen) == signing.BAD_MAC and calls == []
    good = signing.sign("agent-a", "agent-b", "x", TEST_KEY, ts=NOW)
    assert check(good, seen=seen) == signing.REPLAYED_NONCE and len(calls) == 1


@pytest.mark.parametrize(
    "raw",
    [b"\xff\xfe", b"to: agent-b\nfrom: agent-a\n\n\xed\xa0\x80\n", "\ud800".encode("utf-8", "surrogatepass")],
)
def test_invalid_utf8_and_lone_surrogates_are_malformed(raw: bytes) -> None:
    res = signing.verify(raw, me="agent-b", keyring=RING, transport_time=NOW, seen_nonce=never)
    assert res.status in (signing.MALFORMED, signing.UNSIGNED)
    signed = signing.sign("agent-a", "agent-b", "ok", TEST_KEY, ts=NOW).encode()
    bad = signed.replace(b"ok", b"\xed\xa0\x80")
    assert signing.verify(bad, me="agent-b", keyring=RING, transport_time=NOW, seen_nonce=never).status == "malformed"


def test_sign_refuses_lone_surrogate() -> None:
    with pytest.raises(ValueError, match="utf8"):
        signing.sign("agent-a", "agent-b", "bad \ud800", TEST_KEY)


def test_too_large() -> None:
    raw = b" " * (signing.MAX_MESSAGE_BYTES + 1)
    assert signing.verify(raw, me="agent-b", keyring=RING, transport_time=NOW, seen_nonce=never).status == "too_large"


def test_sign_rejects_bad_input() -> None:
    for args in (
        ("agent-a", "agent-b", "   "),
        ("agent-a", "agent-b", "x" * (signing.MAX_BODY_CHARS + 1)),
        ("Agent A", "agent-b", "x"),
    ):
        with pytest.raises(ValueError):
            signing.sign(*args, TEST_KEY)
    with pytest.raises(ValueError):
        signing.sign_text("x", "has space", TEST_KEY)


def test_body_with_only_headers_is_malformed() -> None:
    text = signing.sign_text("to: agent-b\nfrom: agent-a\n\n \n", "agent-a", TEST_KEY, ts=NOW)
    assert check(text) == signing.MALFORMED


def test_uses_constant_time_compare() -> None:
    src = inspect.getsource(signing.verify)
    assert "hmac.compare_digest" in src and "== sig.group" not in src


def test_positive_vectors_2_to_4_are_mac_only() -> None:
    """D2: vectors 2-4 check the MAC and canonical form; as spool messages they are malformed."""
    assert [check(v["signed_text"]) for v in VECTORS["positive"][1:]] == [signing.MALFORMED] * 3
