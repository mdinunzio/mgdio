"""Shared parsing helpers for Whoop resource modules."""

from __future__ import annotations

from datetime import datetime, timezone


def parse_rfc3339(value: str | None) -> datetime | None:
    """Parse an RFC 3339 / ISO 8601 timestamp to a tz-aware datetime.

    Returns ``None`` for empty / missing values (Whoop omits ``start`` /
    ``end`` on some records). A ``Z`` suffix is normalized to ``+00:00``;
    naive results are coerced to UTC.
    """
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def range_params(
    start: datetime | str | None,
    end: datetime | str | None,
) -> dict:
    """Build ``start`` / ``end`` query params (Whoop wants ISO strings).

    Accepts tz-aware datetimes (serialized via ``isoformat``) or
    already-formatted strings. Omits keys that are ``None``.
    """
    params: dict = {}
    if start is not None:
        params["start"] = start.isoformat() if isinstance(start, datetime) else start
    if end is not None:
        params["end"] = end.isoformat() if isinstance(end, datetime) else end
    return params
