"""Unit tests for ``mgdio.auth.ynab._setup_server``."""

from __future__ import annotations

from unittest.mock import MagicMock

import requests

from mgdio.auth.ynab import _setup_server


class TestValidateToken:
    def test_200_response_returns_ok(self, monkeypatch):
        resp = MagicMock()
        resp.status_code = 200
        monkeypatch.setattr(_setup_server.requests, "get", MagicMock(return_value=resp))
        ok, message = _setup_server._validate_token("good-token")
        assert ok is True
        assert "verified" in message.lower()

    def test_401_response_returns_specific_error(self, monkeypatch):
        resp = MagicMock()
        resp.status_code = 401
        monkeypatch.setattr(_setup_server.requests, "get", MagicMock(return_value=resp))
        ok, message = _setup_server._validate_token("bad-token")
        assert ok is False
        assert "401" in message

    def test_other_status_returns_text_in_message(self, monkeypatch):
        resp = MagicMock()
        resp.status_code = 503
        resp.text = "Service Unavailable"
        monkeypatch.setattr(_setup_server.requests, "get", MagicMock(return_value=resp))
        ok, message = _setup_server._validate_token("token")
        assert ok is False
        assert "503" in message
        assert "Service Unavailable" in message

    def test_request_exception_returns_transport_error(self, monkeypatch):
        monkeypatch.setattr(
            _setup_server.requests,
            "get",
            MagicMock(side_effect=requests.RequestException("dns blew up")),
        )
        ok, message = _setup_server._validate_token("token")
        assert ok is False
        assert "Could not reach YNAB" in message


class TestPageContent:
    def test_page_mentions_developer_settings_url(self):
        assert "app.ynab.com/settings/developer" in _setup_server._PAGE

    def test_page_has_paste_textarea_and_save_button(self):
        assert 'id="token"' in _setup_server._PAGE
        assert 'id="save"' in _setup_server._PAGE
        assert "Save token" in _setup_server._PAGE

    def test_page_mentions_keyring_storage(self):
        assert "OS credential vault" in _setup_server._PAGE
        assert "mgdio:ynab" in _setup_server._PAGE
