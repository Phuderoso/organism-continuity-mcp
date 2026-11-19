# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import pytest

from organism_continuity.telepatia import config
from organism_continuity.telepatia.config import ConfigError, load_config


def write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


BASE = '[identity]\nname = "agent-a"\nkey_file = "keys/agent-a.key"\n[spool]\ndir = "../spool"\n'


def test_relative_paths_resolve_against_config_dir(tmp_path: Path) -> None:
    cfg = load_config(write(tmp_path / "a" / "telepatia.toml", BASE))
    assert cfg.key_file == tmp_path / "a" / "keys" / "agent-a.key"
    assert cfg.spool == tmp_path / "a" / ".." / "spool"
    assert cfg.peers == {}


@pytest.mark.parametrize(
    "extra",
    [
        "[wake]\nlegacy_unsigned_wake = true\n",
        "[identity2]\nallow_unsigned = true\n",
        "[x.y]\naccept_unsigned = false\n",
    ],
)
def test_unsigned_switches_are_rejected(tmp_path: Path, extra: str) -> None:
    with pytest.raises(ConfigError, match="unsupported_option"):
        load_config(write(tmp_path / "c.toml", BASE + extra))


def test_inline_secret_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="inline_secret"):
        load_config(
            write(tmp_path / "c.toml", BASE.replace('key_file = "keys/agent-a.key"', 'key_file = "k"\nkey = "00"'))
        )


def test_peers_only_name_and_key_file(tmp_path: Path) -> None:
    write(tmp_path / "peers.toml", '[peers.agent-b]\nkey_file = "keys/agent-b.key"\n')
    cfg = load_config(write(tmp_path / "c.toml", BASE))
    assert cfg.peers == {"agent-b": tmp_path / "keys" / "agent-b.key"}
    write(tmp_path / "peers.toml", '[peers.agent-b]\nkey_file = "k"\nlabel = "x"\n')
    with pytest.raises(ConfigError, match="only_key_file"):
        load_config(tmp_path / "c.toml")


@pytest.mark.parametrize(
    "text,err",
    [
        ("not toml [", "invalid"),
        ("[identity]\nname='agent-a'\n", "identity"),
        ('[identity]\nname="agent-a"\nkey_file="k"\n', "spool"),
    ],
)
def test_invalid_configs(tmp_path: Path, text: str, err: str) -> None:
    with pytest.raises(ConfigError, match=err):
        load_config(write(tmp_path / "c.toml", text))


def test_missing_config(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="missing"):
        load_config(tmp_path / "none.toml")


def test_default_path_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TELEPATIA_CONFIG", str(tmp_path / "x.toml"))
    assert config.default_config_path() == tmp_path / "x.toml"


def test_add_and_remove_peer(tmp_path: Path) -> None:
    pf = tmp_path / "peers.toml"
    config.add_peer(pf, "agent-b", "/k/agent-b.key")
    config.add_peer(pf, "agent-c", "/k/agent-c.key")
    with pytest.raises(ConfigError, match="peer_exists"):
        config.add_peer(pf, "agent-b", "/k/x.key")
    with pytest.raises(ConfigError, match="invalid"):
        config.add_peer(pf, "agent-d", 'bad"path')
    assert config.remove_peer(pf, "agent-b") is True
    assert config.remove_peer(pf, "agent-b") is False
    assert set(config.load_peers(pf)) == {"agent-c"}
    assert (pf.stat().st_mode & 0o777) == 0o600


def test_peers_table_shape(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="table"):
        config.load_peers(write(tmp_path / "p.toml", 'peers = "x"\n'))


def test_keyring_skips_unsafe_peer_key(tmp_path: Path, pair) -> None:
    _a, b = pair
    (b.peers["agent-a"]).chmod(0o644)
    assert b.keyring() == {}
