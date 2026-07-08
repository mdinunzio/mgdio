"""Unit tests for ``mgdio.maps.geocoding``."""

from __future__ import annotations

from mgdio.maps import geocoding
from mgdio.maps.geocoding import GeocodeResult, geocode, reverse_geocode

_SAMPLE_RESULT = {
    "formatted_address": "New York, NY, USA",
    "geometry": {
        "location": {"lat": 40.7127753, "lng": -74.0059728},
        "location_type": "APPROXIMATE",
    },
    "place_id": "ChIJOwg_06VPwokRYv534QaPC8g",
    "types": ["locality", "political"],
}


class TestGeocode:
    def test_maps_results(self, mock_maps_request):
        mock_maps_request.return_value = {"status": "OK", "results": [_SAMPLE_RESULT]}

        results = geocode("New York")

        assert len(results) == 1
        r = results[0]
        assert isinstance(r, GeocodeResult)
        assert r.formatted_address == "New York, NY, USA"
        assert r.latitude == 40.7127753
        assert r.longitude == -74.0059728
        assert r.location_type == "APPROXIMATE"
        assert r.place_id.startswith("ChIJ")
        assert r.types == ("locality", "political")

    def test_sends_address_to_geocode_endpoint(self, mock_maps_request):
        mock_maps_request.return_value = {"status": "OK", "results": []}
        geocode("10 Hanover Square, NY")
        endpoint, params = mock_maps_request.call_args.args
        assert endpoint == "geocode/json"
        assert params == {"address": "10 Hanover Square, NY"}

    def test_zero_results_returns_empty(self, mock_maps_request):
        mock_maps_request.return_value = {"status": "ZERO_RESULTS", "results": []}
        assert geocode("nowhere at all") == []

    def test_latlng_property(self):
        r = geocoding._to_result(_SAMPLE_RESULT)
        assert r.latlng == "40.7127753, -74.0059728"


class TestReverseGeocode:
    def test_builds_latlng_param(self, mock_maps_request):
        mock_maps_request.return_value = {"status": "OK", "results": [_SAMPLE_RESULT]}

        results = reverse_geocode(40.714, -74.006)

        assert results[0].formatted_address == "New York, NY, USA"
        endpoint, params = mock_maps_request.call_args.args
        assert endpoint == "geocode/json"
        assert params == {"latlng": "40.714,-74.006"}
