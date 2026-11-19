# SPDX-License-Identifier: MIT
"""``telepatia-sig v=1`` signing and verification (the single signature format of v0.5).

A signed text ends with exactly one trailer line, its last non-empty line::

    <!-- telepatia-sig v=1 from=<name> ts=<unix> nonce=<hex> mac=<hex64> -->

The MAC is HMAC-SHA256 with the signer's key over the canonical form::

    "telepatia-sig/v1\\n" + base_key(from) + "\\n" + decimal(ts) + "\\n" + nonce + "\\n"
    + hex(sha256(utf8(content)))

where ``content`` is every byte above the trailer line, ending in exactly one ``\\n``. This is
byte-for-byte the canal format; ``docs/PROTOCOL.md`` is the normative specification.

On top of it, the file spool uses a stricter *content profile* (``to:`` / ``from:`` header
lines, a blank line, then the body) and a stricter trailer (canonical ``ts`` without leading
zeros, canonical lowercase ``from``). Freshness is always measured against a *transport*
time supplied by the caller (for the spool: the file's mtime), never against the signed ``ts``
alone, and a nonce store is mandatory.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass

from organism_continuity.telepatia.keys import NAME_RE, check_name

SIG_VERSION = 1
DOMAIN = "telepatia-sig/v1"
WINDOW_S = 600  # |transport_time - ts| must not exceed this, in both directions
MAX_MESSAGE_BYTES = 64 * 1024
MAX_BODY_CHARS = 32 * 1024

# Grammar of the canal (accepts what any v=1 signer may emit).
SIG_LINE_RE = re.compile(
    r"^<!--\s*telepatia-sig\s+v=1\s+from=(?P<from>[^\s<>]+)\s+ts=(?P<ts>\d{1,12})\s+"
    r"nonce=(?P<nonce>[0-9a-f]{16,64})\s+mac=(?P<mac>[0-9a-f]{64})\s*-->$"
)
CANONICAL_TS_RE = re.compile(r"^(0|[1-9][0-9]{0,11})$")

VERIFIED = "verified"
UNSIGNED = "unsigned"
MALFORMED = "malformed"
TOO_LARGE = "too_large"
UNKNOWN_KEY = "unknown_key"
BAD_MAC = "bad_mac"
SENDER_MISMATCH = "sender_mismatch"
WRONG_RECIPIENT = "wrong_recipient"
STALE = "stale"
REPLAYED_NONCE = "replayed_nonce"
REJECT_REASONS = (
    UNSIGNED,
    MALFORMED,
    TOO_LARGE,
    UNKNOWN_KEY,
    BAD_MAC,
    SENDER_MISMATCH,
    WRONG_RECIPIENT,
    STALE,
    REPLAYED_NONCE,
)


# --- canal primitives (byte-for-byte compatible) --------------------------------------------


def base_key(value: str) -> str:
    """Name key used inside the MAC.

    Collapse runs of whitespace to one space and trim, ``casefold()``, strip the characters
    ``*``, backtick, ``'`` and ``"`` from both ends, then remove one trailing ``[...]`` tag and
    trim again. Aliases never enter the MAC.
    """
    key = " ".join((value or "").split()).casefold().strip("*`'\"")
    return re.sub(r"\s*\[[^\]]*\]$", "", key).strip()


def canonical_bytes(signer: str, ts: int, nonce: str, content: str) -> bytes:
    """The exact bytes covered by the MAC. Raises ``UnicodeEncodeError`` for lone surrogates."""
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return f"{DOMAIN}\n{base_key(signer)}\n{ts}\n{nonce}\n{digest}".encode()


def compute_mac(key: bytes, signer: str, ts: int, nonce: str, content: str) -> str:
    """Hex HMAC-SHA256 over :func:`canonical_bytes`."""
    return hmac.new(key, canonical_bytes(signer, ts, nonce, content), hashlib.sha256).hexdigest()


def split_signature(text: str) -> tuple[str, re.Match[str] | None]:
    """(content above the trailer, trailer match or None). Only the last non-empty line counts."""
    stripped = (text or "").rstrip("\n")
    head, _, last = stripped.rpartition("\n")
    match = SIG_LINE_RE.match(last.strip())
    if not match:
        return text or "", None
    return (head + "\n") if head else "", match


def sign_text(text: str, signer: str, key: bytes, *, ts: int | None = None, nonce: str | None = None) -> str:
    """Append (or replace) the trailer. Content gets exactly one final ``\\n`` added if missing."""
    if not re.fullmatch(r"[^\s<>]+", signer or ""):
        raise ValueError("signer name cannot be empty or contain spaces or <>")
    content, _ = split_signature(text)
    if not content.endswith("\n"):
        content += "\n"
    ts = int(time.time()) if ts is None else int(ts)
    nonce = nonce or secrets.token_hex(16)
    try:
        mac = compute_mac(key, signer, ts, nonce, content)
    except UnicodeEncodeError as exc:
        raise ValueError("content_not_utf8_encodable") from exc
    return f"{content}<!-- telepatia-sig v={SIG_VERSION} from={signer} ts={ts} nonce={nonce} mac={mac} -->\n"


# --- spool content profile --------------------------------------------------------------------


@dataclass(frozen=True)
class Message:
    """One verified (or parseable) spool message."""

    id: str
    sender: str
    to: str
    ts: int
    nonce: str
    body: str
    mac: str


@dataclass(frozen=True)
class Check:
    """Outcome of :func:`verify`: a status and, when parseable, the message."""

    status: str
    message: Message | None = None

    @property
    def verified(self) -> bool:
        """True only for status ``verified``."""
        return self.status == VERIFIED


def build_content(sender: str, to: str, body: str) -> str:
    """Spool content profile: ``to:`` line, ``from:`` line, blank line, body, final newline."""
    check_name(sender)
    check_name(to)
    if not isinstance(body, str) or not body.strip():
        raise ValueError("empty_body")
    if len(body) > MAX_BODY_CHARS:
        raise ValueError("body_too_long")
    text = f"to: {to}\nfrom: {sender}\n\n{body}"
    return text if text.endswith("\n") else text + "\n"


def sign(sender: str, to: str, body: str, key: bytes, *, ts: int | None = None, nonce: str | None = None) -> str:
    """Return the full signed spool message text from ``sender`` to ``to``."""
    return sign_text(build_content(sender, to, body), sender, key, ts=ts, nonce=nonce)


_PROFILE_RE = re.compile(r"\Ato: (?P<to>[^\n]*)\nfrom: (?P<from>[^\n]*)\n\n(?P<body>.*)\Z", re.DOTALL)


def parse(raw: bytes) -> tuple[str, Message | None]:
    """Grammar check only (no key). Returns (status, message) with status ``ok`` or a reason."""
    if len(raw) > MAX_MESSAGE_BYTES:
        return TOO_LARGE, None
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return MALFORMED, None
    content, sig = split_signature(text)
    if sig is None:
        return UNSIGNED, None
    signer, ts_raw, nonce, mac = sig.group("from"), sig.group("ts"), sig.group("nonce"), sig.group("mac")
    # strict spool profile: canonical ts and canonical (already lowercase, valid) signer
    if not CANONICAL_TS_RE.match(ts_raw) or not NAME_RE.match(signer) or base_key(signer) != signer:
        return MALFORMED, None
    m = _PROFILE_RE.match(content)
    if not m or not NAME_RE.match(m.group("to")) or not NAME_RE.match(m.group("from")):
        return MALFORMED, None
    body = m.group("body")
    body = body[:-1] if body.endswith("\n") else body
    if not body.strip():
        return MALFORMED, None
    return "ok", Message(nonce, m.group("from"), m.group("to"), int(ts_raw), nonce, body, mac)


def verify(
    raw: bytes,
    *,
    me: str,
    keyring: dict[str, bytes],
    transport_time: float,
    seen_nonce: Callable[[str, str], bool],
) -> Check:
    """Verify one raw spool message for recipient ``me`` (normative order, docs/PROTOCOL.md 6).

    ``transport_time`` is when the transport says the message arrived (for the spool: the
    file's mtime). The signed ``ts`` must be within ``WINDOW_S`` of it in both directions.
    ``seen_nonce(signer, nonce)`` is mandatory and is consulted only after the MAC is valid.
    """
    status, msg = parse(raw)
    if msg is None:
        return Check(status)
    text = raw.decode("utf-8")
    content, sig = split_signature(text)
    assert sig is not None
    signer = sig.group("from")
    key = keyring.get(base_key(signer))
    if key is None:
        return Check(UNKNOWN_KEY, msg)
    try:
        expected = compute_mac(key, signer, int(sig.group("ts")), sig.group("nonce"), content)
    except UnicodeEncodeError:  # pragma: no cover - strict UTF-8 decode above excludes surrogates
        return Check(MALFORMED, msg)
    if not hmac.compare_digest(expected, sig.group("mac")):
        return Check(BAD_MAC, msg)
    if base_key(signer) != base_key(msg.sender):
        return Check(SENDER_MISMATCH, msg)
    if msg.to != me:
        return Check(WRONG_RECIPIENT, msg)
    if abs(float(transport_time) - msg.ts) > WINDOW_S:
        return Check(STALE, msg)
    if seen_nonce(base_key(signer), msg.nonce):
        return Check(REPLAYED_NONCE, msg)
    return Check(VERIFIED, msg)
