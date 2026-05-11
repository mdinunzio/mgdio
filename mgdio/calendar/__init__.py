"""Google Calendar subpackage public API.

Built on top of :mod:`mgdio.auth.google` -- the unified Google OAuth flow
provides the credentials; this subpackage just wraps the Calendar v3 API.
"""

from __future__ import annotations

from mgdio.calendar.calendars import Calendar, fetch_calendars
from mgdio.calendar.client import get_service
from mgdio.calendar.events import (
    CLEAR,
    CalendarEvent,
    create_event,
    delete_event,
    fetch_event,
    fetch_events,
    quick_add,
    update_event,
)

__all__ = [
    "CLEAR",
    "Calendar",
    "CalendarEvent",
    "create_event",
    "delete_event",
    "fetch_calendars",
    "fetch_event",
    "fetch_events",
    "get_service",
    "quick_add",
    "update_event",
]
