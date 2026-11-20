# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from organism_continuity.telepatia import ledger as L


@pytest.fixture
def state(tmp_path: Path) -> Path:
    d = tmp_path / "state"
    d.mkdir(mode=0o700)
    os.chmod(d, 0o700)
    return d


def test_missing_is_empty_and_claim_persists(state: Path) -> None:
    led = L.ReplayLedger(state / "ledger.json")
    with led.transaction(clock=1000.0) as view:
        assert not view.seen("a:1")
        view.claim("a:1", 1600.0)
    assert oct(os.stat(state / "ledger.json").st_mode & 0o777) == "0o600"
    with led.transaction(clock=1000.0) as view:
        assert view.seen("a:1")
    assert json.loads((state / "ledger.json").read_text()) == {"v": 1, "nonces": {"a:1": 1600.0}}


def test_read_only_creates_nothing_and_cannot_claim(state: Path) -> None:
    led = L.ReplayLedger(state / "ledger.json")
    with led.transaction(write=False) as view:
        assert not view.seen("a:1")
        with pytest.raises(L.ReplayLedgerError, match="read_only"):
            view.claim("a:1", 1.0)
    assert list(state.iterdir()) == []


def test_read_only_uses_existing_lock(state: Path) -> None:
    led = L.ReplayLedger(state / "ledger.json")
    with led.transaction(clock=0.0) as view:
        view.claim("a:1", 10.0)
    before = (state / "ledger.json").read_bytes()
    with led.transaction(write=False) as view:
        assert view.seen("a:1")
    assert (state / "ledger.json").read_bytes() == before


def test_prune_uses_local_clock_with_retention(state: Path) -> None:
    led = L.ReplayLedger(state / "ledger.json")
    with led.transaction(clock=0.0) as view:
        view.claim("old:1", 100.0)
        view.claim("new:1", 10_000_000.0)
    later = 100.0 + L.KEEP_AFTER_EXPIRY_S + 1
    with led.transaction(clock=later) as view:
        assert view.seen("old:1")  # still loaded; pruning happens only on save
        view.claim("x:1", later)
    with led.transaction(clock=later) as view:
        assert not view.seen("old:1") and view.seen("new:1") and view.seen("x:1")


def test_error_inside_block_saves_nothing(state: Path) -> None:
    led = L.ReplayLedger(state / "ledger.json")
    with pytest.raises(RuntimeError), led.transaction() as view:
        view.claim("a:1", 1.0)
        raise RuntimeError("boom")
    assert not (state / "ledger.json").exists()


@pytest.mark.parametrize(
    "payload",
    [
        b"not json",
        b"\xff\xfe",
        b"[]",
        b'{"v": 2, "nonces": {}}',
        b'{"v": 1, "nonces": []}',
        b'{"v": 1, "nonces": {}, "extra": 1}',
        b'{"v": 1, "nonces": {"a:1": "x"}}',
        b'{"v": 1, "nonces": {"a:1": true}}',
        b'{"v": 1, "nonces": {"a:1": NaN}}',
        b'{"v": 1, "nonces": {"a:1": Infinity}}',
        b"[" * 200_000 + b"]" * 200_000,
    ],
)
def test_corrupt_fails_closed(state: Path, payload: bytes) -> None:
    p = state / "ledger.json"
    p.write_bytes(payload)
    os.chmod(p, 0o600)
    with pytest.raises(L.ReplayLedgerError, match="corrupt"), L.ReplayLedger(p).transaction():
        pass  # pragma: no cover


def test_oversize_fails_closed(state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(L, "MAX_LEDGER_BYTES", 32)
    p = state / "ledger.json"
    p.write_text(json.dumps({"v": 1, "nonces": {"a" * 40: 1}}))
    os.chmod(p, 0o600)
    with pytest.raises(L.ReplayLedgerError, match="too_large"), L.ReplayLedger(p).transaction():
        pass  # pragma: no cover


def test_full_on_save(state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(L, "MAX_LEDGER_BYTES", 40)
    led = L.ReplayLedger(state / "ledger.json")
    with pytest.raises(L.ReplayLedgerError, match="full"), led.transaction(clock=0.0) as view:
        view.claim("a" * 64, 1.0)
    assert not (state / "ledger.json").exists()


def test_save_failure_is_ledger_error(state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr(L, "atomic_write", boom)
    with pytest.raises(L.ReplayLedgerError, match="save_failed"), L.ReplayLedger(state / "l.json").transaction() as v:
        v.claim("a:1", 1.0)


def test_symlink_ledger_refused(state: Path, tmp_path: Path) -> None:
    real = tmp_path / "real.json"
    real.write_text('{"v": 1, "nonces": {}}')
    os.chmod(real, 0o600)
    (state / "ledger.json").symlink_to(real)
    with pytest.raises(L.ReplayLedgerError, match="unsafe"), L.ReplayLedger(state / "ledger.json").transaction():
        pass  # pragma: no cover


def test_non_private_ledger_refused(state: Path) -> None:
    p = state / "ledger.json"
    p.write_text('{"v": 1, "nonces": {}}')
    os.chmod(p, 0o644)
    with pytest.raises(L.ReplayLedgerError, match="not_private"), L.ReplayLedger(p).transaction(write=False):
        pass  # pragma: no cover


def test_directory_ledger_refused(state: Path) -> None:
    (state / "ledger.json").mkdir()
    with pytest.raises(L.ReplayLedgerError), L.ReplayLedger(state / "ledger.json").transaction(write=False):
        pass  # pragma: no cover


def test_parent_checks(tmp_path: Path) -> None:
    with (
        pytest.raises(L.ReplayLedgerError, match="parent_missing"),
        L.ReplayLedger(tmp_path / "no/l.json").transaction(),
    ):
        pass  # pragma: no cover
    open_dir = tmp_path / "open"
    open_dir.mkdir()
    os.chmod(open_dir, 0o777)  # noqa: S103 - deliberately unsafe fixture
    with (
        pytest.raises(L.ReplayLedgerError, match="parent_not_private"),
        L.ReplayLedger(open_dir / "l.json").transaction(),
    ):
        pass  # pragma: no cover
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(private, target_is_directory=True)
    with pytest.raises(L.ReplayLedgerError, match="not_a_directory"), L.ReplayLedger(link / "l.json").transaction():
        pass  # pragma: no cover


def test_invalid_clock_and_expiry(state: Path) -> None:
    led = L.ReplayLedger(state / "ledger.json")
    for bad in (float("nan"), float("inf")):
        with pytest.raises(L.ReplayLedgerError, match="invalid_clock"), led.transaction(clock=bad):
            pass  # pragma: no cover
    with pytest.raises(L.ReplayLedgerError, match="invalid_expiry"), led.transaction() as view:
        view.claim("a:1", float("nan"))


def test_ledger_key() -> None:
    assert L.ledger_key("agent-a", "ab") == "agent-a:ab"
