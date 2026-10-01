# SPDX-License-Identifier: AGPL-3.0-or-later
"""Weekly recurring appointment series helpers."""
from __future__ import annotations

import secrets
from datetime import date, timedelta


MAX_REPEAT_WEEKS = 26


def new_series_id() -> str:
    return "s_" + secrets.token_urlsafe(10).replace("-", "x").replace("_", "y")


def weekly_dates(start: date, count: int) -> list[date]:
    """Return ``count`` weekly dates starting at ``start`` (inclusive)."""
    n = max(1, min(int(count), MAX_REPEAT_WEEKS))
    return [start + timedelta(weeks=i) for i in range(n)]


def parse_repeat_weeks(raw) -> int:
    try:
        n = int(str(raw or "1").strip())
    except ValueError:
        return 1
    return max(1, min(n, MAX_REPEAT_WEEKS))
