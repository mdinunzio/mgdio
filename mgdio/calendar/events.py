"""Calendar events: list, fetch, create, update, delete, quick-add.

Datetime handling
=================

All datetimes crossing the public boundary must be timezone-aware --
naive datetimes raise ``ValueError`` (boundary validation per CLAUDE.md).
The :class:`CalendarEvent` dataclass always exposes ``start`` and ``end``
as tz-aware datetimes; for all-day events the value is UTC midnight on
the relevant date and ``all_day=True`` signals "ignore time-of-day".

Update semantics
================

:func:`update_event` uses tri-state PATCH semantics for each optional field:

* ``None`` (the default)  -- field is omitted from the PATCH body (no-op).
* :data:`CLEAR` sentinel  -- field is sent as null/empty (clears it on the
  server).
* Any value               -- field is set to that value.

``start`` and ``end`` cannot be cleared (Calendar API requires them).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Sequence

from googleapiclient.errors import HttpError

from mgdio.calendar.client import get_service
from mgdio.exceptions import MgdioAPIError

logger = logging.getLogger(__name__)


class _ClearType:
    """Sentinel singleton: pass :data:`CLEAR` to ``update_event`` to null a field."""

    _instance: "_ClearType | None" = None

    def __new__(cls) -> "_ClearType":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "CLEAR"


CLEAR = _ClearType()


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    """A normalized Calendar event.

    Attributes:
        id: Event id (use as ``event_id`` in update/delete/fetch).
        calendar_id: Owning calendar; populated from the caller's context,
            not the API response.
        summary: Event title.
        description: Body / details, or empty string.
        location: Free-text location, or empty string.
        start: Tz-aware start. For all-day events this is UTC midnight on
            the start date.
        end: Tz-aware end. For all-day events this is UTC midnight on the
            exclusive end date (Calendar's all-day semantics).
        all_day: True if the event is date-only (no time-of-day).
        attendees: Tuple of attendee email addresses.
        creator: Creator email, or empty string.
        organizer: Organizer email, or empty string.
        html_link: ``https://www.google.com/calendar/event?eid=...``.
        status: ``"confirmed" | "tentative" | "cancelled"``.
        created: Tz-aware creation time.
        updated: Tz-aware last-modified time.
    """

    id: str
    calendar_id: str
    summary: str
    description: str
    location: str
    start: datetime
    end: datetime
    all_day: bool
    attendees: tuple[str, ...]
    creator: str
    organizer: str
    html_link: str
    status: str
    created: datetime
    updated: datetime


def fetch_events(
    calendar_id: str = "primary",
    *,
    time_min: datetime | None = None,
    time_max: datetime | None = None,
    query: str = "",
    max_results: int = 50,
    single_events: bool = True,
) -> list[CalendarEvent]:
    """List events on ``calendar_id``.

    Args:
        calendar_id: Calendar to read from. Default ``"primary"``.
        time_min: Optional lower bound (tz-aware). Default: no lower bound.
        time_max: Optional upper bound (tz-aware). Default: no upper bound.
        query: Free-text search across summary, description, etc.
        max_results: Maximum number of events to return.
        single_events: When True (default), recurring events are expanded
            into individual instances and ordered by start time. When
            False, the underlying recurring event is returned once and
            order is by last-modified.

    Returns:
        List of :class:`CalendarEvent`, possibly empty.

    Raises:
        MgdioAPIError: On any Calendar API HTTP error.
        ValueError: If ``time_min`` or ``time_max`` is naive (not tz-aware).
    """
    _require_aware(time_min, "time_min")
    _require_aware(time_max, "time_max")

    params: dict[str, Any] = {
        "calendarId": calendar_id,
        "maxResults": max_results,
        "singleEvents": single_events,
        "orderBy": "startTime" if single_events else "updated",
    }
    if time_min is not None:
        params["timeMin"] = time_min.isoformat()
    if time_max is not None:
        params["timeMax"] = time_max.isoformat()
    if query:
        params["q"] = query

    service = get_service()
    try:
        resp = service.events().list(**params).execute()
    except HttpError as exc:
        raise MgdioAPIError(f"Calendar events.list failed: {exc}") from exc

    return [_to_event(item, calendar_id) for item in resp.get("items", [])]


def fetch_event(event_id: str, calendar_id: str = "primary") -> CalendarEvent:
    """Fetch a single event by id.

    Args:
        event_id: Event id.
        calendar_id: Owning calendar. Default ``"primary"``.

    Returns:
        A populated :class:`CalendarEvent`.

    Raises:
        MgdioAPIError: On any Calendar API HTTP error.
    """
    service = get_service()
    try:
        raw = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    except HttpError as exc:
        raise MgdioAPIError(f"Calendar events.get {event_id} failed: {exc}") from exc
    return _to_event(raw, calendar_id)


def create_event(
    summary: str,
    start: datetime,
    end: datetime,
    *,
    description: str | None = None,
    location: str | None = None,
    attendees: Sequence[str] | None = None,
    calendar_id: str = "primary",
    all_day: bool = False,
) -> CalendarEvent:
    """Create a new event.

    Args:
        summary: Event title.
        start: Tz-aware start datetime. For ``all_day=True`` only the
            date part is used.
        end: Tz-aware end datetime. For ``all_day=True`` Calendar
            treats this as exclusive.
        description: Optional details body.
        location: Optional free-text location.
        attendees: Optional iterable of attendee email addresses.
        calendar_id: Target calendar. Default ``"primary"``.
        all_day: If True, the event is date-only.

    Returns:
        The created :class:`CalendarEvent`.

    Raises:
        MgdioAPIError: On any Calendar API HTTP error.
        ValueError: If ``start`` or ``end`` is naive.
    """
    _require_aware(start, "start")
    _require_aware(end, "end")

    body: dict[str, Any] = {
        "summary": summary,
        "start": _format_endpoint(start, all_day=all_day),
        "end": _format_endpoint(end, all_day=all_day),
    }
    if description is not None:
        body["description"] = description
    if location is not None:
        body["location"] = location
    if attendees:
        body["attendees"] = [{"email": e} for e in attendees]

    service = get_service()
    try:
        raw = service.events().insert(calendarId=calendar_id, body=body).execute()
    except HttpError as exc:
        raise MgdioAPIError(f"Calendar events.insert failed: {exc}") from exc
    return _to_event(raw, calendar_id)


def update_event(
    event_id: str,
    *,
    summary: str | _ClearType | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    description: str | _ClearType | None = None,
    location: str | _ClearType | None = None,
    attendees: Sequence[str] | _ClearType | None = None,
    all_day: bool | None = None,
    calendar_id: str = "primary",
) -> CalendarEvent:
    """PATCH an event. ``None`` = no-op, :data:`CLEAR` = null the field.

    Args:
        event_id: Event id.
        summary: New title; ``CLEAR`` to clear; ``None`` to leave alone.
        start: New tz-aware start; ``None`` to leave alone (cannot be cleared).
        end: New tz-aware end; ``None`` to leave alone (cannot be cleared).
        description: New body; ``CLEAR`` to clear; ``None`` to leave alone.
        location: New location; ``CLEAR`` to clear; ``None`` to leave alone.
        attendees: New attendee list; ``CLEAR`` to clear; ``None`` to leave alone.
        all_day: If start/end are provided, marks them as all-day. If only
            updating times of an existing all-day event you must pass
            ``all_day=True``.
        calendar_id: Owning calendar. Default ``"primary"``.

    Returns:
        The updated :class:`CalendarEvent`.

    Raises:
        MgdioAPIError: On any Calendar API HTTP error.
        ValueError: If ``start`` or ``end`` is provided and naive.
    """
    body: dict[str, Any] = {}
    if summary is not None:
        body["summary"] = None if summary is CLEAR else summary
    if description is not None:
        body["description"] = None if description is CLEAR else description
    if location is not None:
        body["location"] = None if location is CLEAR else location
    if attendees is not None:
        if attendees is CLEAR:
            body["attendees"] = []
        else:
            body["attendees"] = [{"email": e} for e in attendees]
    if start is not None:
        _require_aware(start, "start")
        body["start"] = _format_endpoint(start, all_day=bool(all_day))
    if end is not None:
        _require_aware(end, "end")
        body["end"] = _format_endpoint(end, all_day=bool(all_day))

    service = get_service()
    try:
        raw = (
            service.events()
            .patch(calendarId=calendar_id, eventId=event_id, body=body)
            .execute()
        )
    except HttpError as exc:
        raise MgdioAPIError(f"Calendar events.patch {event_id} failed: {exc}") from exc
    return _to_event(raw, calendar_id)


def delete_event(event_id: str, calendar_id: str = "primary") -> None:
    """Delete an event.

    Args:
        event_id: Event id.
        calendar_id: Owning calendar. Default ``"primary"``.

    Raises:
        MgdioAPIError: On any Calendar API HTTP error.
    """
    service = get_service()
    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    except HttpError as exc:
        raise MgdioAPIError(f"Calendar events.delete {event_id} failed: {exc}") from exc


def quick_add(
    text: str,
    calendar_id: str = "primary",
) -> CalendarEvent:
    """Create an event from a natural-language string.

    Google parses the text (e.g. ``"Lunch with Bob Tuesday 12pm"``) and
    creates an event accordingly. Useful but limited; pass anything
    structured through :func:`create_event` instead.

    Args:
        text: Natural-language event description.
        calendar_id: Target calendar. Default ``"primary"``.

    Returns:
        The created :class:`CalendarEvent`.

    Raises:
        MgdioAPIError: On any Calendar API HTTP error.
    """
    service = get_service()
    try:
        raw = service.events().quickAdd(calendarId=calendar_id, text=text).execute()
    except HttpError as exc:
        raise MgdioAPIError(f"Calendar events.quickAdd failed: {exc}") from exc
    return _to_event(raw, calendar_id)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _require_aware(value: datetime | None, name: str) -> None:
    if value is None:
        return
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(
            f"{name} must be timezone-aware "
            f"(got naive datetime: {value!r}). "
            f"Use datetime(..., tzinfo=...) or zoneinfo.ZoneInfo."
        )


def _format_endpoint(value: datetime, *, all_day: bool) -> dict[str, str]:
    if all_day:
        return {"date": value.date().isoformat()}
    tz_name = _resolve_tz_name(value)
    return {"dateTime": value.isoformat(), "timeZone": tz_name}


def _resolve_tz_name(value: datetime) -> str:
    """Best-effort IANA tz name for a tz-aware datetime."""
    tzinfo = value.tzinfo
    # zoneinfo.ZoneInfo and dateutil tzs expose .key or .zone; fall back
    # to the offset's str otherwise. Calendar accepts either an IANA
    # name or an offset string in timeZone.
    name = getattr(tzinfo, "key", None) or getattr(tzinfo, "zone", None)
    if name:
        return str(name)
    if tzinfo is timezone.utc:
        return "UTC"
    return str(tzinfo)


def _to_event(raw: dict, calendar_id: str) -> CalendarEvent:
    start_raw = raw.get("start", {}) or {}
    end_raw = raw.get("end", {}) or {}
    start_dt, all_day_start = _parse_endpoint(start_raw)
    end_dt, all_day_end = _parse_endpoint(end_raw)
    all_day = all_day_start or all_day_end

    attendees = tuple(
        att["email"]
        for att in (raw.get("attendees") or [])
        if isinstance(att, dict) and "email" in att
    )

    return CalendarEvent(
        id=raw.get("id", ""),
        calendar_id=calendar_id,
        summary=raw.get("summary", ""),
        description=raw.get("description", ""),
        location=raw.get("location", ""),
        start=start_dt,
        end=end_dt,
        all_day=all_day,
        attendees=attendees,
        creator=_extract_email(raw.get("creator")),
        organizer=_extract_email(raw.get("organizer")),
        html_link=raw.get("htmlLink", ""),
        status=raw.get("status", ""),
        created=_parse_rfc3339(raw.get("created", "")),
        updated=_parse_rfc3339(raw.get("updated", "")),
    )


def _extract_email(value: Any) -> str:
    if isinstance(value, dict):
        return value.get("email", "")
    return ""


def _parse_endpoint(endpoint: dict) -> tuple[datetime, bool]:
    """Return (tz-aware datetime, all_day_flag) for an event endpoint dict."""
    date_str = endpoint.get("date")
    if date_str:
        # All-day: anchor to UTC midnight so the dataclass shape stays uniform.
        parsed = date.fromisoformat(date_str)
        return (
            datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc),
            True,
        )
    datetime_str = endpoint.get("dateTime")
    if datetime_str:
        return _parse_rfc3339(datetime_str), False
    # Shouldn't normally happen; return epoch UTC so consumers don't crash.
    return datetime(1970, 1, 1, tzinfo=timezone.utc), False


def _parse_rfc3339(value: str) -> datetime:
    """Parse an RFC 3339 / ISO 8601 string, normalizing Z suffix."""
    if not value:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
