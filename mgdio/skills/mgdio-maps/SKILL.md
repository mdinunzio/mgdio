---
name: mgdio-maps
description: Geocode addresses and compute travel distance/duration/directions
  via the `mgdio maps` CLI (Google Maps Platform). Use this when the user
  wants the coordinates of an address, the address of a lat/long point,
  the formatted address of a place, or the driving/walking/bicycling/transit
  distance, travel time, or turn-by-turn directions between two locations.
  Mirrors the common GOOGLEMAPS_* Google Sheets helper functions.
---

# mgdio Maps

Geocode addresses and compute routes with the `mgdio maps` CLI, backed by
the Google Maps Geocoding + Directions APIs.

## Prerequisite

Maps uses a **Google Maps Platform API key**, NOT the shared Google
login used by Gmail/Sheets/Calendar/Drive. The user must have run
`mgdio auth maps` once: it opens a local page with Cloud Console
instructions (enable the Geocoding + Directions APIs, create a key,
billing must be enabled) and stores the key under `mgdio:maps`. If a
command fails with an auth error or "REQUEST_DENIED", tell them to run
`mgdio auth maps`.

## Safety contract

The Maps integration is **read-only** -- it only reads geocoding/route
data, with no write/update/delete operations, so nothing here needs
confirmation. (For consistency with the other mgdio skills: any write
operation MUST be confirmed with the user before invocation -- but Maps
exposes none.) Note each call consumes Google Maps API quota (billable).

## CLI

```bash
# Address / place -> formatted address + coordinates
mgdio maps geocode "10 Hanover Square, NY"
mgdio maps geocode "Artemisia Domus, Naples"

# Coordinate -> postal address (single "lat,lng" token; the negative
# longitude must not be split, so it's one argument)
mgdio maps reverse "40.714,-74.006"

# Distance / duration between two locations
mgdio maps distance "NY 10005" "Hoboken NJ"
mgdio maps duration "NY 10005" "Hoboken NJ" --mode walking

# Turn-by-turn directions (prints distance, duration, then steps)
mgdio maps directions "NY 10005" "Hoboken NJ"
```

`--mode` is `driving` (default), `walking`, `bicycling`, or `transit`.
`--units` is `imperial` (default, miles) or `metric` (km); it only
affects the printed text, not the underlying numbers.

## Python (for chaining / raw numbers)

```python
from mgdio.maps import (
    geocode, reverse_geocode, fetch_route, fetch_routes,
    GeocodeResult, Route, RouteStep,
)

# Forward geocoding -> list[GeocodeResult] (best match first)
hits = geocode("10 Hanover Square, NY")
first = hits[0]
first.formatted_address      # "10 Hanover Square, New York, NY 10004, USA"
first.latitude, first.longitude
first.latlng                 # "40.70..., -74.01..."  (Sheets-style string)

# Reverse geocoding
reverse_geocode(40.714, -74.006)[0].formatted_address

# Routing -> a Route with raw + text distance/duration and steps
route = fetch_route("NY 10005", "Hoboken NJ", mode="driving", units="imperial")
route.distance_text          # "5.2 mi"    (units-dependent text)
route.duration_text          # "12 mins"
route.distance_meters        # 8368        (always raw meters)
route.duration_seconds       # 720
route.distance_miles         # 5.2  (also .distance_km, .duration_minutes)
route.instructions           # ["Head north on Broadway", ...] (HTML stripped)
```

`fetch_route` returns the single best route and **raises `MgdioAPIError`
if no route exists** (matching the Sheets "No route found!" behavior).
Use `fetch_routes(..., alternatives=True) -> list[Route]` (empty on no
result) when you want alternatives or to handle "no route" without an
exception.

## Mapping from the Google Sheets helpers

- `GOOGLEMAPS_ADDRESS_TO_LATLONG(addr)` -> `geocode(addr)[0].latlng`
- `GOOGLEMAPS_PLACE_TO_ADDRESS(place)` -> `geocode(place)[0].formatted_address`
- `GOOGLEMAPS_LATLONG_TO_ADDRESS(lat,lng)` -> `reverse_geocode(lat,lng)[0].formatted_address`
- `GOOGLEMAPS_DISTANCE(a,b,mode)` -> `fetch_route(a,b,mode=mode).distance_text`
- `GOOGLEMAPS_DURATION(a,b,mode)` -> `fetch_route(a,b,mode=mode).duration_text`
- `GOOGLEMAPS_DIRECTIONS(a,b,mode)` -> `fetch_route(a,b,mode=mode).instructions`

## Gotchas

- **Separate API key.** Maps does not use `mgdio auth google`; it needs
  its own key via `mgdio auth maps`.
- **Reverse coords are one argument.** Pass `"lat,lng"` as a single
  quoted token so the negative longitude isn't read as a CLI option.
- **`geocode` returns a list.** Take `[0]` for the best match; it's empty
  (not an error) when nothing matches.
- **`units` only changes text.** `distance_meters` / `duration_seconds`
  are always raw SI; use the `*_miles` / `*_minutes` / `*_km` properties
  for converted numbers.
