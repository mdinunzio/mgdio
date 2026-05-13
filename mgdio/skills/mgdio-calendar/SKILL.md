---
name: mgdio-calendar
description: Read, create, update, and delete Google Calendar events via the
  `mgdio calendar` CLI. Use this when the user asks what's on their
  calendar today/this week, wants to list calendars they have access to,
  fetch a specific event, schedule a meeting, reschedule or rename an
  event, add/remove attendees, delete an event, or quick-add an event
  from a natural-language phrase like "Lunch with Bob Tuesday 12pm".
---

# mgdio Calendar

Read and write Google Calendar events through the user's account via the
`mgdio` CLI.

## Prerequisite

The user must have authenticated once: `mgdio auth google`. The same token
covers Gmail, Calendar, and Sheets.

## Safety contract

**Read** operations (`list-cals`, `list-events`, `get`) are safe to
perform on user request. **Write** operations (`create`, `update`,
`delete`, `quick-add`) MUST be confirmed with the user before invocation.
Paraphrase what you're about to do — calendar, event summary, start/end,
attendees — and wait for explicit approval, even if the user's prompt
sounded like permission. **`delete` is irreversible** — be especially
explicit about which event will be removed. Never chain multiple writes
without re-confirming each one.

## CLI: read

```bash
# List every calendar the user can access (primary + secondary + shared)
mgdio calendar list-cals

# List upcoming events on primary (default) with optional bounds
mgdio calendar list-events --max 10
mgdio calendar list-events --query "standup" --max 5
mgdio calendar list-events \
  --time-min "2026-05-12T00:00:00-04:00" \
  --time-max "2026-05-19T00:00:00-04:00"

# Pick an id from list-events output and fetch full details
mgdio calendar get <event_id>
```

`mgdio calendar list-events` prints `YYYY-MM-DD HH:MM  <summary>  [<event_id>]`
(or `YYYY-MM-DD` if the event is all-day). The `[<event_id>]` is the
handle for `get` / `update` / `delete`.

**`--time-min` and `--time-max` must include a timezone offset** (e.g.
`...T14:00:00-04:00` or `...T14:00:00Z`). Naive datetimes are rejected
with a clear error. When the user says "this week" or "today", convert
to a tz-aware ISO datetime in their local zone before invoking.

## CLI: write (REQUIRES CONFIRMATION)

```bash
# Create a timed event (start/end ISO with tz offset)
mgdio calendar create --summary "Coffee with Bob" \
  --start "2026-05-15T10:00:00-04:00" \
  --end   "2026-05-15T11:00:00-04:00" \
  --location "The Spot" --description "Q2 plans" \
  --attendee bob@example.com

# All-day event (Calendar treats end-date as exclusive)
mgdio calendar create --summary "Holiday" \
  --start "2026-07-04T00:00:00-04:00" \
  --end   "2026-07-05T00:00:00-04:00" \
  --all-day

# Update: only fields you pass are changed
mgdio calendar update <event_id> --summary "renamed"

# Delete (irreversible)
mgdio calendar delete <event_id>

# Natural-language quick-add (Google parses the string)
mgdio calendar quick-add "Lunch with Alice Tuesday 12pm at Bistro"
```

## Python (when chaining is needed)

```python
from datetime import datetime, timezone
from mgdio.calendar import (
    CLEAR,
    fetch_events, fetch_event, fetch_calendars,
    create_event, update_event, delete_event, quick_add,
    CalendarEvent, Calendar,
)
```

`fetch_events(calendar_id="primary", *, time_min=None, time_max=None,
query="", max_results=50, single_events=True) -> list[CalendarEvent]`.
`fetch_event(event_id, calendar_id="primary") -> CalendarEvent`.
`fetch_calendars() -> list[Calendar]`.

`create_event(summary, start, end, *, description=None, location=None,
attendees=None, calendar_id="primary", all_day=False) -> CalendarEvent`.

`update_event(event_id, *, summary=..., start=..., end=..., description=...,
location=..., attendees=..., all_day=None, calendar_id="primary") ->
CalendarEvent`. Uses tri-state PATCH semantics (see Gotchas).

`delete_event(event_id, calendar_id="primary") -> None`.
`quick_add(text, calendar_id="primary") -> CalendarEvent`.

`CalendarEvent` fields: `id, calendar_id, summary, description, location,
start: datetime, end: datetime, all_day: bool, attendees: tuple[str, ...],
creator, organizer, html_link, status, created: datetime, updated: datetime`.

`Calendar` fields: `id, summary, description, time_zone, primary: bool,
access_role`.

## Gotchas

- **All datetimes must be timezone-aware.** Naive datetimes raise
  `ValueError` at the boundary. In Python:
  `datetime(2026, 5, 15, 10, tzinfo=ZoneInfo("America/New_York"))` ✅,
  `datetime(2026, 5, 15, 10)` ❌. Same on the CLI: every `--start`,
  `--end`, `--time-min`, `--time-max` needs a `±HH:MM` offset (or `Z`).
- **`CLEAR` sentinel** for `update_event`: `description=CLEAR` nulls the
  field on the server; `description=None` (the default) is a no-op.
  `start` / `end` cannot be cleared — they're required by the API.
- **All-day events**: the dataclass stores `start` / `end` as UTC midnight
  with `all_day=True`; Calendar API treats the end date as exclusive
  (a one-day event has end = start + 1 day).
- **Recurring events**: `single_events=True` (default) expands recurrence
  into individual instances ordered by start time. Pass `False` to get
  the underlying recurring event once (ordered by last-modified).
- **`calendar_id`** is the long opaque string for non-primary calendars,
  from `mgdio calendar list-cals`. `"primary"` is the magic alias for
  the user's own calendar.
