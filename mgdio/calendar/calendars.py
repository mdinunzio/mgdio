"""Calendar listing: ``calendarList.list``."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from googleapiclient.errors import HttpError

from mgdio.calendar.client import get_service
from mgdio.exceptions import MgdioAPIError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Calendar:
    """A calendar in the authenticated user's calendarList.

    Attributes:
        id: Calendar id (use this as ``calendar_id`` in event functions).
        summary: Display name.
        description: Optional description; empty string when missing.
        time_zone: IANA tz name, e.g. ``"America/New_York"``.
        primary: True for the user's primary calendar.
        access_role: One of ``"owner"``, ``"writer"``, ``"reader"``,
            ``"freeBusyReader"``.
    """

    id: str
    summary: str
    description: str
    time_zone: str
    primary: bool
    access_role: str


def fetch_calendars() -> list[Calendar]:
    """List every calendar the authenticated user has access to.

    Returns:
        List of :class:`Calendar`, including the primary calendar and
        any secondary or shared calendars.

    Raises:
        MgdioAPIError: On any Calendar API HTTP error.
    """
    service = get_service()
    try:
        resp = service.calendarList().list().execute()
    except HttpError as exc:
        raise MgdioAPIError(f"Calendar calendarList.list failed: {exc}") from exc
    return [_to_calendar(item) for item in resp.get("items", [])]


def _to_calendar(raw: dict) -> Calendar:
    return Calendar(
        id=raw.get("id", ""),
        summary=raw.get("summary", ""),
        description=raw.get("description", ""),
        time_zone=raw.get("timeZone", ""),
        primary=bool(raw.get("primary", False)),
        access_role=raw.get("accessRole", ""),
    )
