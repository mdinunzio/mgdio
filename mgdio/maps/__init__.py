"""Google Maps Platform: geocoding + directions on an API key.

Unlike the OAuth-based Google service subpackages, Maps authenticates
with an API key stored under ``mgdio:maps`` (see
:mod:`mgdio.auth.maps`). Covers the common Google Sheets map helpers:
address <-> coordinates (geocoding) and distance / duration /
turn-by-turn directions between two locations.
"""

from __future__ import annotations

from mgdio.maps.client import reset_session_cache
from mgdio.maps.directions import (
    Route,
    RouteStep,
    fetch_route,
    fetch_routes,
)
from mgdio.maps.geocoding import (
    GeocodeResult,
    geocode,
    reverse_geocode,
)

__all__ = [
    "GeocodeResult",
    "Route",
    "RouteStep",
    "fetch_route",
    "fetch_routes",
    "geocode",
    "reset_session_cache",
    "reverse_geocode",
]
