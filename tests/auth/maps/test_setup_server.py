"""Unit tests for ``mgdio.auth.maps._setup_server``."""

from __future__ import annotations

from unittest.mock import MagicMock

import requests

from mgdio.auth.maps import _setup_server


def _fake_response(*, json_body=None, status_code=200, raise_json=False):
    resp = MagicMock(name="Response")
    resp.status_code = status_code
    if raise_json:
        resp.json.side_effect = ValueError("no json")
    else:
        resp.json.return_value = json_body
    return resp


class TestValidateKey:
    def test_ok_status_passes(self, monkeypatch):
        monkeypatch.setattr(
            _setup_server.requests,
            "get",
            MagicMock(return_value=_fake_response(json_body={"status": "OK"})),
        )
        ok, msg = _setup_server._validate_key("k")
        assert ok is True
        assert "verified" in msg.lower()

    def test_zero_results_passes(self, monkeypatch):
        monkeypatch.setattr(
            _setup_server.requests,
            "get",
            MagicMock(
                return_value=_fake_response(json_body={"status": "ZERO_RESULTS"})
            ),
        )
        ok, _ = _setup_server._validate_key("k")
        assert ok is True

    def test_request_denied_fails_with_detail(self, monkeypatch):
        monkeypatch.setattr(
            _setup_server.requests,
            "get",
            MagicMock(
                return_value=_fake_response(
                    json_body={
                        "status": "REQUEST_DENIED",
                        "error_message": "API key not valid",
                    }
                )
            ),
        )
        ok, msg = _setup_server._validate_key("k")
        assert ok is False
        assert "API key not valid" in msg

    def test_over_query_limit_fails(self, monkeypatch):
        monkeypatch.setattr(
            _setup_server.requests,
            "get",
            MagicMock(
                return_value=_fake_response(json_body={"status": "OVER_QUERY_LIMIT"})
            ),
        )
        ok, msg = _setup_server._validate_key("k")
        assert ok is False
        assert "quota" in msg.lower() or "billing" in msg.lower()

    def test_transport_error_fails(self, monkeypatch):
        def boom(*_a, **_k):
            raise requests.RequestException("down")

        monkeypatch.setattr(_setup_server.requests, "get", boom)
        ok, msg = _setup_server._validate_key("k")
        assert ok is False
        assert "reach" in msg.lower()

    def test_non_json_fails(self, monkeypatch):
        monkeypatch.setattr(
            _setup_server.requests,
            "get",
            MagicMock(return_value=_fake_response(raise_json=True)),
        )
        ok, _ = _setup_server._validate_key("k")
        assert ok is False


class TestPage:
    def test_page_mentions_key_and_both_apis(self):
        page = _setup_server._PAGE
        assert "API key" in page
        assert "Geocoding API" in page
        assert "Directions API" in page
