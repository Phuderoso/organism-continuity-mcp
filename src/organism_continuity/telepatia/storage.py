# SPDX-License-Identifier: MIT
"""Small filesystem helpers: private dirs, atomic writes, exclusive locks, safe reads."""

from __future__ import annotations

import contextlib
import fcntl
import os
import stat
import tempfile
from collections.abc import Iterator
from pathlib import Path

FILE_MODE = 0o600
DIR_MODE = 0o700


class UnsafePath(RuntimeError):
    """A path is a symlink, not a directory, or owned by someone else."""

    pass


def private_dir(path: str | Path) -> Path:
    """mkdir -p with mode 0700 on the leaf; refuses a symlink or non-directory at ``path``."""
    d = Path(path)
    d.mkdir(parents=True, exist_ok=True, mode=DIR_MODE)
    st = os.lstat(d)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise UnsafePath(f"not_a_directory: {d}")
    if hasattr(os, "getuid") and st.st_uid != os.getuid():
        raise UnsafePath(f"wrong_owner: {d}")
    os.chmod(d, DIR_MODE)
    return d


def require_dir(path: str | Path) -> Path:
    """An existing real directory (no symlink) owned by us, or ``UnsafePath``/``FileNotFoundError``."""
    d = Path(path)
    st = os.lstat(d)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise UnsafePath(f"not_a_directory: {d}")
    if hasattr(os, "getuid") and st.st_uid != os.getuid():
        raise UnsafePath(f"wrong_owner: {d}")
    return d


def fsync_dir(d: Path) -> None:
    """Best-effort fsync of a directory so a rename is durable."""
    try:
        fd = os.open(str(d), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write(dest: Path, data: bytes, *, mode: int = FILE_MODE) -> Path:
    """tmp (dotfile, same dir) + fsync + rename + directory fsync. Readers never see partial files."""
    fd, tmp = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".tmp", dir=str(dest.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            os.fchmod(fh.fileno(), mode)
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, dest)
        tmp = ""
        fsync_dir(dest.parent)
    finally:
        if tmp:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
    return dest


@contextlib.contextmanager
def locked(lock_path: Path) -> Iterator[None]:
    """Hold an exclusive ``flock`` on ``lock_path`` for the duration of the block."""
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0), FILE_MODE)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def read_regular_stat(path: Path, max_bytes: int) -> tuple[bytes, os.stat_result] | None:
    """Read a regular file without following symlinks, returning its bytes and ``fstat``.

    None if the path is a symlink or special file, larger than ``max_bytes``, swapped between
    ``lstat`` and ``open``, or unreadable.
    """
    try:
        st = os.lstat(path)
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode) or st.st_size > max_bytes:
        return None
    try:
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return None
    try:
        fst = os.fstat(fd)
        if not stat.S_ISREG(fst.st_mode) or (fst.st_dev, fst.st_ino) != (st.st_dev, st.st_ino):
            return None
        data = os.read(fd, max_bytes + 1)
    finally:
        os.close(fd)
    return None if len(data) > max_bytes else (data, fst)


def read_regular(path: Path, max_bytes: int) -> bytes | None:
    """Like :func:`read_regular_stat` but returns only the bytes."""
    got = read_regular_stat(path, max_bytes)
    return None if got is None else got[0]
