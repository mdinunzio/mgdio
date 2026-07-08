"""Google Geocoding API: forward (address -> lat/lng) and reverse.

Covers the Sheets helpers ``GOOGLEMAPS_ADDRESS_TO_LATLONG``,
``GOOGLEMAPS_PLACE_TO_ADDRESS`` (both forward geocoding -- the first
result's ``formatted_address`` / ``lat,lng``), and
``GOOGLEMAPS_LATLONG_TO_ADDRESS`` (reverse geocoding).
"""

from __future__ import annotations

from dataclasses import dataclass

from mgdio.maps.client import request


@dataclass(frozen=True, slots=True)
class GeocodeResult:
    """A single geocoding match.

    Attributes:
        formatted_address: The human-readable postal address.
        latitude: Latitude of the matched location.
        longitude: Longitude of the matched location.
        location_type: Precision, e.g. ``"ROOFTOP"`` or ``"APPROXIMATE"``.
        place_id: Stable Google place identifier.
        types: Feature types, e.g. ``("street_address",)``.
    """

    formatted_address: str
    latitude: float
    longitude: float
    location_type: str
    place_id: str
    types: tuple[str, ...]

    @property
    def latlng(self) -> str:
        """Return ``"lat, lng"`` -- matches the Sheets latlong helper output."""
        return f"{self.latitude}, {self.longitude}"


def geocode(address: str) -> list[GeocodeResult]:
    """Geocode an address or place name to coordinates.

    Args:
        address: A street address or place name, e.g.
            ``"10 Hanover Square, NY"`` or ``"Artemisia Domus, Naples"``.

    Returns:
        Matching :class:`GeocodeResult` objects (best match first);
        empty if the address wasn't found.

    Raises:
        MgdioAPIError: On any Maps API error.
    """
    body = request("geocode/json", {"address": address})
    return [_to_result(item) for item in body.get("results", [])]


def reverse_geocode(latitude: float, longitude: float) -> list[GeocodeResult]:
    """Reverse-geocode a coordinate to postal addresses.

    Args:
        latitude: Latitude to look up.
        longitude: Longitude to look up.

    Returns:
        Matching :class:`GeocodeResult` objects (best match first);
        empty if nothing was found.

    Raises:
        MgdioAPIError: On any Maps API error.
    """
    body = request("geocode/json", {"latlng": f"{latitude},{longitude}"})
    return [_to_result(item) for item in body.get("results", [])]


def _to_result(raw: dict) -> GeocodeResult:
    location = raw.get("geometry", {}).get("location", {})
    return GeocodeResult(
        formatted_address=raw.get("formatted_address", ""),
        latitude=float(location.get("lat", 0.0)),
        longitude=float(location.get("lng", 0.0)),
        location_type=raw.get("geometry", {}).get("location_type", ""),
        place_id=raw.get("place_id", ""),
        types=tuple(raw.get("types", [])),
    )
