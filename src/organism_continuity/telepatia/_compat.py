# SPDX-License-Identifier: MIT
"""Compatibility shims for Python 3.10 (``tomllib`` and ``datetime.UTC`` arrived in 3.11).

On 3.10 the kit uses its own strict TOML subset parser (:mod:`organism_continuity.telepatia._toml`) so it has
no third-party runtime dependency.
"""

from __future__ import annotations

import sys
from datetime import timedelta, timezone

if sys.version_info >= (3, 11):
    from datetime import UTC

    import tomllib
else:  # pragma: no cover - exercised only on 3.10
    from organism_continuity.telepatia import _toml as tomllib

    UTC = timezone(timedelta(0), "UTC")

__all__ = ["UTC", "tomllib"]
