"""Unit tests for ``mgdio.whoop.client``."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mgdio.exceptions import MgdioAPIError
from mgdio.whoop import client as whoop_client


def _ok_response(body: dict):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = body
    return resp


class TestRequest:
    def test_sets_bearer_header_and_returns_json(self, monkeypatch):
        monkeypatch.setattr(whoop_client, "get_access_token", lambda: "tok-1")
        req = MagicMock(return_value=_ok_response({"hello": "world"}))
        monkeypatch.setattr(whoop_client.requests, "request", req)

        out = whoop_client.request("GET", "/v2/recovery", params={"limit": 5})

        assert out == {"hello": "world"}
        kwargs = req.call_args.kwargs
        assert kwargs["headers"]["Authorization"] == "Bearer tok-1"
        assert kwargs["params"] == {"limit": 5}
        assert req.call_args.args[1].endswith("/developer/v2/recovery")

    def test_transport_error_wrapped(self, monkeypatch):
        import requests as real_requests

        monkeypatch.setattr(whoop_client, "get_access_token", lambda: "t")
        monkeypatch.setattr(
            whoop_client.requests,
            "request",
            MagicMock(side_effect=real_requests.RequestException("boom")),
        )
        with pytest.raises(MgdioAPIError, match="transport failed"):
            whoop_client.request("GET", "/v2/recovery")

    def test_non_2xx_wrapped(self, monkeypatch):
        monkeypatch.setattr(whoop_client, "get_access_token", lambda: "t")
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "server error"
        monkeypatch.setattr(
            whoop_client.requests, "request", MagicMock(return_value=resp)
        )
        with pytest.raises(MgdioAPIError, match="HTTP 500"):
            whoop_client.request("GET", "/v2/recovery")


class TestPaginate:
    def test_follows_next_token_across_pages(self, monkeypatch):
        pages = [
            {"records": [{"id": 1}, {"id": 2}], "next_token": "t1"},
            {"records": [{"id": 3}, {"id": 4}], "next_token": "t2"},
            {"records": [{"id": 5}], "next_token": None},
        ]
        calls = []

        def fake_request(method, path, *, params=None):
            calls.append(params)
            return pages[len(calls) - 1]

        monkeypatch.setattr(whoop_client, "request", fake_request)

        out = whoop_client._paginate("/v2/recovery", max_records=100)

        assert [r["id"] for r in out] == [1, 2, 3, 4, 5]
        # First call has no nextToken; subsequent ones carry the cursor.
        assert "nextToken" not in calls[0]
        assert calls[1]["nextToken"] == "t1"
        assert calls[2]["nextToken"] == "t2"

    def test_stops_at_max_records(self, monkeypatch):
        pages = [
            {"records": [{"id": i} for i in range(25)], "next_token": "t1"},
            {"records": [{"id": i} for i in range(25, 50)], "next_token": "t2"},
        ]
        calls = []

        def fake_request(method, path, *, params=None):
            calls.append(params)
            return pages[len(calls) - 1]

        monkeypatch.setattr(whoop_client, "request", fake_request)

        out = whoop_client._paginate("/v2/recovery", max_records=30)

        assert len(out) == 30
        # Second page requested only the remaining 5 (limit capped to need).
        assert calls[1]["limit"] == 5

    def test_caps_limit_at_25(self, monkeypatch):
        captured = []

        def fake_request(method, path, *, params=None):
            captured.append(params["limit"])
            return {"records": [], "next_token": None}

        monkeypatch.setattr(whoop_client, "request", fake_request)
        whoop_client._paginate("/v2/recovery", max_records=100)
        assert captured[0] == 25  # never asks for more than Whoop allows

    def test_stops_when_no_next_token(self, monkeypatch):
        calls = []

        def fake_request(method, path, *, params=None):
            calls.append(1)
            return {"records": [{"id": 1}]}  # no next_token key

        monkeypatch.setattr(whoop_client, "request", fake_request)
        out = whoop_client._paginate("/v2/recovery", max_records=100)
        assert len(out) == 1
        assert len(calls) == 1

    def test_passes_base_params_through(self, monkeypatch):
        captured = []

        def fake_request(method, path, *, params=None):
            captured.append(params)
            return {"records": [], "next_token": None}

        monkeypatch.setattr(whoop_client, "request", fake_request)
        whoop_client._paginate(
            "/v2/recovery", params={"start": "2026-05-01T00:00:00Z"}, max_records=10
        )
        assert captured[0]["start"] == "2026-05-01T00:00:00Z"


class TestResetSessionCache:
    def test_is_noop(self):
        # No state to clear; just confirm it doesn't raise.
        whoop_client.reset_session_cache()
