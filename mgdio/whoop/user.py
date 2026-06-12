"""Whoop user: profile + body-measurement single-object endpoints."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from mgdio.whoop.client import request

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Profile:
    """Basic Whoop user profile (``/v2/user/profile/basic``).

    Attributes:
        user_id: Whoop user id.
        email: Account email.
        first_name: Given name.
        last_name: Family name.
    """

    user_id: int | None
    email: str
    first_name: str
    last_name: str


@dataclass(frozen=True, slots=True)
class BodyMeasurement:
    """Whoop body measurements (``/v2/user/measurement/body``).

    Attributes:
        height_meter: Height in meters.
        weight_kilogram: Weight in kilograms.
        max_heart_rate: Maximum heart rate in bpm.
    """

    height_meter: float | None
    weight_kilogram: float | None
    max_heart_rate: float | None


def fetch_profile() -> Profile:
    """Fetch the authenticated user's basic profile.

    Returns:
        A :class:`Profile`.

    Raises:
        MgdioAPIError: On any Whoop API error.
    """
    raw = request("GET", "/v2/user/profile/basic")
    return Profile(
        user_id=raw.get("user_id"),
        email=raw.get("email", ""),
        first_name=raw.get("first_name", ""),
        last_name=raw.get("last_name", ""),
    )


def fetch_body_measurement() -> BodyMeasurement:
    """Fetch the authenticated user's body measurements.

    Returns:
        A :class:`BodyMeasurement`.

    Raises:
        MgdioAPIError: On any Whoop API error.
    """
    raw = request("GET", "/v2/user/measurement/body")
    return BodyMeasurement(
        height_meter=raw.get("height_meter"),
        weight_kilogram=raw.get("weight_kilogram"),
        max_heart_rate=raw.get("max_heart_rate"),
    )
