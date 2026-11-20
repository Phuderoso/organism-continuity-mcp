# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import os
import shutil
import threading
import time
from pathlib import Path

import pytest

from organism_continuity.telepatia import inbox, signing
from organism_continuity.telepatia.storage import UnsafePath, atomic_write


def msgs(d: Path) -> list[Path]:
    return sorted(p for p in d.iterdir() if p.name.endswith(".msg"))


def box(cfg) -> Path:
    return inbox.inbox_dir(cfg.spool, cfg.name)


def store_path(cfg) -> Path:
    return inbox.state_dir(cfg.spool, cfg.name) / inbox.NONCE_FILE


def test_deliver_and_read_verified(pair) -> None:
    a, b = pair
    sent = inbox.deliver(a, "agent-b", "synthetic: build finished")
    res = inbox.read_verified(b)
    assert [m.body for m in res.messages] == ["synthetic: build finished"]
    assert res.messages[0].id == sent.id and res.messages[0].sender == "agent-a"
    assert res.rejected == {}
    assert inbox.read_verified(b).messages == []
    assert len(list((box(b) / "read").iterdir())) == 1


def test_message_file_is_telepatia_sig_v1(pair) -> None:
    a, b = pair
    inbox.deliver(a, "agent-b", "line one\nline two")
    text = msgs(box(b))[0].read_text()
    assert text.startswith("to: agent-b\nfrom: agent-a\n\nline one\nline two\n<!-- telepatia-sig v=1 from=agent-a ts=")
    content, sig = signing.split_signature(text)
    assert sig is not None
    expected = signing.compute_mac(a.signing_key(), "agent-a", int(sig.group("ts")), sig.group("nonce"), content)
    assert sig.group("mac") == expected


def test_peek_does_not_consume(pair) -> None:
    a, b = pair
    inbox.deliver(a, "agent-b", "peek me")
    assert len(inbox.read_verified(b, mark_read=False).messages) == 1
    assert len(inbox.read_verified(b).messages) == 1


def test_files_are_private(pair) -> None:
    a, b = pair
    inbox.deliver(a, "agent-b", "x")
    assert (os.stat(box(b)).st_mode & 0o777) == 0o700
    assert all((p.stat().st_mode & 0o777) == 0o600 for p in msgs(box(b)))
    assert (store_path(b).stat().st_mode & 0o777) == 0o600


def test_missing_peer_inbox(pair) -> None:
    a, _ = pair
    with pytest.raises(inbox.PeerInboxMissing):
        inbox.deliver(a, "agent-z", "x")


def test_unsigned_forged_and_misaddressed_are_quarantined(pair) -> None:
    a, b = pair
    d = box(b)
    (d / "1-unsigned.msg").write_text("to: agent-b\nfrom: agent-a\n\nhi\n")
    (d / "2-forged.msg").write_text(signing.sign("agent-a", "agent-b", "forged", os.urandom(32)))
    (d / "3-other.msg").write_text(signing.sign("agent-a", "agent-c", "not for b", a.signing_key()))
    res = inbox.read_verified(b)
    assert res.messages == []
    assert res.rejected == {"unsigned": 1, "bad_mac": 1, "wrong_recipient": 1}
    names = sorted(p.name for p in (d / "rejected").iterdir())
    assert names == ["1-unsigned.msg.unsigned", "2-forged.msg.bad_mac", "3-other.msg.wrong_recipient"]


def test_lone_surrogate_does_not_block_the_inbox(pair) -> None:
    a, b = pair
    d = box(b)
    good = signing.sign("agent-a", "agent-b", "ok", a.signing_key()).encode()
    (d / "0-bad.msg").write_bytes(good.replace(b"ok", b"\xed\xa0\x80"))
    inbox.deliver(a, "agent-b", "still readable")
    res = inbox.read_verified(b)
    assert [m.body for m in res.messages] == ["still readable"]
    assert res.rejected == {"malformed": 1}


# --- B1: freshness from the transport, persisted nonces --------------------------------------


def test_replay_of_read_message_with_fresh_mtime_is_stale(pair) -> None:
    a, b = pair
    data = json.loads(store_path(b).read_text())
    store_path(b).write_text(json.dumps({**data, "floor": 0}))  # store older than the message
    inbox.deliver(a, "agent-b", "once", now=time.time() - 3600)  # signed an hour ago
    os.utime(msgs(box(b))[0], (time.time() - 3600, time.time() - 3600))
    assert len(inbox.read_verified(b).messages) == 1
    original = next((box(b) / "read").iterdir())
    shutil.copy(original, box(b) / "replay.msg")  # new mtime = now, signed ts = an hour ago
    res = inbox.read_verified(b)
    assert res.messages == [] and res.rejected == {"stale": 1}


def test_replay_with_preserved_mtime_hits_the_persisted_nonce(pair) -> None:
    a, b = pair
    inbox.deliver(a, "agent-b", "once")
    assert len(inbox.read_verified(b).messages) == 1
    original = next((box(b) / "read").iterdir())
    shutil.copy2(original, box(b) / "replay.msg")  # mtime preserved
    from organism_continuity.telepatia.config import load_config

    fresh_reader = load_config(b.path)  # a new process: only the persisted store remembers
    res = inbox.read_verified(fresh_reader)
    assert res.messages == [] and res.rejected == {"replayed_nonce": 1}


def test_old_replayed_message_does_not_wake_again(pair) -> None:
    a, b = pair
    inbox.deliver(a, "agent-b", "wake once")
    assert len(inbox.wait_verified(b, timeout=0).messages) == 1
    original = next((box(b) / "read").iterdir())

    def replay() -> None:
        shutil.copy2(original, box(b) / ".tmp-replay")
        os.replace(box(b) / ".tmp-replay", box(b) / "replay.msg")

    timer = threading.Timer(0.2, replay)
    timer.start()
    res = inbox.wait_verified(b, timeout=1.0)
    timer.join()
    assert res.messages == [] and res.rejected == {"replayed_nonce": 1}


def test_signed_ts_far_from_mtime_is_stale_both_ways(pair) -> None:
    a, b = pair
    now = time.time()
    for i, skew in enumerate((signing.WINDOW_S + 5, -(signing.WINDOW_S + 5))):
        text = signing.sign("agent-a", "agent-b", f"skew {i}", a.signing_key(), ts=int(now + skew))
        atomic_write(box(b) / f"{i}.msg", text.encode())
    assert inbox.read_verified(b).rejected == {"stale": 2}


def test_mtime_older_than_retention_or_in_future_is_stale(pair) -> None:
    a, b = pair
    old_ts = time.time() - inbox.RETENTION_S - 100
    text = signing.sign("agent-a", "agent-b", "very old", a.signing_key(), ts=int(old_ts))
    p = box(b) / "old.msg"
    atomic_write(p, text.encode())
    os.utime(p, (old_ts, old_ts))
    fut = time.time() + 3 * signing.WINDOW_S
    q = box(b) / "future.msg"
    atomic_write(q, signing.sign("agent-a", "agent-b", "future", a.signing_key(), ts=int(fut)).encode())
    os.utime(q, (fut, fut))
    assert inbox.read_verified(b).rejected == {"stale": 2}


def test_duplicate_in_same_scan_is_replay(pair) -> None:
    a, b = pair
    inbox.deliver(a, "agent-b", "dup")
    src = msgs(box(b))[0]
    shutil.copy2(src, box(b) / "zz-dup.msg")
    res = inbox.read_verified(b)
    assert len(res.messages) == 1 and res.rejected == {"replayed_nonce": 1}


def test_nonce_store_persists_and_prunes(pair) -> None:
    a, b = pair
    inbox.deliver(a, "agent-b", "x")
    inbox.read_verified(b)
    data = json.loads(store_path(b).read_text())
    assert data["v"] == 1 and len(data["nonces"]) == 1 and next(iter(data["nonces"])).startswith("agent-a:")
    later = time.time() + inbox.NONCE_KEEP_S + 10
    assert inbox._NonceStore(store_path(b), later).data == {}


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        json.dumps({"v": 2, "floor": 0, "nonces": {}}),
        json.dumps({"v": 1, "floor": True, "nonces": {}}),
        json.dumps({"v": 1, "floor": 0, "nonces": {"a:b": "x"}}),
        json.dumps([]),
    ],
)
def test_corrupt_nonce_store_fails_closed(pair, content: str) -> None:
    a, b = pair
    store_path(b).write_text(content)
    inbox.deliver(a, "agent-b", "x")
    with pytest.raises(inbox.NonceStoreError, match="corrupt"):
        inbox.read_verified(b)
    assert len(msgs(box(b))) == 1  # nothing consumed or quarantined


def test_missing_or_oversized_nonce_store_fails_closed(pair) -> None:
    _, b = pair
    store_path(b).unlink()
    with pytest.raises(inbox.NonceStoreError, match="missing"):
        inbox.read_verified(b)
    store_path(b).write_text(" " * (inbox.MAX_NONCE_FILE_BYTES + 1))
    with pytest.raises(inbox.NonceStoreError, match="too_large"):
        inbox.read_verified(b)


def test_reset_floor_blocks_replay_of_older_files(pair) -> None:
    a, b = pair
    inbox.deliver(a, "agent-b", "before reset")
    inbox.read_verified(b)
    original = next((box(b) / "read").iterdir())
    store_path(b).write_text("{corrupt")
    inbox.reset_nonce_store(b.spool, "agent-b", now=time.time() + inbox.FLOOR_SLACK_S + 1)
    assert any(p.name.startswith("nonces.json.bad-") for p in store_path(b).parent.iterdir())
    shutil.copy2(original, box(b) / "replay.msg")  # preserved mtime is below the new floor
    res = inbox.read_verified(b)
    assert res.messages == [] and res.rejected == {"stale": 1}


def test_init_keeps_existing_store(pair) -> None:
    _, b = pair
    before = store_path(b).read_text()
    inbox.init_inbox(b.spool, "agent-b")
    assert store_path(b).read_text() == before


def test_symlink_message_is_dropped(pair, tmp_path: Path) -> None:
    _, b = pair
    target = tmp_path / "outside.txt"
    target.write_text("secret")
    (box(b) / "link.msg").symlink_to(target)
    res = inbox.read_verified(b)
    assert res.rejected == {"not_regular_or_too_large": 1}
    assert not (box(b) / "link.msg").exists() and target.exists()


def test_symlinked_inbox_dir_refused(pair, tmp_path: Path) -> None:
    a, b = pair
    d = box(b)
    shutil.rmtree(d)
    (tmp_path / "elsewhere").mkdir()
    d.symlink_to(tmp_path / "elsewhere")
    with pytest.raises(UnsafePath):
        inbox.deliver(a, "agent-b", "x")
    with pytest.raises(UnsafePath):
        inbox.read_verified(b)


def test_dotfiles_and_other_names_ignored(pair) -> None:
    _, b = pair
    (box(b) / ".partial.msg.tmp").write_text("x")
    (box(b) / "notes.txt").write_text("x")
    res = inbox.read_verified(b)
    assert res.messages == [] and res.rejected == {}


def test_wait_wakes_on_event(pair) -> None:
    a, b = pair
    timer = threading.Timer(0.3, lambda: inbox.deliver(a, "agent-b", "event"))
    timer.start()
    t0 = time.monotonic()
    res = inbox.wait_verified(b, timeout=5)
    timer.join()
    assert [m.body for m in res.messages] == ["event"]
    assert time.monotonic() - t0 < 4


def test_wait_ignores_forged_and_times_out(pair) -> None:
    _, b = pair

    def drop_forged() -> None:
        atomic_write(box(b) / "9-forged.msg", signing.sign("agent-a", "agent-b", "f", os.urandom(32)).encode())

    timer = threading.Timer(0.2, drop_forged)
    timer.start()
    res = inbox.wait_verified(b, timeout=1.0)
    timer.join()
    assert res.messages == [] and res.rejected == {"bad_mac": 1}


def test_wait_returns_existing_immediately(pair) -> None:
    a, b = pair
    inbox.deliver(a, "agent-b", "already here")
    assert len(inbox.wait_verified(b, timeout=0).messages) == 1


def test_reset_floor_rejects_old_signed_ts_even_with_a_fresh_mtime(pair) -> None:
    """D5: a consumed message re-spooled after a reset, mtime moved past the floor, stays stale."""
    a, b = pair
    signed_at = time.time() - 300  # within the 600 s window of the reset time
    inbox.deliver(a, "agent-b", "consumed before the reset", now=signed_at)
    os.utime(msgs(box(b))[0], (signed_at, signed_at))
    data = json.loads(store_path(b).read_text())
    store_path(b).write_text(json.dumps({**data, "floor": 0}))
    assert [m.body for m in inbox.read_verified(b).messages] == ["consumed before the reset"]
    original = next((box(b) / "read").iterdir())
    reset_at = time.time()
    inbox.reset_nonce_store(b.spool, "agent-b", now=reset_at)
    replay = box(b) / "replay.msg"
    shutil.copy(original, replay)
    later = reset_at + 5
    os.utime(replay, (later, later))  # attacker-chosen mtime after the floor, within 600 s of ts
    res = inbox.read_verified(b, now=later)
    assert res.messages == [] and res.rejected == {"stale": 1}
    inbox.deliver(a, "agent-b", "new after reset", now=later)
    assert [m.body for m in inbox.read_verified(b, now=later + 1).messages] == ["new after reset"]


def test_nonces_are_persisted_before_files_are_consumed(pair, monkeypatch: pytest.MonkeyPatch) -> None:
    """D4: if saving the nonce store fails, nothing is delivered and the files stay retriable."""
    a, b = pair
    inbox.deliver(a, "agent-b", "one")
    inbox.deliver(a, "agent-b", "two")
    before = store_path(b).read_bytes()

    def failing_save(self: object) -> None:
        raise inbox.NonceStoreError("nonce_store_full")

    monkeypatch.setattr(inbox._NonceStore, "save", failing_save)
    with pytest.raises(inbox.NonceStoreError):
        inbox.read_verified(b)
    assert len(msgs(box(b))) == 2 and list((box(b) / "read").iterdir()) == []
    assert store_path(b).read_bytes() == before
    monkeypatch.undo()
    assert sorted(m.body for m in inbox.read_verified(b).messages) == ["one", "two"]
    assert len(json.loads(store_path(b).read_text())["nonces"]) == 2


def test_save_happens_before_move(pair, monkeypatch: pytest.MonkeyPatch) -> None:
    a, b = pair
    inbox.deliver(a, "agent-b", "order")
    events: list[str] = []
    real_save, real_move = inbox._NonceStore.save, inbox._move

    def save(self: inbox._NonceStore) -> None:
        events.append("save")
        real_save(self)

    def move(src: Path, dest_dir: Path, suffix: str = "") -> None:
        events.append("move:" + dest_dir.name)
        real_move(src, dest_dir, suffix)

    monkeypatch.setattr(inbox._NonceStore, "save", save)
    monkeypatch.setattr(inbox, "_move", move)
    inbox.read_verified(b)
    assert events == ["save", "move:read"]


def test_peek_persists_nothing(pair) -> None:
    a, b = pair
    inbox.deliver(a, "agent-b", "peek")
    before = store_path(b).read_bytes()
    assert len(inbox.read_verified(b, mark_read=False).messages) == 1
    assert store_path(b).read_bytes() == before and len(msgs(box(b))) == 1
