"""Whoop cycles: ``/v2/cycle`` -- daily physiological cycles (day strain)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from mgdio.whoop._parse import parse_rfc3339, range_params
from mgdio.whoop.client import _paginate

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Cycle:
    """A Whoop physiological cycle (roughly a day of strain).

    Attributes:
        id: Cycle id.
        user_id: Whoop user id.
        created_at: Record creation time (tz-aware).
        updated_at: Record update time (tz-aware).
        start: Cycle start (tz-aware) or ``None``.
        end: Cycle end (tz-aware) or ``None``; the current cycle has no end.
        timezone_offset: e.g. ``"-05:00"``.
        score_state: ``"SCORED" | "PENDING_SCORE" | "UNSCORABLE"``.
        strain: 0-21 accumulated day strain (``None`` if unscored).
        kilojoule: Energy expenditure for the cycle in kJ (``None`` if unscored).
        average_heart_rate: bpm across the cycle (``None`` if unscored).
        max_heart_rate: bpm across the cycle (``None`` if unscored).
    """

    id: int | None
    user_id: int | None
    created_at: datetime | None
    updated_at: datetime | None
    start: datetime | None
    end: datetime | None
    timezone_offset: str
    score_state: str
    strain: float | None
    kilojoule: float | None
    average_heart_rate: float | None
    max_heart_rate: float | None


def fetch_cycles(
    *,
    start: datetime | str | None = None,
    end: datetime | str | None = None,
    max_records: int = 100,
) -> list[Cycle]:
    """Fetch physiological cycles, newest first.

    Args:
        start: Optional lower bound (tz-aware datetime or ISO string).
        end: Optional upper bound (tz-aware datetime or ISO string).
        max_records: Maximum number of records to return (auto-paginated).

    Returns:
        List of :class:`Cycle`, possibly empty.

    Raises:
        MgdioAPIError: On any Whoop API error.
    """
    params = range_params(start, end)
    raw = _paginate("/v2/cycle", params=params, max_records=max_records)
    return [_to_cycle(item) for item in raw]


def _to_cycle(raw: dict) -> Cycle:
    score = raw.get("score") or {}
    return Cycle(
        id=raw.get("id"),
        user_id=raw.get("user_id"),
        created_at=parse_rfc3339(raw.get("created_at")),
        updated_at=parse_rfc3339(raw.get("updated_at")),
        start=parse_rfc3339(raw.get("start")),
        end=parse_rfc3339(raw.get("end")),
        timezone_offset=raw.get("timezone_offset", ""),
        score_state=raw.get("score_state", ""),
        strain=score.get("strain"),
        kilojoule=score.get("kilojoule"),
        average_heart_rate=score.get("average_heart_rate"),
        max_heart_rate=score.get("max_heart_rate"),
    )
