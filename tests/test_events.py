# SPDX-License-Identifier: MIT
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from organism_continuity.telepatia import events


def test_wait_returns_true_on_new_file(tmp_path: Path) -> None:
    with events.DirWatch(tmp_path) as w:
        t = threading.Timer(0.2, lambda: (tmp_path / "x").write_text("1"))
        t.start()
        assert w.wait(5) is True
        t.join()


def test_wait_times_out(tmp_path: Path) -> None:
    with events.DirWatch(tmp_path) as w:
        assert w.wait(0.1) is False


def test_missing_dir_raises(tmp_path: Path) -> None:
    with pytest.raises((events.EventsUnavailable, OSError)), events.DirWatch(tmp_path / "nope"):
        pass


def test_wait_unarmed_raises(tmp_path: Path) -> None:
    with pytest.raises(events.EventsUnavailable):
        events.DirWatch(tmp_path).wait(0)


def test_no_sleep_loop_in_package() -> None:
    import organism_continuity.handoff
    import organism_continuity.telepatia

    for pkg in (organism_continuity.telepatia, organism_continuity.handoff):
        for src in Path(pkg.__file__).parent.glob("*.py"):
            assert "time.sleep" not in src.read_text(), src.name
