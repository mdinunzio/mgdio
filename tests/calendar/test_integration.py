"""Opt-in integration tests that hit the real Calendar API.

Skipped unless ``MGDIO_RUN_INTEGRATION=1``. Creates a throwaway event,
exercises update + fetch + quick_add, then deletes both events. Lists
calendars to confirm at least the primary calendar is present.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.integration

if os.getenv("MGDIO_RUN_INTEGRATION") != "1":
    pytest.skip(
        "MGDIO_RUN_INTEGRATION!=1; skipping real-API tests",
        allow_module_level=True,
    )


def test_list_calendars_returns_primary():
    from mgdio.calendar import fetch_calendars

    cals = fetch_calendars()
    assert any(c.primary for c in cals)


def test_full_event_cycle():
    from mgdio.calendar import (
        CLEAR,
        create_event,
        delete_event,
        fetch_event,
        fetch_events,
        quick_add,
        update_event,
    )

    token = uuid.uuid4().hex[:8]
    summary = f"mgdio integration {token}"
    start = datetime.now(timezone.utc) + timedelta(days=30)
    end = start + timedelta(hours=1)

    created = create_event(
        summary=summary,
        start=start,
        end=end,
        description="initial body",
        location="here",
    )
    assert created.summary == summary

    fetched = fetch_event(created.id)
    assert fetched.id == created.id
    assert fetched.description == "initial body"

    updated = update_event(
        created.id,
        summary=f"{summary} renamed",
        description=CLEAR,
    )
    assert updated.summary.endswith("renamed")
    assert updated.description == ""

    hits = fetch_events(
        time_min=start - timedelta(days=1),
        time_max=end + timedelta(days=1),
        query=token,
        max_results=5,
    )
    assert any(token in ev.summary for ev in hits)

    quick = quick_add(f"mgdio quickadd {token} tomorrow 3pm for 30 minutes")

    delete_event(created.id)
    delete_event(quick.id)
