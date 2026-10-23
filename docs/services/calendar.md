# Calendar

List calendars, list events, full event CRUD, and Google's natural-language
"quick add". Uses the shared Google login from
[`mgdio auth google`](../auth.md#first-run-auth).

| | |
| --- | --- |
| Import | `from mgdio.calendar import fetch_events, create_event, update_event, CLEAR, ...` |
| Returns | [`CalendarEvent`](../reference/calendar.md) and `Calendar` frozen dataclasses |
| CLI | `mgdio calendar list-cals / list-events / get / create / update / delete / quick-add` |
| Reference | [mgdio.calendar](../reference/calendar.md) |
| Example | [`examples/calendar_demo.py`](https://github.com/mdinunzio/mgdio/blob/main/examples/calendar_demo.py) |

## Python

```python
from datetime import datetime, timedelta, timezone

from mgdio.calendar import (
    CLEAR,
    create_event,
    delete_event,
    fetch_calendars,
    fetch_event,
    fetch_events,
    quick_add,
    update_event,
)

# Every calendar you can access (primary + secondary + shared).
for cal in fetch_calendars():
    print(cal.id, cal.summary, "primary" if cal.primary else cal.access_role)

# Events in a time window. Datetimes must be tz-aware; naive ones raise.
now = datetime.now(timezone.utc)
events = fetch_events(
    time_min=now,
    time_max=now + timedelta(days=7),
    query="lunch",
    max_results=20,
)
for ev in events:
    when = f"{ev.start:%Y-%m-%d}" if ev.all_day else f"{ev.start:%Y-%m-%d %H:%M}"
    print(when, ev.summary, ev.id)

# Create a timed event.
created = create_event(
    summary="Coffee with Bob",
    start=now + timedelta(days=2, hours=10),
    end=now + timedelta(days=2, hours=11),
    description="check in on Q2 plans",
    location="The Spot",
    attendees=["bob@example.com"],
)

# Create an all-day event. The end date is exclusive.
create_event(
    summary="Holiday",
    start=datetime(2026, 7, 4, tzinfo=timezone.utc),
    end=datetime(2026, 7, 5, tzinfo=timezone.utc),
    all_day=True,
)

# Update with tri-state PATCH semantics:
#   None (default) -> field is left alone
#   CLEAR          -> field is nulled on the server
#   any value      -> field is set
update_event(created.id, summary="Coffee with Bob (rescheduled)")
update_event(created.id, description=CLEAR, location=CLEAR)

# Natural-language creation; Google parses the text.
quick_add("Lunch with Alice Tuesday 12pm")

delete_event(created.id)
```

Every function accepts a trailing `profile=` keyword to pick a Google account.

!!! note "Why the example file is called `calendar_demo.py`"
    A script literally named `calendar.py` would shadow the stdlib `calendar`
    module that google-auth imports transitively. Avoid that name in your own
    projects too.

## CLI

```bash
mgdio calendar list-cals
mgdio calendar list-events --max 10
mgdio calendar list-events --time-min "2026-05-09T00:00:00-04:00" \
  --time-max "2026-05-16T00:00:00-04:00" --query lunch
mgdio calendar get <event_id>
mgdio calendar create --summary "Coffee with Bob" \
  --start "2026-05-12T10:00:00-04:00" --end "2026-05-12T11:00:00-04:00" \
  --attendee bob@example.com --location "The Spot"
mgdio calendar update <event_id> --summary "renamed"
mgdio calendar delete <event_id>
mgdio calendar quick-add "Lunch with Alice Tuesday 12pm"
```

Add `--profile <slug>` to any command to choose the Google account.
