# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import threading
import time

import pytest

from organism_continuity.telepatia import inbox, outbox, presence


def test_hold_until_idle_then_deliver(pair) -> None:
    a, b = pair
    box = outbox.Outbox(a)
    presence.write_presence(b.spool, "agent-b", "busy", task="synthetic")
    mid = box.enqueue("agent-b", "after your turn")
    rep = box.flush()
    assert rep.delivered == [] and rep.held == {mid: "held_busy"}
    presence.write_presence(b.spool, "agent-b", "idle")
    rep = box.flush()
    assert rep.delivered == [mid]
    assert [m.body for m in inbox.read_verified(b).messages] == ["after your turn"]
    assert box.pending() == []


def test_state_survives_restart_and_has_no_secrets(pair) -> None:
    a, b = pair
    mid = outbox.Outbox(a).enqueue("agent-b", "persist me")
    data = json.loads((outbox.queue_dir(a.spool, "agent-a") / "outbox.json").read_text())
    blob = json.dumps(data)
    assert a.signing_key().hex() not in blob
    assert not {"mac", "nonce", "key"} & set(data["pending"][0])
    fresh = outbox.Outbox(a)
    assert [r["message_id"] for r in fresh.pending()] == [mid]
    presence.write_presence(b.spool, "agent-b", "idle")
    assert fresh.flush().delivered == [mid]
    done = json.loads((outbox.queue_dir(a.spool, "agent-a") / "outbox.json").read_text())["completed"][0]
    assert "body" not in done and len(done["body_sha256"]) == 64


def test_hold_expires_into_plain_delivery(pair) -> None:
    a, _b = pair
    box = outbox.Outbox(a)
    t0 = time.time()
    mid = box.enqueue("agent-b", "late", now=t0)
    assert box.flush(now=t0 + 1).held  # unknown presence -> held
    rep = box.flush(now=t0 + outbox.HOLD_MAX_S + 1)
    assert rep.delivered == [mid]


def test_missing_inbox_keeps_message(pair) -> None:
    a, _ = pair
    box = outbox.Outbox(a)
    mid = box.enqueue("agent-z", "for later")
    rep = box.flush(hold_max_s=0)
    assert rep.held == {mid: "peer_inbox_missing"}
    assert box.pending()[0]["attempts"] == 1


@pytest.mark.parametrize(
    "content",
    [
        "{bad json",
        json.dumps({"v": 99, "pending": [], "completed": []}),
        json.dumps({"v": 1, "pending": [{"message_id": "x", "state": "pending", "mac": "00"}], "completed": []}),
    ],
)
def test_corrupt_state_is_quarantined(pair, content: str) -> None:
    a, _ = pair
    box = outbox.Outbox(a)
    box.enqueue("agent-b", "x")
    box.path.write_text(content)
    assert box.pending() == []
    assert any(p.name.startswith("outbox.json.corrupt-") for p in box.dir.iterdir())


def test_symlinked_state_is_quarantined(pair, tmp_path) -> None:
    a, _ = pair
    box = outbox.Outbox(a)
    box.enqueue("agent-b", "x")
    real = tmp_path / "real.json"
    real.write_text(box.path.read_text())
    box.path.unlink()
    box.path.symlink_to(real)
    assert box.pending() == []
    assert real.exists()


def test_enqueue_validates(pair) -> None:
    a, _ = pair
    with pytest.raises(ValueError):
        outbox.Outbox(a).enqueue("agent-b", "  ")
    with pytest.raises(ValueError):
        outbox.Outbox(a).enqueue("Not Valid", "x")


def test_run_wakes_on_presence_event(pair) -> None:
    a, b = pair
    presence.write_presence(b.spool, "agent-b", "busy")
    box = outbox.Outbox(a)
    mid = box.enqueue("agent-b", "event driven")
    timer = threading.Timer(0.3, lambda: presence.write_presence(b.spool, "agent-b", "idle"))
    timer.start()
    rep = box.run(timeout=5)
    timer.join()
    assert rep.delivered == [mid] and rep.held == {}


def test_run_times_out(pair) -> None:
    a, _ = pair
    box = outbox.Outbox(a)
    box.enqueue("agent-b", "stuck")
    rep = box.run(timeout=0.2)
    assert rep.delivered == [] and rep.held
