"""Whoop recovery: ``/v2/recovery`` -- morning recovery scores.

Recovery is a *morning* metric: a recovery record does not exist until the
preceding sleep cycle closes, so querying before the user has woken up may
return nothing for "today".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from mgdio.whoop._parse import parse_rfc3339, range_params
from mgdio.whoop.client import _paginate

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Recovery:
    """A Whoop recovery record.

    Attributes:
        cycle_id: Physiological cycle this recovery belongs to.
        sleep_id: Sleep whose end produced this recovery.
        user_id: Whoop user id.
        created_at: When Whoop created the record (tz-aware).
        updated_at: When Whoop last updated it (tz-aware).
        score_state: ``"SCORED" | "PENDING_SCORE" | "UNSCORABLE"``.
        recovery_score: 0-100 recovery percentage (``None`` if unscored).
        resting_heart_rate: Resting HR in bpm (``None`` if unscored).
        hrv_rmssd_milli: HRV (RMSSD) in milliseconds (``None`` if unscored).
        spo2_percentage: Blood-oxygen percentage (``None`` if unavailable).
        skin_temp_celsius: Skin temperature in Celsius (``None`` if unavailable).
        user_calibrating: True while Whoop is still calibrating the user.
    """

    cycle_id: int | None
    sleep_id: str
    user_id: int | None
    created_at: datetime | None
    updated_at: datetime | None
    score_state: str
    recovery_score: float | None
    resting_heart_rate: float | None
    hrv_rmssd_milli: float | None
    spo2_percentage: float | None
    skin_temp_celsius: float | None
    user_calibrating: bool


def fetch_recoveries(
    *,
    start: datetime | str | None = None,
    end: datetime | str | None = None,
    max_records: int = 100,
) -> list[Recovery]:
    """Fetch recovery records, newest first.

    Args:
        start: Optional lower bound (tz-aware datetime or ISO string).
        end: Optional upper bound (tz-aware datetime or ISO string).
        max_records: Maximum number of records to return (auto-paginated).

    Returns:
        List of :class:`Recovery`, possibly empty.

    Raises:
        MgdioAPIError: On any Whoop API error.
    """
    params = range_params(start, end)
    raw = _paginate("/v2/recovery", params=params, max_records=max_records)
    return [_to_recovery(item) for item in raw]


def _to_recovery(raw: dict) -> Recovery:
    score = raw.get("score") or {}
    return Recovery(
        cycle_id=raw.get("cycle_id"),
        sleep_id=raw.get("sleep_id", ""),
        user_id=raw.get("user_id"),
        created_at=parse_rfc3339(raw.get("created_at")),
        updated_at=parse_rfc3339(raw.get("updated_at")),
        score_state=raw.get("score_state", ""),
        recovery_score=score.get("recovery_score"),
        resting_heart_rate=score.get("resting_heart_rate"),
        hrv_rmssd_milli=score.get("hrv_rmssd_milli"),
        spo2_percentage=score.get("spo2_percentage"),
        skin_temp_celsius=score.get("skin_temp_celsius"),
        user_calibrating=bool(score.get("user_calibrating", False)),
    )
