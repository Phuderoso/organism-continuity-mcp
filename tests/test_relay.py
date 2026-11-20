# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from organism_continuity.telepatia import relay, signing

KEY = b"k" * 32


def test_unsigned_shape_is_default() -> None:
    body = relay.relay_text("agent-c", "hello\n", to="agent-b", reply_to=42)
    assert body == "<!-- telepatia-relay -->\n<!-- reply-to: 42 -->\n**from: agent-c**\nto: agent-b\n\nhello\n"
    assert signing.split_signature(body)[1] is None
    assert relay.parse_relay(body) == relay.Relay("agent-c", "agent-b", 42, "hello")


def test_minimal_shape_round_trip() -> None:
    body = relay.format_relay("Agent C", "multi\nline")
    assert relay.parse_relay(body) == relay.Relay("Agent C", "", None, "multi\nline")


def test_signed_as_relayer_only_when_asked() -> None:
    signed = relay.relay_text("agent-c", "hi", sign=True, relayer="agent-a", key=KEY)
    content, sig = signing.split_signature(signed)
    assert sig is not None and sig.group("from") == "agent-a"
    assert content == relay.format_relay("agent-c", "hi")
    mac = signing.compute_mac(KEY, "agent-a", int(sig.group("ts")), sig.group("nonce"), content)
    assert mac == sig.group("mac")


def test_sign_relay_deterministic() -> None:
    body = relay.format_relay("agent-c", "hi")
    a = relay.sign_relay(body, "agent-a", KEY, ts=1760000000, nonce="0" * 32)
    b = signing.sign_text(body, "agent-a", KEY, ts=1760000000, nonce="0" * 32)
    assert a == b


def test_sign_needs_relayer_and_key() -> None:
    with pytest.raises(ValueError, match="needs_relayer_and_key"):
        relay.relay_text("agent-c", "hi", sign=True)
    with pytest.raises(ValueError, match="needs_relayer_and_key"):
        relay.relay_text("agent-c", "hi", sign=True, relayer="agent-a")


def test_sign_relay_refuses_non_relay() -> None:
    with pytest.raises(ValueError, match="not_a_relay_body"):
        relay.sign_relay("plain text\n", "agent-a", KEY)


@pytest.mark.parametrize("origin", ["", "  ", "a\nb", "<!-- x", "x -->", "**x**"])
def test_bad_origin(origin: str) -> None:
    with pytest.raises(ValueError, match="relay_origin_invalid"):
        relay.format_relay(origin, "hi")


def test_bad_to_message_reply_to() -> None:
    with pytest.raises(ValueError, match="relay_to_invalid"):
        relay.format_relay("a", "hi", to="b\nc")
    with pytest.raises(ValueError, match="message_required"):
        relay.format_relay("a", " \n")
    with pytest.raises(ValueError, match="reply_to_invalid"):
        relay.format_relay("a", "hi", reply_to=-1)
    with pytest.raises(ValueError, match="reply_to_invalid"):
        relay.format_relay("a", "hi", reply_to=True)


def test_message_with_trailer_refused() -> None:
    forged = signing.sign_text("x\n", "agent-b", KEY)
    with pytest.raises(ValueError, match="has_sig_trailer"):
        relay.format_relay("agent-c", forged)


@pytest.mark.parametrize(
    "text",
    [
        "plain\n",
        "<!-- telepatia-relay -->\n**from: a**\n",
        "<!-- telepatia-relay -->\nfrom: a\n\nhi\n",
        "<!-- telepatia-relay -->\n<!-- reply-to: 1 -->\n\nhi\n",
        "<!-- telepatia-relay -->\n**from: a**\nto: b\nextra\n\nhi\n",
        "<!-- telepatia-relay -->\n**from: a**\nnot-to\n\nhi\n",
        "<!-- telepatia-relay -->\n**from: a**\n\n  \n",
    ],
)
def test_parse_rejects(text: str) -> None:
    assert relay.parse_relay(text) is None


def test_is_relay() -> None:
    assert relay.is_relay("<!-- telepatia-relay -->\nx")
    assert not relay.is_relay("x\n<!-- telepatia-relay -->")
    assert not relay.is_relay("")
