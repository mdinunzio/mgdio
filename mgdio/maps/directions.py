"""Google Directions API: distance, duration, and turn-by-turn steps.

Covers the Sheets helpers ``GOOGLEMAPS_DISTANCE``, ``GOOGLEMAPS_DURATION``,
and ``GOOGLEMAPS_DIRECTIONS``. A single :func:`fetch_route` call returns a
:class:`Route` carrying the distance, duration, and steps; distance
defaults to **imperial** (miles) text to match typical Sheets usage,
while raw meters/seconds are always available.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mgdio.exceptions import MgdioAPIError
from mgdio.maps.client import request

_VALID_MODES = frozenset({"driving", "walking", "bicycling", "transit"})
_VALID_UNITS = frozenset({"imperial", "metric"})
_TAG_RE = re.compile(r"<[^>]+>")
_METERS_PER_MILE = 1609.344


def _strip_html(html: str) -> str:
    """Strip HTML tags from a Directions ``html_instructions`` string."""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", html)).strip()


@dataclass(frozen=True, slots=True)
class RouteStep:
    """One turn-by-turn step of a route.

    Attributes:
        instruction: Plain-text instruction (HTML tags stripped).
        distance_meters: Step distance in meters.
        distance_text: Localized distance string, e.g. ``"0.2 mi"``.
        duration_seconds: Step duration in seconds.
        duration_text: Localized duration string, e.g. ``"1 min"``.
        travel_mode: e.g. ``"DRIVING"`` or ``"WALKING"``.
    """

    instruction: str
    distance_meters: int
    distance_text: str
    duration_seconds: int
    duration_text: str
    travel_mode: str


@dataclass(frozen=True, slots=True)
class Route:
    """A single route between an origin and destination.

    Attributes:
        distance_meters: Total distance in meters (summed across legs).
        distance_text: Localized total-distance string (units-dependent).
        duration_seconds: Total duration in seconds.
        duration_text: Localized total-duration string.
        start_address: Formatted origin address (from the first leg).
        end_address: Formatted destination address (from the last leg).
        summary: Google's short route summary, e.g. ``"I-95 S"``.
        steps: All turn-by-turn steps across every leg.
    """

    distance_meters: int
    distance_text: str
    duration_seconds: int
    duration_text: str
    start_address: str
    end_address: str
    summary: str
    steps: tuple[RouteStep, ...]

    @property
    def distance_miles(self) -> float:
        """Total distance in miles."""
        return self.distance_meters / _METERS_PER_MILE

    @property
    def distance_km(self) -> float:
        """Total distance in kilometers."""
        return self.distance_meters / 1000.0

    @property
    def duration_minutes(self) -> float:
        """Total duration in minutes."""
        return self.duration_seconds / 60.0

    @property
    def instructions(self) -> list[str]:
        """Plain-text step instructions, in order."""
        return [step.instruction for step in self.steps]


def fetch_routes(
    origin: str,
    destination: str,
    *,
    mode: str = "driving",
    units: str = "imperial",
    alternatives: bool = False,
) -> list[Route]:
    """Fetch route(s) between two locations.

    Args:
        origin: Start address / place / ``"lat,lng"``.
        destination: End address / place / ``"lat,lng"``.
        mode: ``"driving"`` (default), ``"walking"``, ``"bicycling"``, or
            ``"transit"``.
        units: ``"imperial"`` (default, miles) or ``"metric"`` (km). Only
            affects the localized ``*_text`` fields; raw meters/seconds
            are unaffected.
        alternatives: If True, ask Google for alternative routes.

    Returns:
        Matching :class:`Route` objects; empty if no route was found.

    Raises:
        ValueError: If ``mode`` or ``units`` is not recognized.
        MgdioAPIError: On any Maps API error.
    """
    if mode not in _VALID_MODES:
        raise ValueError(f"mode must be one of {sorted(_VALID_MODES)}; got {mode!r}.")
    if units not in _VALID_UNITS:
        raise ValueError(f"units must be one of {sorted(_VALID_UNITS)}; got {units!r}.")
    params = {
        "origin": origin,
        "destination": destination,
        "mode": mode,
        "units": units,
    }
    if alternatives:
        params["alternatives"] = "true"
    body = request("directions/json", params)
    return [_to_route(item) for item in body.get("routes", [])]


def fetch_route(
    origin: str,
    destination: str,
    *,
    mode: str = "driving",
    units: str = "imperial",
) -> Route:
    """Fetch the single best route between two locations.

    Convenience wrapper over :func:`fetch_routes` returning the top
    result. Raises if no route exists (matching the Sheets helpers'
    "No route found!" behavior).

    Args:
        origin: Start address / place / ``"lat,lng"``.
        destination: End address / place / ``"lat,lng"``.
        mode: Travel mode (see :func:`fetch_routes`).
        units: ``"imperial"`` (default) or ``"metric"``.

    Returns:
        The best :class:`Route`.

    Raises:
        ValueError: If ``mode`` or ``units`` is not recognized.
        MgdioAPIError: On any Maps API error, or if no route was found.
    """
    routes = fetch_routes(origin, destination, mode=mode, units=units)
    if not routes:
        raise MgdioAPIError(
            f"No route found from {origin!r} to {destination!r} " f"(mode={mode})."
        )
    return routes[0]


def _to_route(raw: dict) -> Route:
    legs = raw.get("legs", [])
    distance_meters = sum(leg.get("distance", {}).get("value", 0) for leg in legs)
    duration_seconds = sum(leg.get("duration", {}).get("value", 0) for leg in legs)
    # Prefer the localized text when there's exactly one leg; otherwise
    # fall back to a derived value so multi-leg totals stay sensible.
    if len(legs) == 1:
        distance_text = legs[0].get("distance", {}).get("text", "")
        duration_text = legs[0].get("duration", {}).get("text", "")
    else:
        distance_text = f"{distance_meters} m"
        duration_text = f"{duration_seconds} s"

    steps: list[RouteStep] = []
    for leg in legs:
        for step in leg.get("steps", []):
            steps.append(_to_step(step))

    return Route(
        distance_meters=distance_meters,
        distance_text=distance_text,
        duration_seconds=duration_seconds,
        duration_text=duration_text,
        start_address=legs[0].get("start_address", "") if legs else "",
        end_address=legs[-1].get("end_address", "") if legs else "",
        summary=raw.get("summary", ""),
        steps=tuple(steps),
    )


def _to_step(raw: dict) -> RouteStep:
    return RouteStep(
        instruction=_strip_html(raw.get("html_instructions", "")),
        distance_meters=int(raw.get("distance", {}).get("value", 0)),
        distance_text=raw.get("distance", {}).get("text", ""),
        duration_seconds=int(raw.get("duration", {}).get("value", 0)),
        duration_text=raw.get("duration", {}).get("text", ""),
        travel_mode=raw.get("travel_mode", ""),
    )
