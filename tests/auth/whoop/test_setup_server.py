"""Unit tests for ``mgdio.auth.whoop._setup_server``."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from mgdio.auth.whoop import _setup_server
from mgdio.exceptions import MgdioAuthError
from mgdio.settings import WHOOP_REDIRECT_URI


class TestDerivedBinding:
    def test_default_bind_and_callback_match_redirect_uri(self):
        # Default WHOOP_REDIRECT_URI is http://localhost:8765/callback.
        assert _setup_server._BIND_HOST == "localhost"
        assert _setup_server._BIND_PORT == 8765
        assert _setup_server._CALLBACK_PATH == "/callback"

    def test_custom_uri_parses_to_host_port_path(self):
        from urllib.parse import urlparse

        parsed = urlparse("http://127.0.0.1:9000/oauth/cb")
        assert (parsed.hostname or "localhost") == "127.0.0.1"
        assert (parsed.port or 80) == 9000
        assert (parsed.path or "/callback") == "/oauth/cb"


class TestExchangeCode:
    def test_posts_authorization_code_grant_with_redirect_uri(
        self, fake_keyring, monkeypatch
    ):
        import json

        from mgdio.settings import (
            WHOOP_KEYRING_SERVICE,
            WHOOP_KEYRING_USERNAME_APP,
        )

        fake_keyring[(WHOOP_KEYRING_SERVICE, WHOOP_KEYRING_USERNAME_APP)] = json.dumps(
            {"client_id": "cid", "client_secret": "csec"}
        )
        # patch the keyring the setup server imports
        monkeypatch.setattr(_setup_server, "keyring", _FakeKeyringFrom(fake_keyring))

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "access_token": "acc",
            "refresh_token": "ref",
            "expires_in": 3600,
            "scope": "offline",
            "token_type": "bearer",
        }
        post = MagicMock(return_value=resp)
        monkeypatch.setattr(_setup_server.requests, "post", post)

        bundle = _setup_server._exchange_code("the-code")

        assert bundle["access_token"] == "acc"
        assert bundle["refresh_token"] == "ref"
        assert bundle["expires_at"] > time.time()
        data = post.call_args.kwargs["data"]
        assert data["grant_type"] == "authorization_code"
        assert data["code"] == "the-code"
        assert data["redirect_uri"] == WHOOP_REDIRECT_URI
        assert data["client_id"] == "cid"

    def test_non_200_raises(self, fake_keyring, monkeypatch):
        monkeypatch.setattr(_setup_server, "keyring", _FakeKeyringFrom(fake_keyring))
        resp = MagicMock()
        resp.status_code = 400
        resp.text = "bad code"
        monkeypatch.setattr(
            _setup_server.requests, "post", MagicMock(return_value=resp)
        )
        with pytest.raises(MgdioAuthError, match="HTTP 400"):
            _setup_server._exchange_code("x")


class TestValidateAccessToken:
    def test_200_returns_ok(self, monkeypatch):
        resp = MagicMock()
        resp.status_code = 200
        monkeypatch.setattr(_setup_server.requests, "get", MagicMock(return_value=resp))
        ok, _msg = _setup_server._validate_access_token("acc")
        assert ok is True

    def test_401_returns_not_ok(self, monkeypatch):
        resp = MagicMock()
        resp.status_code = 401
        monkeypatch.setattr(_setup_server.requests, "get", MagicMock(return_value=resp))
        ok, msg = _setup_server._validate_access_token("acc")
        assert ok is False
        assert "401" in msg


class TestPage:
    def test_page_shows_redirect_uri_and_scopes(self):
        page = _setup_server._render_page()
        assert WHOOP_REDIRECT_URI in page
        assert "read:recovery" in page
        assert "offline" in page

    def test_page_has_both_credential_inputs(self):
        page = _setup_server._render_page()
        assert 'id="client_id"' in page
        assert 'id="client_secret"' in page
        assert "Authorize with Whoop" in page

    def test_page_mentions_env_override(self):
        page = _setup_server._render_page()
        assert "MGDIO_WHOOP_REDIRECT_URI" in page


class _FakeKeyringFrom:
    """Adapt the conftest fake_keyring dict store to the keyring module API."""

    def __init__(self, store: dict):
        self._store = store

    def get_password(self, service, username):
        return self._store.get((service, username))

    def set_password(self, service, username, password):
        self._store[(service, username)] = password
