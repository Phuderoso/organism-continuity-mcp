# SPDX-License-Identifier: MIT
"""Shared fixtures: two fictional agents, ``agent-a`` and ``agent-b``, on one spool."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from organism_continuity.telepatia import cli
from organism_continuity.telepatia.config import Config, load_config


def _init(tmp: Path, name: str, spool: Path) -> Path:
    cfg = tmp / name / "telepatia.toml"
    assert cli.main(["init", "--name", name, "--config", str(cfg), "--spool", str(spool)]) == 0
    return cfg


def _shred_keys(root: Path) -> int:
    """Overwrite and delete every test key file under ``root``; returns how many were removed."""
    n = 0
    for key in root.rglob("*.key"):
        if key.is_file() and not key.is_symlink():
            key.write_bytes(b"\0" * key.stat().st_size)
            key.unlink()
            n += 1
    return n


@pytest.fixture(autouse=True)
def _no_test_keys_left_behind(request: pytest.FixtureRequest) -> Iterator[None]:
    """Remove test keys after each test that used ``tmp_path`` (pytest retains tmp dirs)."""
    root = request.getfixturevalue("tmp_path") if "tmp_path" in request.fixturenames else None
    yield
    if root is not None:
        _shred_keys(root)


@pytest.fixture
def pair(tmp_path: Path) -> tuple[Config, Config]:
    spool = tmp_path / "spool"
    a = _init(tmp_path, "agent-a", spool)
    b = _init(tmp_path, "agent-b", spool)
    assert (
        cli.main(
            ["peer", "add", "agent-a", "--key-file", str(tmp_path / "agent-a/keys/agent-a.key"), "--config", str(b)]
        )
        == 0
    )
    assert (
        cli.main(
            ["peer", "add", "agent-b", "--key-file", str(tmp_path / "agent-b/keys/agent-b.key"), "--config", str(a)]
        )
        == 0
    )
    return load_config(a), load_config(b)
