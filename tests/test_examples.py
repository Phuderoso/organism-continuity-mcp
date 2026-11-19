# SPDX-License-Identifier: MIT
from __future__ import annotations

import shutil
from pathlib import Path

from organism_continuity.telepatia.config import load_config

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "telepatia"


def test_example_configs_load(tmp_path: Path) -> None:
    for agent, peer in (("a", "b"), ("b", "a")):
        d = tmp_path / agent
        d.mkdir()
        shutil.copy(EXAMPLES / f"agent-{agent}.example.toml", d / "telepatia.toml")
        shutil.copy(EXAMPLES / f"peers-{agent}.example.toml", d / "peers.toml")
        cfg = load_config(d / "telepatia.toml")
        assert cfg.name == f"agent-{agent}"
        assert list(cfg.peers) == [f"agent-{peer}"]


def test_examples_contain_no_key_material() -> None:
    import re

    for f in (p for p in EXAMPLES.parent.rglob("*") if p.is_file()):
        assert not re.search(r"\b[0-9a-f]{64}\b", f.read_text()), f.name


def test_handoff_example_section_loads(tmp_path: Path) -> None:
    import argparse

    from organism_continuity.handoff.cli import settings

    d = tmp_path / "a"
    d.mkdir()
    text = (
        (EXAMPLES / "agent-a.example.toml").read_text()
        + "\n"
        + (EXAMPLES.parent / "handoff" / "handoff.example.toml").read_text()
    )
    (d / "telepatia.toml").write_text(text)
    shutil.copy(EXAMPLES / "peers-a.example.toml", d / "peers.toml")
    args = argparse.Namespace(config=str(d / "telepatia.toml"), lane=None, dir=None)
    hdir, lanes, th, cfg = settings(args)
    assert hdir == d / ".." / "handoffs" and set(lanes) == {"long", "fresh"} and th.log_warn_mb == 40
    assert cfg is not None and cfg.name == "agent-a"
