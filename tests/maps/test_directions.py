"""Unit tests for ``mgdio.maps.directions``."""

from __future__ import annotations

import pytest

from mgdio.exceptions import MgdioAPIError
from mgdio.maps.directions import Route, fetch_route, fetch_routes

_SAMPLE_ROUTE = {
    "summary": "I-95 S",
    "legs": [
        {
            "distance": {"text": "5.2 mi", "value": 8368},
            "duration": {"text": "12 mins", "value": 720},
            "start_address": "New York, NY 10005, USA",
            "end_address": "Hoboken, NJ, USA",
            "steps": [
                {
                    "html_instructions": "Head <b>north</b> on <b>Broadway</b>",
                    "distance": {"text": "0.1 mi", "value": 161},
                    "duration": {"text": "1 min", "value": 60},
                    "travel_mode": "DRIVING",
                },
                {
                    "html_instructions": "Turn <b>left</b> onto W St",
                    "distance": {"text": "5.1 mi", "value": 8207},
                    "duration": {"text": "11 mins", "value": 660},
                    "travel_mode": "DRIVING",
                },
            ],
        }
    ],
}


def _ok(routes):
    return {"status": "OK", "routes": routes}


class TestFetchRoutes:
    def test_maps_route(self, mock_maps_request):
        mock_maps_request.return_value = _ok([_SAMPLE_ROUTE])

        routes = fetch_routes("NY 10005", "Hoboken NJ")

        assert len(routes) == 1
        route = routes[0]
        assert isinstance(route, Route)
        assert route.distance_meters == 8368
        assert route.distance_text == "5.2 mi"
        assert route.duration_seconds == 720
        assert route.duration_text == "12 mins"
        assert route.start_address.startswith("New York")
        assert route.end_address.startswith("Hoboken")
        assert route.summary == "I-95 S"

    def test_steps_have_html_stripped(self, mock_maps_request):
        mock_maps_request.return_value = _ok([_SAMPLE_ROUTE])
        route = fetch_routes("a", "b")[0]
        assert route.instructions == [
            "Head north on Broadway",
            "Turn left onto W St",
        ]
        assert route.steps[0].distance_meters == 161
        assert route.steps[0].travel_mode == "DRIVING"

    def test_convenience_units(self, mock_maps_request):
        mock_maps_request.return_value = _ok([_SAMPLE_ROUTE])
        route = fetch_routes("a", "b")[0]
        assert round(route.distance_miles, 2) == 5.2
        assert round(route.distance_km, 2) == 8.37
        assert route.duration_minutes == 12.0

    def test_sends_mode_and_units_params(self, mock_maps_request):
        mock_maps_request.return_value = _ok([_SAMPLE_ROUTE])
        fetch_routes("a", "b", mode="walking", units="metric")
        endpoint, params = mock_maps_request.call_args.args
        assert endpoint == "directions/json"
        assert params["origin"] == "a"
        assert params["destination"] == "b"
        assert params["mode"] == "walking"
        assert params["units"] == "metric"
        assert "alternatives" not in params

    def test_alternatives_flag(self, mock_maps_request):
        mock_maps_request.return_value = _ok([_SAMPLE_ROUTE])
        fetch_routes("a", "b", alternatives=True)
        _, params = mock_maps_request.call_args.args
        assert params["alternatives"] == "true"

    def test_zero_results_returns_empty(self, mock_maps_request):
        mock_maps_request.return_value = {"status": "ZERO_RESULTS", "routes": []}
        assert fetch_routes("a", "b") == []

    def test_invalid_mode_raises_before_call(self, mock_maps_request):
        with pytest.raises(ValueError, match="mode must be"):
            fetch_routes("a", "b", mode="flying")
        mock_maps_request.assert_not_called()

    def test_invalid_units_raises_before_call(self, mock_maps_request):
        with pytest.raises(ValueError, match="units must be"):
            fetch_routes("a", "b", units="furlongs")
        mock_maps_request.assert_not_called()


class TestFetchRoute:
    def test_returns_first(self, mock_maps_request):
        mock_maps_request.return_value = _ok([_SAMPLE_ROUTE, {"legs": []}])
        route = fetch_route("a", "b")
        assert route.distance_meters == 8368

    def test_raises_when_no_route(self, mock_maps_request):
        mock_maps_request.return_value = {"status": "ZERO_RESULTS", "routes": []}
        with pytest.raises(MgdioAPIError, match="No route found"):
            fetch_route("a", "b")
