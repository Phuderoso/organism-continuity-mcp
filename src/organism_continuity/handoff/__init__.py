# SPDX-License-Identifier: MIT
"""Session handoff packages between two agent sessions ("lanes").

A separate package that depends on ``organism_continuity.telepatia`` for storage helpers and, for optional
notifications, for signing and delivery. It contains no cryptography of its own.
"""

from organism_continuity.handoff.core import (
    ID_RE,
    LANE_RE,
    MAX_NOTE_CHARS,
    SCHEMA_HANDOFF,
    SCHEMA_PENDING,
    SCHEMA_STATUS,
    HandoffError,
    LaneStatus,
    Thresholds,
    absorb,
    check_lane,
    check_note,
    lane_status,
    package,
    pending,
    status,
)

__version__ = "0.5.1"

__all__ = [
    "ID_RE",
    "LANE_RE",
    "MAX_NOTE_CHARS",
    "SCHEMA_HANDOFF",
    "SCHEMA_PENDING",
    "SCHEMA_STATUS",
    "HandoffError",
    "LaneStatus",
    "Thresholds",
    "__version__",
    "absorb",
    "check_lane",
    "check_note",
    "lane_status",
    "package",
    "pending",
    "status",
]
