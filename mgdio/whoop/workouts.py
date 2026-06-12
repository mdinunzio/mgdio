"""Whoop workouts: ``/v2/activity/workout`` -- strain + heart-rate data."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from mgdio.whoop._parse import parse_rfc3339, range_params
from mgdio.whoop.client import _paginate

logger = logging.getLogger(__name__)

# Conversion for the kilojoule -> kilocalorie convenience property.
_KJ_PER_KCAL = 4.184


@dataclass(frozen=True, slots=True)
class Workout:
    """A Whoop workout activity record.

    Energy is reported in kilojoules; use :attr:`calories` for kcal.

    Attributes:
        id: Workout id.
        user_id: Whoop user id.
        created_at: Record creation time (tz-aware).
        updated_at: Record update time (tz-aware).
        start: Workout start (tz-aware) or ``None``.
        end: Workout end (tz-aware) or ``None``.
        timezone_offset: e.g. ``"-05:00"``.
        sport_name: Human-readable sport, e.g. ``"running"``.
        sport_id: Numeric Whoop sport id.
        score_state: ``"SCORED" | "PENDING_SCORE" | "UNSCORABLE"``.
        strain: 0-21 Whoop strain (``None`` if unscored).
        average_heart_rate: bpm (``None`` if unscored).
        max_heart_rate: bpm (``None`` if unscored).
        kilojoule: Energy expenditure in kJ (``None`` if unscored).
        percent_recorded: Fraction of the workout with HR data.
        distance_meter: Distance in meters (``None`` if not applicable).
        altitude_gain_meter: Total ascent in meters (``None`` if n/a).
        altitude_change_meter: Net altitude change in meters (``None`` if n/a).
        zone_durations: Raw heart-rate-zone duration dict.
    """

    id: str
    user_id: int | None
    created_at: datetime | None
    updated_at: datetime | None
    start: datetime | None
    end: datetime | None
    timezone_offset: str
    sport_name: str
    sport_id: int | None
    score_state: str
    strain: float | None
    average_heart_rate: float | None
    max_heart_rate: float | None
    kilojoule: float | None
    percent_recorded: float | None
    distance_meter: float | None
    altitude_gain_meter: float | None
    altitude_change_meter: float | None
    zone_durations: dict

    @property
    def calories(self) -> float | None:
        """Return kilocalories burned (``kilojoule`` / 4.184), or ``None``."""
        if self.kilojoule is None:
            return None
        return self.kilojoule / _KJ_PER_KCAL


def fetch_workouts(
    *,
    start: datetime | str | None = None,
    end: datetime | str | None = None,
    max_records: int = 100,
) -> list[Workout]:
    """Fetch workout records, newest first.

    Args:
        start: Optional lower bound (tz-aware datetime or ISO string).
        end: Optional upper bound (tz-aware datetime or ISO string).
        max_records: Maximum number of records to return (auto-paginated).

    Returns:
        List of :class:`Workout`, possibly empty.

    Raises:
        MgdioAPIError: On any Whoop API error.
    """
    params = range_params(start, end)
    raw = _paginate("/v2/activity/workout", params=params, max_records=max_records)
    return [_to_workout(item) for item in raw]


def _to_workout(raw: dict) -> Workout:
    score = raw.get("score") or {}
    return Workout(
        id=raw.get("id", ""),
        user_id=raw.get("user_id"),
        created_at=parse_rfc3339(raw.get("created_at")),
        updated_at=parse_rfc3339(raw.get("updated_at")),
        start=parse_rfc3339(raw.get("start")),
        end=parse_rfc3339(raw.get("end")),
        timezone_offset=raw.get("timezone_offset", ""),
        sport_name=raw.get("sport_name", ""),
        sport_id=raw.get("sport_id"),
        score_state=raw.get("score_state", ""),
        strain=score.get("strain"),
        average_heart_rate=score.get("average_heart_rate"),
        max_heart_rate=score.get("max_heart_rate"),
        kilojoule=score.get("kilojoule"),
        percent_recorded=score.get("percent_recorded"),
        distance_meter=score.get("distance_meter"),
        altitude_gain_meter=score.get("altitude_gain_meter"),
        altitude_change_meter=score.get("altitude_change_meter"),
        zone_durations=score.get("zone_durations") or {},
    )
