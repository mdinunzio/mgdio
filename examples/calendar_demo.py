"""Google Calendar end-to-end demo for the mgdio package.

Run this after installing mgdio and completing the one-time OAuth setup
(``uv run mgdio auth google``).

Walks through:

1. List the calendars the authenticated user has access to.
2. Show events in the next 7 days on the primary calendar.
3. Create a throwaway event ~30 days out (tagged with a uuid).
4. Update its summary; clear its description with the CLEAR sentinel.
5. Quick-add a natural-language event.
6. Delete both events.

Usage:
    uv run python examples/calendar_demo.py

NOTE: this file is intentionally NOT named ``calendar.py`` -- Python's
``sys.path[0]`` includes the directory of the script being run, so a
script at ``examples/calendar.py`` would shadow the stdlib ``calendar``
module that ``google-auth`` imports transitively, causing a misleading
circular-import error in ``from mgdio.calendar import ...``. If you copy
this demo into your own project, keep the filename distinct from
``calendar`` for the same reason.
"""

from __future__ import annotations

import uuid
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


def main() -> None:
    """Run the full Calendar demo cycle."""
    print("== 1. Calendars on this account ==")
    for cal in fetch_calendars():
        marker = "*" if cal.primary else " "
        print(f"   {marker} {cal.access_role:18} {cal.summary}  ({cal.id})")

    print("\n== 2. Events on primary in the next 7 days ==")
    now = datetime.now(timezone.utc)
    upcoming = fetch_events(
        time_min=now,
        time_max=now + timedelta(days=7),
        max_results=10,
    )
    if not upcoming:
        print("   (none)")
    for ev in upcoming:
        when = f"{ev.start:%Y-%m-%d}" if ev.all_day else f"{ev.start:%Y-%m-%d %H:%M}"
        print(f"   {when}  {ev.summary}  [{ev.id}]")

    print("\n== 3. Create a throwaway event ~30 days out ==")
    token = uuid.uuid4().hex[:8]
    summary = f"mgdio demo {token}"
    start = now + timedelta(days=30)
    end = start + timedelta(hours=1)
    created = create_event(
        summary=summary,
        start=start,
        end=end,
        description="initial body -- will be cleared by update",
        location="Localhost Cafe",
    )
    print(f"   created: {created.id}")
    print(f"   url:     {created.html_link}")

    print("\n== 4. Update summary + clear description with CLEAR ==")
    updated = update_event(
        created.id,
        summary=f"{summary} (renamed)",
        description=CLEAR,
    )
    refreshed = fetch_event(updated.id)
    print(f"   summary now: {refreshed.summary!r}")
    print(f"   description: {refreshed.description!r}")

    print("\n== 5. Quick-add a natural-language event ==")
    quick = quick_add(f"mgdio quickadd {token} tomorrow 3pm for 30 minutes")
    print(f"   created: {quick.id}")
    print(f"   summary: {quick.summary}")
    print(f"   start:   {quick.start.isoformat()}")

    print("\n== 6. Delete both throwaway events ==")
    delete_event(created.id)
    delete_event(quick.id)
    print("   deleted.")

    print(f"\nDone. (Demo token: {token})")


if __name__ == "__main__":
    main()
