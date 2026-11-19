# SPDX-License-Identifier: MIT
"""Agent config (``telepatia.toml``) and the peers file (``peers.toml``).

``telepatia.toml`` (one per agent, local, never committed)::

    [identity]
    name = "agent-a"
    key_file = "keys/agent-a.key"     # this agent's own signing key

    [spool]
    dir = "../spool"                  # shared root: inbox/, presence/, queue/

    [peers]
    file = "peers.toml"

``peers.toml`` holds ONLY a name and a key path per peer, never key material::

    [peers.agent-b]
    key_file = "keys/agent-b.key"

Relative paths resolve against the directory of the file that names them. There is no
switch that accepts unsigned messages: a config that tries to set one is rejected.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from organism_continuity.telepatia._compat import tomllib
from organism_continuity.telepatia.keys import KeyFileError, check_name, expand, load_key

DEFAULT_CONFIG = "~/.config/telepatia/telepatia.toml"
FORBIDDEN_KEYS = frozenset({"legacy_unsigned_wake", "allow_unsigned", "accept_unsigned"})
SECRET_KEYS = frozenset({"key", "secret", "token", "mac", "hmac_key", "password"})


class ConfigError(ValueError):
    """The config or peers file is missing, invalid, or asks for something unsafe."""

    pass


@dataclass(frozen=True)
class Config:
    """A loaded agent configuration with all paths resolved."""

    path: Path
    name: str
    key_file: Path
    spool: Path
    peers_file: Path
    peers: dict[str, Path] = field(default_factory=dict)

    def signing_key(self) -> bytes:
        """Load this agent's own signing key (refuses unsafe key files)."""
        return load_key(self.key_file)

    def keyring(self) -> dict[str, bytes]:
        """Peer name -> key. Unsafe or missing peer key files are skipped (never trusted)."""
        ring: dict[str, bytes] = {}
        for peer, path in self.peers.items():
            try:
                ring[peer] = load_key(path)
            except KeyFileError:
                continue
        return ring


def default_config_path() -> Path:
    """``$TELEPATIA_CONFIG`` or ``~/.config/telepatia/telepatia.toml``."""
    return expand(os.environ.get("TELEPATIA_CONFIG") or DEFAULT_CONFIG)


def _resolve(base: Path, value: str) -> Path:
    p = expand(value)
    return p if p.is_absolute() else (base / p)


def _walk_forbidden(obj: object, where: str = "") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FORBIDDEN_KEYS:
                raise ConfigError(f"unsupported_option: {where}{k} (signature checks cannot be turned off)")
            if k in SECRET_KEYS:
                raise ConfigError(f"inline_secret_refused: {where}{k} (use key_file)")
            _walk_forbidden(v, f"{where}{k}.")


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"config_missing: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"config_toml_invalid: {path}") from exc
    _walk_forbidden(data)
    return data


def load_peers(path: Path) -> dict[str, Path]:
    """Parse a peers file into ``{name: key_path}``. A missing file means no peers."""
    if not path.exists():
        return {}
    data = _read_toml(path)
    table = data.get("peers") or {}
    if not isinstance(table, dict):
        raise ConfigError("peers_must_be_table")
    out: dict[str, Path] = {}
    for name, entry in table.items():
        check_name(name)
        if not isinstance(entry, dict) or set(entry) != {"key_file"} or not isinstance(entry["key_file"], str):
            raise ConfigError(f"peer_entry_must_be_only_key_file: {name}")
        out[name] = _resolve(path.parent, entry["key_file"])
    return out


def load_config(path: str | Path | None = None) -> Config:
    """Load and validate an agent config; relative paths resolve against its directory."""
    cfg_path = (expand(path) if path else default_config_path()).absolute()
    data = _read_toml(cfg_path)
    base = cfg_path.parent
    ident = data.get("identity") or {}
    spool = data.get("spool") or {}
    peers = data.get("peers") or {}
    name = ident.get("name")
    key_file = ident.get("key_file")
    if not isinstance(name, str) or not isinstance(key_file, str):
        raise ConfigError("identity_name_and_key_file_required")
    check_name(name)
    spool_dir = spool.get("dir")
    if not isinstance(spool_dir, str) or not spool_dir:
        raise ConfigError("spool_dir_required")
    peers_file = _resolve(base, peers.get("file") or "peers.toml")
    return Config(
        path=cfg_path,
        name=name,
        key_file=_resolve(base, key_file),
        spool=_resolve(base, spool_dir),
        peers_file=peers_file,
        peers=load_peers(peers_file),
    )


def render_config(name: str, key_file: str, spool_dir: str, peers_file: str = "peers.toml") -> str:
    """Render the text of a new ``telepatia.toml``."""
    return (
        "[identity]\n"
        f'name = "{check_name(name)}"\n'
        f'key_file = "{key_file}"\n\n'
        "[spool]\n"
        f'dir = "{spool_dir}"\n\n'
        "[peers]\n"
        f'file = "{peers_file}"\n'
    )


def add_peer(peers_file: Path, name: str, key_file: str) -> None:
    """Append ``[peers.<name>] key_file = ...``; refuses a duplicate name."""
    check_name(name)
    existing = load_peers(peers_file) if peers_file.exists() else {}
    if name in existing:
        raise ConfigError(f"peer_exists: {name}")
    if '"' in key_file or "\n" in key_file:
        raise ConfigError("peer_key_path_invalid")
    peers_file.parent.mkdir(parents=True, exist_ok=True)
    with open(peers_file, "a", encoding="utf-8") as fh:
        fh.write(f'\n[peers.{name}]\nkey_file = "{key_file}"\n')
    os.chmod(peers_file, 0o600)


def remove_peer(peers_file: Path, name: str) -> bool:
    """Rewrite the peers file without ``name``. Returns True if it was present."""
    peers = load_peers(peers_file)
    if name not in peers:
        return False
    text = peers_file.read_text(encoding="utf-8")
    data = tomllib.loads(text).get("peers", {})
    data.pop(name, None)
    out = "".join(f'[peers.{n}]\nkey_file = "{e["key_file"]}"\n\n' for n, e in data.items())
    peers_file.write_text(out, encoding="utf-8")
    os.chmod(peers_file, 0o600)
    return True
