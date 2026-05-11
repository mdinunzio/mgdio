"""Unit tests for ``mgdio.ynab.client``."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mgdio.exceptions import MgdioAPIError
from mgdio.ynab import client as ynab_client


def _mock_response(status_code: int, body=None, *, raises_on_json=False):
    resp = MagicMock()
    resp.status_code = status_code
    if raises_on_json:
        resp.json.side_effect = ValueError("not json")
    elif body is not None:
        resp.json.return_value = body
    resp.text = "" if body is None else "<text body>"
    return resp


class TestGetSession:
    def test_injects_bearer_header_from_token(self, monkeypatch):
        monkeypatch.setattr(ynab_client, "get_token", lambda: "tok-123")
        # First call builds it.
        session = ynab_client.get_session()
        assert session.headers["Authorization"] == "Bearer tok-123"
        # Second call returns the same instance.
        assert ynab_client.get_session() is session

    def test_reset_session_cache_closes_and_clears(self, monkeypatch):
        monkeypatch.setattr(ynab_client, "get_token", lambda: "tok")
        first = ynab_client.get_session()
        first.close = MagicMock()
        ynab_client.reset_session_cache()
        first.close.assert_called_once()
        assert ynab_client._session is None


class TestRequest:
    def test_returns_data_envelope_on_2xx(self, monkeypatch):
        resp = _mock_response(200, {"data": {"budgets": [{"id": "b1"}]}})
        monkeypatch.setattr(ynab_client, "raw_request", MagicMock(return_value=resp))

        result = ynab_client.request("GET", "/budgets")
        assert result == {"budgets": [{"id": "b1"}]}

    def test_2xx_without_data_envelope_raises(self, monkeypatch):
        resp = _mock_response(200, {"weird": "response"})
        monkeypatch.setattr(ynab_client, "raw_request", MagicMock(return_value=resp))
        with pytest.raises(MgdioAPIError, match="no 'data' envelope"):
            ynab_client.request("GET", "/x")

    def test_401_raises_with_ynab_error_detail(self, monkeypatch):
        resp = _mock_response(
            401, {"error": {"id": "401", "name": "unauthorized", "detail": "bad token"}}
        )
        monkeypatch.setattr(ynab_client, "raw_request", MagicMock(return_value=resp))
        with pytest.raises(MgdioAPIError, match="bad token"):
            ynab_client.request("GET", "/x")

    def test_500_with_non_json_body_falls_back_to_text(self, monkeypatch):
        resp = _mock_response(500, raises_on_json=True)
        resp.text = "Internal Server Error"
        monkeypatch.setattr(ynab_client, "raw_request", MagicMock(return_value=resp))
        with pytest.raises(MgdioAPIError, match="500"):
            ynab_client.request("GET", "/x")


class TestRawRequest:
    def test_calls_session_with_full_url_and_kwargs(self, monkeypatch):
        session = MagicMock()
        monkeypatch.setattr(ynab_client, "get_session", lambda: session)

        ynab_client.raw_request(
            "PATCH", "/budgets/abc/transactions/t1", params={"x": "y"}, json={"a": 1}
        )

        session.request.assert_called_once()
        kwargs = session.request.call_args.kwargs
        assert kwargs["method"] == "PATCH"
        assert kwargs["url"].endswith("/v1/budgets/abc/transactions/t1")
        assert kwargs["params"] == {"x": "y"}
        assert kwargs["json"] == {"a": 1}

    def test_transport_failure_wraps_to_mgdio_api_error(self, monkeypatch):
        import requests

        session = MagicMock()
        session.request.side_effect = requests.RequestException("connect refused")
        monkeypatch.setattr(ynab_client, "get_session", lambda: session)

        with pytest.raises(MgdioAPIError, match="transport failed"):
            ynab_client.raw_request("GET", "/x")
