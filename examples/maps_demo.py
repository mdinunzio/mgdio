"""Google Maps end-to-end demo for the mgdio package.

Run this after installing mgdio and completing the one-time API-key setup
(``uv run mgdio auth maps``). It exercises geocoding (forward + reverse)
and routing (distance / duration / directions) -- the same operations as
the common GOOGLEMAPS_* Google Sheets helpers.

Note: each call consumes Google Maps Platform quota (billable).

Usage:
    uv run python examples/maps_demo.py
"""

from __future__ import annotations

from mgdio.maps import fetch_route, geocode, reverse_geocode


def main() -> None:
    """Run the Maps demo (geocoding + routing)."""
    print("== 1. Geocode an address -> coordinates ==")
    hits = geocode("10 Hanover Square, New York, NY")
    if hits:
        best = hits[0]
        print(f"   address: {best.formatted_address}")
        print(f"   latlng:  {best.latlng}  [{best.location_type}]")
    else:
        print("   (no match)")

    print("\n== 2. Reverse-geocode coordinates -> address ==")
    rev = reverse_geocode(40.7127753, -74.0059728)
    if rev:
        print(f"   {rev[0].formatted_address}")

    print("\n== 3. Geocode a place by name ==")
    place = geocode("Statue of Liberty")
    if place:
        print(f"   {place[0].formatted_address}")

    print("\n== 4. Distance + duration (driving) ==")
    route = fetch_route("NY 10005", "Hoboken, NJ", mode="driving")
    print(f"   distance: {route.distance_text}  ({route.distance_meters} m)")
    print(f"   duration: {route.duration_text}  ({route.duration_seconds} s)")

    print("\n== 5. Walking directions (first few steps) ==")
    walk = fetch_route("NY 10005", "Hoboken, NJ", mode="walking")
    print(f"   {walk.distance_text}, {walk.duration_text}")
    for i, step in enumerate(walk.instructions[:5], start=1):
        print(f"     {i}. {step}")

    print("\nDone.")


if __name__ == "__main__":
    main()
