# SPDX-License-Identifier: MIT
"""Block until a directory changes, using the OS event API (no clock polling).

Linux: inotify via ctypes. macOS/BSD: kqueue (``select.kqueue``). If neither is available the
call raises ``EventsUnavailable`` instead of silently falling back to a sleep loop.

Usage pattern (no lost wake-ups)::

    with DirWatch(path) as w:      # 1. arm the watch
        items = scan()             # 2. look
        if not items:
            w.wait(timeout)        # 3. sleep until the kernel reports a change
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import select
import sys
from pathlib import Path
from typing import TYPE_CHECKING


class EventsUnavailable(RuntimeError):
    """The platform offers no file-event API (inotify or kqueue)."""

    pass


_IN_MODIFY = 0x00000002
_IN_CLOSE_WRITE = 0x00000008
_IN_MOVED_TO = 0x00000080
_IN_CREATE = 0x00000100
_IN_DELETE_SELF = 0x00000400
_IN_NONBLOCK = 0o4000
_IN_CLOEXEC = 0o2000000


def _libc() -> ctypes.CDLL | None:
    name = ctypes.util.find_library("c")
    lib = ctypes.CDLL(name or None, use_errno=True)
    if not hasattr(lib, "inotify_init1"):
        return None
    return lib


if TYPE_CHECKING:
    # select.kqueue exists only in the Darwin/BSD stubs; keep a dummy on Linux so
    # the same annotation is valid under `mypy --strict --platform linux`.
    if sys.platform == "darwin":
        _KQueue = select.kqueue
    else:

        class _KQueue:
            def close(self) -> None: ...
            def control(self, changelist: object, maxevents: int, timeout: float | None = None) -> object: ...


class DirWatch:
    """Watch one directory for new/changed entries. Context manager; ``wait`` returns True on an
    event and False on timeout (``timeout=None`` waits indefinitely)."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._fd = -1
        self._kq: _KQueue | None = None
        self._dirfd = -1

    def __enter__(self) -> DirWatch:
        """Arm the watch. Must happen before the caller scans the directory."""
        if sys.platform.startswith("linux"):
            lib = _libc()
            if lib is None:
                raise EventsUnavailable("inotify_unavailable")
            fd = lib.inotify_init1(_IN_NONBLOCK | _IN_CLOEXEC)
            if fd < 0:
                raise EventsUnavailable(f"inotify_init1_failed:{ctypes.get_errno()}")
            mask = _IN_CREATE | _IN_MOVED_TO | _IN_CLOSE_WRITE | _IN_MODIFY | _IN_DELETE_SELF
            wd = lib.inotify_add_watch(fd, os.fsencode(self.path), mask)
            if wd < 0:
                os.close(fd)
                raise EventsUnavailable(f"inotify_add_watch_failed:{ctypes.get_errno()}")
            self._fd = fd
        elif hasattr(select, "kqueue"):
            flags = os.O_RDONLY | getattr(os, "O_EVTONLY", 0)
            self._dirfd = os.open(self.path, flags)
            self._kq = select.kqueue()
            ev = select.kevent(
                self._dirfd,
                filter=select.KQ_FILTER_VNODE,
                flags=select.KQ_EV_ADD | select.KQ_EV_CLEAR,
                fflags=select.KQ_NOTE_WRITE | select.KQ_NOTE_EXTEND | select.KQ_NOTE_DELETE,
            )
            self._kq.control([ev], 0, 0)
        else:
            raise EventsUnavailable("no_inotify_or_kqueue")
        return self

    def wait(self, timeout: float | None = None) -> bool:
        """Block until the directory changes (True) or ``timeout`` seconds pass (False)."""
        if self._fd >= 0:
            ready, _, _ = select.select([self._fd], [], [], timeout)
            if not ready:
                return False
            try:
                while os.read(self._fd, 65536):
                    pass
            except BlockingIOError:
                pass
            return True
        if self._kq is not None:
            events = self._kq.control(None, 1, timeout)
            return bool(events)
        raise EventsUnavailable("watch_not_armed")

    def __exit__(self, *exc: object) -> None:
        """Release the watch descriptors."""
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1
        if self._kq is not None:
            self._kq.close()
            self._kq = None
        if self._dirfd >= 0:
            os.close(self._dirfd)
            self._dirfd = -1
