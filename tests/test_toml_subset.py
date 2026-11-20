# SPDX-License-Identifier: MIT
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from organism_continuity.telepatia import _toml
from organism_continuity.telepatia.config import render_config

EXAMPLES = sorted((Path(__file__).parent.parent / "examples").glob("**/*.toml"))
SAMPLES = [
    render_config("agent-a", "/k/agent-a.key", "/s", "peers.toml"),
    '[a]\nx = "q\\"\\\\\\n\\t\\u00e9\\U0001F600" # c\ny = \'lit #\'\nn = -1_000\nf = 1.5e3\nb = true\nc = false\n',
    "[handoff.thresholds]\nlog_warn_mb = 8\ncheckpoints_handoff = 40\n[handoff]\ndir = 'x'\n",
    "# only a comment\n\n",
]


@pytest.mark.parametrize("text", SAMPLES + [p.read_text() for p in EXAMPLES])
def test_subset_matches_stdlib(text: str) -> None:
    got = _toml.loads(text)
    if sys.version_info >= (3, 11):
        import tomllib

        assert got == tomllib.loads(text)
    assert isinstance(got, dict)


@pytest.mark.parametrize(
    "text",
    [
        "x = [1, 2]\n",
        "x = {a = 1}\n",
        'x = """m"""\n',
        "a.b = 1\n",
        "[[t]]\n",
        "[t]\n[t]\n",
        "x = 1\nx = 2\n",
        'x = "open\n',
        "x = 'open\n",
        'x = "\\q"\n',
        'x = "\\ud800"\n',
        'x = "\\u12"\n',
        "x = 1979-05-27\n",
        "x = 1 2\n",
        'x = "a" b\n',
        "x = 01\n",
        "nonsense\n",
        "[bad header\n",
        'x = "\x01"\n',
        "x = 'a\x01'\n",
        "x = 1\n[x]\n",
        'x = "\\U00110000"\n',
    ],
)
def test_subset_rejects(text: str) -> None:
    with pytest.raises(_toml.TOMLDecodeError):
        _toml.loads(text)
    if sys.version_info >= (3, 11) and text not in (
        "x = [1, 2]\n",
        "x = {a = 1}\n",
        'x = """m"""\n',
        "a.b = 1\n",
        "[[t]]\n",
        "x = 1979-05-27\n",
    ):
        import tomllib

        with pytest.raises(tomllib.TOMLDecodeError):
            tomllib.loads(text)
