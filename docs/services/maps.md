# Maps

Geocoding (address to coordinates and back) and routing (distance, duration,
turn-by-turn directions). Covers the common `GOOGLEMAPS_*` Google Sheets
helpers.

| | |
| --- | --- |
| Import | `from mgdio.maps import geocode, reverse_geocode, fetch_route, fetch_routes` |
| Returns | [`GeocodeResult`](../reference/maps.md), `Route`, `RouteStep` frozen dataclasses |
| CLI | `mgdio maps geocode / reverse / distance / duration / directions` |
| Reference | [mgdio.maps](../reference/maps.md) |
| Example | [`examples/maps_demo.py`](https://github.com/mdinunzio/mgdio/blob/main/examples/maps_demo.py) |

## Setup

Google Maps Platform uses an **API key**, not the shared Google OAuth login.

```bash
mgdio auth maps              # opens a setup page
mgdio auth maps --headless   # paste the key on the terminal instead
```

The setup page walks you through creating a key in the Cloud Console: enable
the **Geocoding API** and **Directions API** (billing must be enabled, even for
the free tier), paste the key, and mgdio validates it with a test geocode before
storing it in the keyring under `mgdio:maps`.

!!! danger "Cap usage at the free tier"
    Maps Platform requires a billing account and has **no automatic spending
    cap**. Budget alerts only notify. The reliable hard cap is a **per-API
    daily quota**: when it is hit, requests fail instead of being billed.

    In the [Cloud Console](https://console.cloud.google.com/google/maps-apis/quotas)
    go to *Google Maps Platform → Quotas*, pick the **Geocoding API**, set
    **Requests per day** to a low number such as `500`, then repeat for the
    **Directions API**. Quotas reset at midnight Pacific. Restricting the key
    to those two APIs and adding a budget alert are good hygiene, but the
    daily quota is what prevents charges.

## Python

```python
from mgdio.maps import fetch_route, geocode, reverse_geocode

# Address / place -> coordinates (list, best match first).
hit = geocode("10 Hanover Square, NY")[0]
print(hit.formatted_address, hit.latitude, hit.longitude)
print(hit.latlng)                       # "40.70..., -74.01..." (Sheets-style)

# Formatted address of a place.
print(geocode("Statue of Liberty")[0].formatted_address)

# Coordinate -> postal address.
print(reverse_geocode(40.7127753, -74.0059728)[0].formatted_address)

# Distance / duration / directions between two locations.
route = fetch_route("NY 10005", "Hoboken NJ", mode="driving")
print(route.distance_text, route.duration_text)       # "5.2 mi" "12 mins"
print(route.distance_meters, route.duration_seconds)  # raw SI, always present
print(route.distance_miles, route.duration_minutes)   # converted numbers
for step in route.instructions:                       # HTML-stripped steps
    print(step)
```

`fetch_route` returns the best route and raises `MgdioAPIError` when none
exists (matching the Sheets "No route found!" behavior). `fetch_routes`
returns a list (empty on no result) and accepts `alternatives=True`. `mode` is
`driving` (default), `walking`, `bicycling`, or `transit`. `units` is
`imperial` (default) or `metric` and only affects the `*_text` fields.

## CLI

```bash
mgdio maps geocode "10 Hanover Square, NY"
mgdio maps reverse "40.714,-74.006"    # one quoted "lat,lng" token
mgdio maps distance "NY 10005" "Hoboken NJ"
mgdio maps duration "NY 10005" "Hoboken NJ" --mode walking
mgdio maps directions "NY 10005" "Hoboken NJ"
```

Quote the coordinate for `reverse` as a single token so the negative longitude
is not parsed as a CLI option.
