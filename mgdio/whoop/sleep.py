"""Whoop sleep: ``/v2/activity/sleep`` -- sleep performance + stages.

Note: this module is named ``sleep`` but is only ever imported as
``mgdio.whoop.sleep``; it never shadows the stdlib ``time.sleep``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from mgdio.whoop._parse import parse_rfc3339, range_params
from mgdio.whoop.client import _paginate

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Sleep:
    """A Whoop sleep activity record.

    Attributes:
        id: Sleep id.
        cycle_id: Owning physiological cycle id.
        user_id: Whoop user id.
        created_at: Record creation time (tz-aware).
        updated_at: Record update time (tz-aware).
        start: Sleep onset (tz-aware) or ``None``.
        end: Wake time (tz-aware) or ``None``.
        timezone_offset: e.g. ``"-05:00"``.
        nap: True if this was a nap rather than the main sleep.
        score_state: ``"SCORED" | "PENDING_SCORE" | "UNSCORABLE"``.
        sleep_performance_percentage: 0-100 (``None`` if unscored).
        sleep_efficiency_percentage: 0-100 (``None`` if unscored).
        sleep_consistency_percentage: 0-100 (``None`` if unscored).
        respiratory_rate: Breaths per minute (``None`` if unscored).
        stage_summary: Raw stage-duration dict (light/deep/REM/awake ms).
        sleep_needed: Raw sleep-needed breakdown dict.
    """

    id: str
    cycle_id: int | None
    user_id: int | None
    created_at: datetime | None
    updated_at: datetime | None
    start: datetime | None
    end: datetime | None
    timezone_offset: str
    nap: bool
    score_state: str
    sleep_performance_percentage: float | None
    sleep_efficiency_percentage: float | None
    sleep_consistency_percentage: float | None
    respiratory_rate: float | None
    stage_summary: dict
    sleep_needed: dict


def fetch_sleeps(
    *,
    start: datetime | str | None = None,
    end: datetime | str | None = None,
    max_records: int = 100,
) -> list[Sleep]:
    """Fetch sleep records, newest first.

    Args:
        start: Optional lower bound (tz-aware datetime or ISO string).
        end: Optional upper bound (tz-aware datetime or ISO string).
        max_records: Maximum number of records to return (auto-paginated).

    Returns:
        List of :class:`Sleep`, possibly empty.

    Raises:
        MgdioAPIError: On any Whoop API error.
    """
    params = range_params(start, end)
    raw = _paginate("/v2/activity/sleep", params=params, max_records=max_records)
    return [_to_sleep(item) for item in raw]


def _to_sleep(raw: dict) -> Sleep:
    score = raw.get("score") or {}
    return Sleep(
        id=raw.get("id", ""),
        cycle_id=raw.get("cycle_id"),
        user_id=raw.get("user_id"),
        created_at=parse_rfc3339(raw.get("created_at")),
        updated_at=parse_rfc3339(raw.get("updated_at")),
        start=parse_rfc3339(raw.get("start")),
        end=parse_rfc3339(raw.get("end")),
        timezone_offset=raw.get("timezone_offset", ""),
        nap=bool(raw.get("nap", False)),
        score_state=raw.get("score_state", ""),
        sleep_performance_percentage=score.get("sleep_performance_percentage"),
        sleep_efficiency_percentage=score.get("sleep_efficiency_percentage"),
        sleep_consistency_percentage=score.get("sleep_consistency_percentage"),
        respiratory_rate=score.get("respiratory_rate"),
        stage_summary=score.get("stage_summary") or {},
        sleep_needed=score.get("sleep_needed") or {},
    )
