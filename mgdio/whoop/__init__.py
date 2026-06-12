"""Whoop subpackage public API.

Built on top of :mod:`mgdio.auth.whoop` -- the auth subsystem provides
the OAuth access token (refreshed automatically); this subpackage wraps
the Whoop v2 REST API with typed dataclasses.

All ``fetch_*`` collection functions auto-paginate up to ``max_records``
(default 100). Datetimes are tz-aware. Whoop is read-only here.
"""

from __future__ import annotations

from mgdio.whoop.client import request, reset_session_cache
from mgdio.whoop.cycles import Cycle, fetch_cycles
from mgdio.whoop.recovery import Recovery, fetch_recoveries
from mgdio.whoop.sleep import Sleep, fetch_sleeps
from mgdio.whoop.user import (
    BodyMeasurement,
    Profile,
    fetch_body_measurement,
    fetch_profile,
)
from mgdio.whoop.workouts import Workout, fetch_workouts

__all__ = [
    "BodyMeasurement",
    "Cycle",
    "Profile",
    "Recovery",
    "Sleep",
    "Workout",
    "fetch_body_measurement",
    "fetch_cycles",
    "fetch_profile",
    "fetch_recoveries",
    "fetch_sleeps",
    "fetch_workouts",
    "request",
    "reset_session_cache",
]
