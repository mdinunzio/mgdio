"""Unit tests for ``mgdio.maps.client``."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from mgdio.exceptions import MgdioAPIError
from mgdio.maps import client as maps_client


def _fake_response(*, json_body=None, status_code=200, raise_json=False):
    resp = MagicMock(name="Response")
    resp.status_code = status_code
    resp.text = "body-text"
    if raise_json:
        resp.json.side_effect = ValueError("no json")
    else:
        resp.json.return_value = json_body
    return resp


def _patch_session(monkeypatch, response=None, side_effect=None):
    session = MagicMock(name="Session")
    if side_effect is not None:
        session.get.side_effect = side_effect
    else:
        session.get.return_value = response
    monkeypatch.setattr(maps_client, "get_session", lambda: session)
    monkeypatch.setattr(maps_client, "get_api_key", lambda: "secret-key-123")
    return session


class TestRequest:
    def test_injects_key_and_returns_body_on_ok(self, monkeypatch):
        body = {"status": "OK", "results": [1, 2]}
        session = _patch_session(monkeypatch, response=_fake_response(json_body=body))

        out = maps_client.request("geocode/json", {"address": "NY"})

        assert out is body
        _, kwargs = session.get.call_args
        assert kwargs["params"]["key"] == "secret-key-123"
        assert kwargs["params"]["address"] == "NY"

    def test_zero_results_returns_body(self, monkeypatch):
        body = {"status": "ZERO_RESULTS", "results": []}
        _patch_session(monkeypatch, response=_fake_response(json_body=body))
        assert maps_client.request("geocode/json", {}) is body

    def test_request_denied_raises_with_detail(self, monkeypatch):
        body = {"status": "REQUEST_DENIED", "error_message": "key bad"}
        _patch_session(monkeypatch, response=_fake_response(json_body=body))
        with pytest.raises(MgdioAPIError, match="key bad"):
            maps_client.request("geocode/json", {})

    def test_transport_error_wraps(self, monkeypatch):
        _patch_session(monkeypatch, side_effect=requests.RequestException("down"))
        with pytest.raises(MgdioAPIError, match="transport failed"):
            maps_client.request("geocode/json", {})

    def test_non_2xx_raises(self, monkeypatch):
        _patch_session(
            monkeypatch, response=_fake_response(json_body={}, status_code=500)
        )
        with pytest.raises(MgdioAPIError, match="HTTP 500"):
            maps_client.request("geocode/json", {})

    def test_key_never_leaks_into_error(self, monkeypatch):
        body = {"status": "REQUEST_DENIED", "error_message": "denied"}
        _patch_session(monkeypatch, response=_fake_response(json_body=body))
        with pytest.raises(MgdioAPIError) as exc:
            maps_client.request("geocode/json", {})
        assert "secret-key-123" not in str(exc.value)
