# SPDX-License-Identifier: MIT
"""Per-sender HMAC keys: generate, load, fingerprint, rotate, revoke.

Format: one file per identity, ``<keys_dir>/<name>.key``; content is 64 lowercase hex chars
(32 random bytes) plus a newline. The file must be a regular file (not a symlink), owned by
the current user, mode 0600. The keys directory is created 0700.

The secret is never printed: callers only ever see the name, the path, the mode and a
fingerprint (domain-separated sha256, truncated to 16 hex chars).
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import secrets
import stat
import tempfile
from pathlib import Path

KEY_BYTES = 32
MIN_KEY_BYTES = 32
FP_DOMAIN = b"telepatia-key-fingerprint/v1\n"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
KEY_FILE_MODE = 0o600
KEY_DIR_MODE = 0o700


class KeyFileError(ValueError):
    """A key file is missing, unsafe or malformed. The message never contains key material."""


def check_name(name: str) -> str:
    """Agent names are lowercase ``[a-z0-9._-]``, 1..64 chars. Returns the name unchanged."""
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise ValueError(f"invalid_agent_name: {name!r} (use lowercase [a-z0-9._-], max 64)")
    return name


def expand(path: str | Path) -> Path:
    """Expand ``~`` and environment variables in a path."""
    return Path(os.path.expanduser(os.path.expandvars(str(path))))


def fingerprint(key: bytes) -> str:
    """Public, non-reversible id of a key. Safe to log and to compare out-of-band."""
    return hashlib.sha256(FP_DOMAIN + key).hexdigest()[:16]


def inside_git_worktree(path: Path) -> bool:
    """True when ``path`` (or a parent) contains a ``.git`` entry: keys must live outside repos."""
    p = expand(path).resolve()
    return any((parent / ".git").exists() for parent in (p, *p.parents))


def ensure_private_dir(path: str | Path) -> Path:
    """Create ``path`` (and parents) and force mode 0700 on the leaf. Refuses a symlinked leaf."""
    d = expand(path)
    d.mkdir(parents=True, exist_ok=True, mode=KEY_DIR_MODE)
    st = os.lstat(d)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise KeyFileError(f"key_dir_not_a_directory: {d}")
    os.chmod(d, KEY_DIR_MODE)
    return d


def load_key(path: str | Path) -> bytes:
    """Load a key file, refusing anything that is not a private regular file with >= 32 bytes."""
    target = expand(path)
    try:
        st = os.lstat(target)
    except OSError as exc:
        raise KeyFileError(f"key_file_missing: {target}") from exc
    if not stat.S_ISREG(st.st_mode):
        raise KeyFileError(f"key_file_not_regular: {target}")
    if st.st_mode & 0o077:
        raise KeyFileError(f"key_file_mode_too_open: {target} must be 0600")
    if hasattr(os, "getuid") and st.st_uid != os.getuid():
        raise KeyFileError(f"key_file_wrong_owner: {target}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(target, flags)
    except OSError as exc:
        raise KeyFileError(f"key_file_unreadable: {target}") from exc
    try:
        raw = os.read(fd, 4096)
    finally:
        os.close(fd)
    try:
        key = bytes.fromhex(raw.decode("ascii").strip())
    except (UnicodeDecodeError, ValueError) as exc:
        raise KeyFileError(f"key_file_not_hex: {target}") from exc
    if len(key) < MIN_KEY_BYTES:
        raise KeyFileError(f"key_file_too_short: {target}")
    return key


def _write_new_key(dest: Path, *, replace: bool = False) -> bytes:
    """Atomic write of a fresh key next to ``dest`` (tmp 0600 + fsync + replace)."""
    key = secrets.token_bytes(KEY_BYTES)
    fd, tmp = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".tmp", dir=str(dest.parent))
    try:
        os.fchmod(fd, KEY_FILE_MODE)
        os.write(fd, (key.hex() + "\n").encode("ascii"))
        os.fsync(fd)
        os.close(fd)
        fd = -1
        if replace:
            os.replace(tmp, dest)
            tmp = ""
        else:
            os.link(tmp, dest, follow_symlinks=False)  # atomic no-overwrite, even under a race
            os.unlink(tmp)
            tmp = ""
    finally:
        if fd >= 0:
            os.close(fd)
        if tmp:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
    return key


def key_path(keys_dir: str | Path, name: str) -> Path:
    """``<keys_dir>/<name>.key`` after validating ``name``."""
    return expand(keys_dir) / f"{check_name(name)}.key"


def generate_key(keys_dir: str | Path, name: str, *, allow_in_worktree: bool = False) -> dict[str, str]:
    """Create ``<keys_dir>/<name>.key``. Never overwrites (use ``rotate_key``)."""
    dest = key_path(keys_dir, name)
    if not allow_in_worktree and inside_git_worktree(dest.parent):
        raise KeyFileError(f"key_dir_inside_git_worktree: {dest.parent}")
    ensure_private_dir(dest.parent)
    if os.path.lexists(dest):
        raise FileExistsError(f"key_exists: {dest} (use rotate to replace it)")
    key = _write_new_key(dest)
    return {"name": name, "path": str(dest), "mode": "0600", "fingerprint": fingerprint(key)}


def rotate_key(keys_dir: str | Path, name: str) -> dict[str, str]:
    """Replace an existing key atomically; report old and new fingerprints only."""
    dest = key_path(keys_dir, name)
    old = load_key(dest)
    key = _write_new_key(dest, replace=True)
    return {
        "name": name,
        "path": str(dest),
        "mode": "0600",
        "fingerprint": fingerprint(key),
        "replaced_fingerprint": fingerprint(old),
    }


def revoke_key(keys_dir: str | Path, name: str) -> dict[str, str]:
    """Overwrite (best effort; not a guarantee on SSDs/copy-on-write filesystems) and delete."""
    dest = key_path(keys_dir, name)
    st = os.lstat(dest)
    if not stat.S_ISREG(st.st_mode):
        raise KeyFileError(f"key_file_not_regular: {dest}")
    fp = ""
    with contextlib.suppress(KeyFileError):
        fp = fingerprint(load_key(dest))
    fd = os.open(dest, os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.write(fd, b"0" * max(st.st_size, KEY_BYTES * 2))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.unlink(dest)
    return {"name": name, "path": str(dest), "revoked_fingerprint": fp}
