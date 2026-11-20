# SPDX-License-Identifier: MIT
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from organism_continuity.telepatia import keys


def mode(p: Path) -> int:
    return stat.S_IMODE(os.lstat(p).st_mode)


def test_generate_creates_private_file_and_dir(tmp_path: Path) -> None:
    info = keys.generate_key(tmp_path / "k", "agent-a")
    path = Path(info["path"])
    assert mode(path) == 0o600
    assert mode(path.parent) == 0o700
    assert len(keys.load_key(path)) == 32
    assert info["fingerprint"] == keys.fingerprint(keys.load_key(path))
    assert path.read_text().strip() not in str(info)


def test_generate_never_overwrites(tmp_path: Path) -> None:
    keys.generate_key(tmp_path, "agent-a")
    with pytest.raises(FileExistsError):
        keys.generate_key(tmp_path, "agent-a")


def test_generate_refuses_git_worktree(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    with pytest.raises(keys.KeyFileError, match="worktree"):
        keys.generate_key(tmp_path / "keys", "agent-a")
    assert keys.generate_key(tmp_path / "keys", "agent-a", allow_in_worktree=True)


@pytest.mark.parametrize("bad", ["", "Agent", "a b", "../x", "x" * 65, "-x"])
def test_bad_names(bad: str) -> None:
    with pytest.raises(ValueError):
        keys.check_name(bad)


def test_load_refuses_open_mode(tmp_path: Path) -> None:
    p = Path(keys.generate_key(tmp_path, "agent-a")["path"])
    os.chmod(p, 0o644)
    with pytest.raises(keys.KeyFileError, match="mode_too_open"):
        keys.load_key(p)


def test_load_refuses_symlink(tmp_path: Path) -> None:
    p = Path(keys.generate_key(tmp_path, "agent-a")["path"])
    link = tmp_path / "link.key"
    link.symlink_to(p)
    with pytest.raises(keys.KeyFileError, match="not_regular"):
        keys.load_key(link)


def test_load_refuses_short_and_non_hex(tmp_path: Path) -> None:
    for content, reason in (("abcd\n", "too_short"), ("zz" * 32 + "\n", "not_hex")):
        p = tmp_path / f"{reason}.key"
        p.write_text(content)
        os.chmod(p, 0o600)
        with pytest.raises(keys.KeyFileError, match=reason):
            keys.load_key(p)


def test_load_missing(tmp_path: Path) -> None:
    with pytest.raises(keys.KeyFileError, match="missing"):
        keys.load_key(tmp_path / "nope.key")


def test_rotate_changes_key_and_reports_fingerprints(tmp_path: Path) -> None:
    first = keys.generate_key(tmp_path, "agent-a")
    rotated = keys.rotate_key(tmp_path, "agent-a")
    assert rotated["replaced_fingerprint"] == first["fingerprint"]
    assert rotated["fingerprint"] != first["fingerprint"]
    assert mode(Path(rotated["path"])) == 0o600
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


def test_revoke_deletes(tmp_path: Path) -> None:
    info = keys.generate_key(tmp_path, "agent-a")
    out = keys.revoke_key(tmp_path, "agent-a")
    assert out["revoked_fingerprint"] == info["fingerprint"]
    assert not Path(info["path"]).exists()


def test_revoke_refuses_symlink(tmp_path: Path) -> None:
    target = Path(keys.generate_key(tmp_path / "real", "agent-a")["path"])
    (tmp_path / "agent-b.key").symlink_to(target)
    with pytest.raises(keys.KeyFileError):
        keys.revoke_key(tmp_path, "agent-b")
    assert target.exists()


def test_ensure_private_dir_refuses_symlink(tmp_path: Path) -> None:
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")
    with pytest.raises(keys.KeyFileError):
        keys.ensure_private_dir(tmp_path / "link")


def test_fixture_cleanup_shreds_keys(tmp_path: Path) -> None:
    from conftest import _shred_keys

    keys.generate_key(tmp_path / "k", "agent-z")
    assert _shred_keys(tmp_path) == 1 and not list(tmp_path.rglob("*.key"))
