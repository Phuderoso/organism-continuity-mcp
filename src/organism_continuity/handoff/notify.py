# SPDX-License-Identifier: MIT
"""Signed notification that a handoff package is ready.

Signing and delivery are imported from ``organism_continuity.telepatia`` (``inbox.deliver`` signs with
``organism_continuity.telepatia.signing``); nothing is reimplemented here.
"""

from __future__ import annotations

from pathlib import Path

from organism_continuity.telepatia import inbox, keys, signing
from organism_continuity.telepatia.config import Config


def notify(cfg: Config, to: str, handoff_id: str, md_path: str | Path) -> signing.Message:
    """Deliver a signed ``telepatia-sig v=1`` message to ``to`` pointing at the package."""
    return inbox.deliver(cfg, keys.check_name(to), f"handoff {handoff_id} is ready: {md_path}")
