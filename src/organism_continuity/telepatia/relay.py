# SPDX-License-Identifier: MIT
"""Relayed texts: one agent posts a message on behalf of another, optionally signed.

A relay body has this shape (the first line is the marker)::

    <!-- telepatia-relay -->
    <!-- reply-to: 1234 -->          (optional)
    **from: <origin>**
    to: <recipient>                  (optional)

    <message>

It is **unsigned by default**. Signing is an explicit opt-in per call (``sign=True``) and always
signs as the *relayer*, with the relayer's own key, using the ordinary ``telepatia-sig v=1``
trailer (:func:`organism_continuity.telepatia.signing.sign_text`). A verifier therefore learns
that the relayer vouched for the text; the ``from:`` line names the origin for information only
and never grants the origin's authority.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from organism_continuity.telepatia import signing

RELAY_MARK = "<!-- telepatia-relay -->"
_REPLY_RE = re.compile(r"^<!-- reply-to: (?P<id>\d{1,20}) -->$")
_FROM_RE = re.compile(r"^\*\*from: (?P<name>[^\n]+)\*\*$")
_TO_RE = re.compile(r"^to: (?P<name>[^\n]+)$")


@dataclass(frozen=True)
class Relay:
    """A parsed relay body."""

    origin: str
    to: str
    reply_to: int | None
    message: str


def _label(value: str, what: str) -> str:
    raw = str(value or "")
    text = " ".join(raw.split())
    if not text or "\n" in raw or "\r" in raw or "<!--" in text or "-->" in text or "*" in text:
        raise ValueError(f"relay_{what}_invalid")
    return text


def format_relay(origin: str, message: str, *, to: str = "", reply_to: int | None = None) -> str:
    """Build the unsigned relay body. Refuses a message that already ends in a signature trailer."""
    origin = _label(origin, "origin")
    msg = (message or "").strip("\n")
    if not msg.strip():
        raise ValueError("relay_message_required")
    lines = [RELAY_MARK]
    if reply_to is not None:
        if isinstance(reply_to, bool) or int(reply_to) < 0:
            raise ValueError("relay_reply_to_invalid")
        lines.append(f"<!-- reply-to: {int(reply_to)} -->")
    lines.append(f"**from: {origin}**")
    if to:
        lines.append(f"to: {_label(to, 'to')}")
    body = "\n".join(lines) + f"\n\n{msg}\n"
    if signing.split_signature(body)[1] is not None:
        # a trailer typed into the message would read as a signature by someone else
        raise ValueError("relay_message_has_sig_trailer")
    return body


def is_relay(text: str) -> bool:
    """True when the first line of ``text`` is the relay marker."""
    return (text or "").split("\n", 1)[0].strip() == RELAY_MARK


def parse_relay(content: str) -> Relay | None:
    """Parse a relay body (signature trailer already removed). None when it is not one."""
    if not is_relay(content):
        return None
    head, sep, message = content.partition("\n\n")
    if not sep:
        return None
    lines = head.split("\n")[1:]
    reply_to: int | None = None
    if lines and (m := _REPLY_RE.match(lines[0])):
        reply_to = int(m.group("id"))
        lines = lines[1:]
    if not lines or not (f := _FROM_RE.match(lines[0])):
        return None
    to = ""
    if len(lines) == 2 and (t := _TO_RE.match(lines[1])):
        to = t.group("name")
    elif len(lines) != 1:
        return None
    message = message[:-1] if message.endswith("\n") else message
    if not message.strip():
        return None
    return Relay(f.group("name"), to, reply_to, message)


def sign_relay(body: str, relayer: str, key: bytes, *, ts: int | None = None, nonce: str | None = None) -> str:
    """Append a ``telepatia-sig v=1`` trailer to a relay body, signed as ``relayer``."""
    if parse_relay(body) is None:
        raise ValueError("not_a_relay_body")
    return signing.sign_text(body, relayer, key, ts=ts, nonce=nonce)


def relay_text(
    origin: str,
    message: str,
    *,
    to: str = "",
    reply_to: int | None = None,
    sign: bool = False,
    relayer: str | None = None,
    key: bytes | None = None,
) -> str:
    """Relay body for ``origin``; signed as ``relayer`` only when ``sign`` is True (opt-in per call)."""
    body = format_relay(origin, message, to=to, reply_to=reply_to)
    if not sign:
        return body
    if not relayer or key is None:
        raise ValueError("relay_sign_needs_relayer_and_key")
    return sign_relay(body, relayer, key)
