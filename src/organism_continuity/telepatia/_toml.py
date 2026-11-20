# SPDX-License-Identifier: MIT
"""A strict TOML subset parser, used only on Python 3.10 where ``tomllib`` is missing.

Supported: comments, ``[table]`` and ``[dotted.table]`` headers with bare keys, and
``key = value`` lines whose value is a basic or literal single-line string, an integer, a float
or a boolean. Everything else (arrays, inline tables, multi-line strings, dotted keys, dates)
raises :class:`TOMLDecodeError`, so the kit fails closed instead of misreading a config. On
3.11+ the standard library parser is used and this module is only exercised by tests.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["TOMLDecodeError", "loads"]


class TOMLDecodeError(ValueError):
    """The text is not valid TOML or uses a construct outside the supported subset."""


_BARE = r"[A-Za-z0-9_-]+"
_HEADER_RE = re.compile(rf"^\[\s*({_BARE}(?:\s*\.\s*{_BARE})*)\s*\]\s*(?:#.*)?$")
_KEY_RE = re.compile(rf"^({_BARE})\s*=\s*(.*)$")
_INT_RE = re.compile(r"^[+-]?(?:0|[1-9](?:_?[0-9])*)$")
_FLOAT_RE = re.compile(r"^[+-]?(?:0|[1-9](?:_?[0-9])*)(?:\.[0-9](?:_?[0-9])*)?(?:[eE][+-]?[0-9](?:_?[0-9])*)?$")
_ESCAPES = {"b": "\b", "t": "\t", "n": "\n", "f": "\f", "r": "\r", '"': '"', "\\": "\\"}


def _rest_is_comment(rest: str, lineno: int) -> None:
    rest = rest.strip()
    if rest and not rest.startswith("#"):
        raise TOMLDecodeError(f"unexpected text after value (line {lineno})")


def _basic_string(src: str, lineno: int) -> tuple[str, str]:
    out: list[str] = []
    i = 1
    while i < len(src):
        ch = src[i]
        if ch == '"':
            return "".join(out), src[i + 1 :]
        if ch == "\\":
            nxt = src[i + 1 : i + 2]
            if nxt in _ESCAPES:
                out.append(_ESCAPES[nxt])
                i += 2
                continue
            if nxt in ("u", "U"):
                width = 4 if nxt == "u" else 8
                digits = src[i + 2 : i + 2 + width]
                if len(digits) != width or not re.fullmatch(r"[0-9A-Fa-f]+", digits):
                    raise TOMLDecodeError(f"bad unicode escape (line {lineno})")
                code = int(digits, 16)
                if 0xD800 <= code <= 0xDFFF or code > 0x10FFFF:
                    raise TOMLDecodeError(f"bad unicode escape (line {lineno})")
                out.append(chr(code))
                i += 2 + width
                continue
            raise TOMLDecodeError(f"bad escape (line {lineno})")
        if (ch < " " and ch != "\t") or ch == "\x7f":
            raise TOMLDecodeError(f"control character in string (line {lineno})")
        out.append(ch)
        i += 1
    raise TOMLDecodeError(f"unterminated string (line {lineno})")


def _value(src: str, lineno: int) -> Any:
    if src.startswith('"""') or src.startswith("'''"):
        raise TOMLDecodeError(f"multi-line strings are not supported (line {lineno})")
    if src.startswith('"'):
        val, rest = _basic_string(src, lineno)
        _rest_is_comment(rest, lineno)
        return val
    if src.startswith("'"):
        end = src.find("'", 1)
        if end < 0:
            raise TOMLDecodeError(f"unterminated string (line {lineno})")
        val = src[1:end]
        if any(c < " " and c != "\t" for c in val):
            raise TOMLDecodeError(f"control character in string (line {lineno})")
        _rest_is_comment(src[end + 1 :], lineno)
        return val
    word, _, _rest = src.partition("#")
    word = word.strip()
    if word == "true":
        return True
    if word == "false":
        return False
    if _INT_RE.match(word):
        return int(word.replace("_", ""))
    if _FLOAT_RE.match(word):
        return float(word.replace("_", ""))
    raise TOMLDecodeError(f"unsupported value (line {lineno})")


def loads(text: str) -> dict[str, Any]:
    """Parse ``text`` (the supported subset) into nested dicts."""
    root: dict[str, Any] = {}
    defined: set[tuple[str, ...]] = set()
    current = root
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            m = _HEADER_RE.match(line)
            if not m or line.startswith("[["):
                raise TOMLDecodeError(f"unsupported table header (line {lineno})")
            path = tuple(part.strip() for part in m.group(1).split("."))
            if path in defined:
                raise TOMLDecodeError(f"table defined twice (line {lineno})")
            defined.add(path)
            current = root
            for part in path:
                nxt = current.setdefault(part, {})
                if not isinstance(nxt, dict):
                    raise TOMLDecodeError(f"key redefined as table (line {lineno})")
                current = nxt
            continue
        m = _KEY_RE.match(line)
        if not m:
            raise TOMLDecodeError(f"unsupported line (line {lineno})")
        key, src = m.group(1), m.group(2).strip()
        if key in current:
            raise TOMLDecodeError(f"duplicate key (line {lineno})")
        current[key] = _value(src, lineno)
    return root
