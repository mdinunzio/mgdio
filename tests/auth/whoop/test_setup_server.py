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


class TestParseRedirectUrl:
    def test_extracts_code_when_state_matches(self):
        url = f"{WHOOP_REDIRECT_URI}?code=abc123&state=st-1"
        assert _setup_server._parse_redirect_url(url, "st-1") == "abc123"

    def test_state_mismatch_raises(self):
        url = f"{WHOOP_REDIRECT_URI}?code=abc&state=other"
        with pytest.raises(MgdioAuthError, match="State mismatch"):
            _setup_server._parse_redirect_url(url, "st-1")

    def test_provider_error_param_raises(self):
        url = f"{WHOOP_REDIRECT_URI}?error=access_denied&state=st-1"
        with pytest.raises(MgdioAuthError, match="access_denied"):
            _setup_server._parse_redirect_url(url, "st-1")

    def test_missing_code_raises(self):
        url = f"{WHOOP_REDIRECT_URI}?state=st-1"
        with pytest.raises(MgdioAuthError, match="No authorization code"):
            _setup_server._parse_redirect_url(url, "st-1")


class TestRunHeadlessFlow:
    def _arrange(self, fake_keyring, monkeypatch, *, inputs, with_app_creds=True):
        import json

        from mgdio.settings import (
            WHOOP_KEYRING_SERVICE,
            WHOOP_KEYRING_USERNAME_APP,
        )

        if with_app_creds:
            fake_keyring[(WHOOP_KEYRING_SERVICE, WHOOP_KEYRING_USERNAME_APP)] = (
                json.dumps({"client_id": "cid", "client_secret": "csec"})
            )
        monkeypatch.setattr(_setup_server, "keyring", _FakeKeyringFrom(fake_keyring))
        monkeypatch.setattr(
            _setup_server, "secrets", MagicMock(token_urlsafe=lambda n=24: "st-1")
        )
        monkeypatch.setattr("builtins.input", MagicMock(side_effect=inputs))

    def test_happy_path_exchanges_pasted_url(self, fake_keyring, monkeypatch):
        pasted = f"{WHOOP_REDIRECT_URI}?code=the-code&state=st-1"
        self._arrange(fake_keyring, monkeypatch, inputs=[pasted])
        bundle = {"access_token": "acc", "refresh_token": "ref"}
        exchange = MagicMock(return_value=bundle)
        monkeypatch.setattr(_setup_server, "_exchange_code", exchange)
        monkeypatch.setattr(
            _setup_server, "_validate_access_token", lambda t: (True, "Authorized.")
        )

        assert _setup_server.run_headless_flow() is bundle
        exchange.assert_called_once_with("the-code")

    def test_prompts_for_app_credentials_when_missing(self, fake_keyring, monkeypatch):
        import json

        from mgdio.settings import (
            WHOOP_KEYRING_SERVICE,
            WHOOP_KEYRING_USERNAME_APP,
        )

        pasted = f"{WHOOP_REDIRECT_URI}?code=c&state=st-1"
        self._arrange(
            fake_keyring,
            monkeypatch,
            inputs=["new-cid", "new-csec", pasted],
            with_app_creds=False,
        )
        monkeypatch.setattr(
            _setup_server,
            "_exchange_code",
            MagicMock(return_value={"access_token": "a"}),
        )
        monkeypatch.setattr(
            _setup_server, "_validate_access_token", lambda t: (True, "Authorized.")
        )

        _setup_server.run_headless_flow()

        saved = json.loads(
            fake_keyring[(WHOOP_KEYRING_SERVICE, WHOOP_KEYRING_USERNAME_APP)]
        )
        assert saved == {"client_id": "new-cid", "client_secret": "new-csec"}

    def test_empty_paste_raises(self, fake_keyring, monkeypatch):
        self._arrange(fake_keyring, monkeypatch, inputs=["   "])
        with pytest.raises(MgdioAuthError, match="No URL pasted"):
            _setup_server.run_headless_flow()

    def test_validation_failure_raises(self, fake_keyring, monkeypatch):
        pasted = f"{WHOOP_REDIRECT_URI}?code=c&state=st-1"
        self._arrange(fake_keyring, monkeypatch, inputs=[pasted])
        monkeypatch.setattr(
            _setup_server,
            "_exchange_code",
            MagicMock(return_value={"access_token": "a"}),
        )
        monkeypatch.setattr(
            _setup_server, "_validate_access_token", lambda t: (False, "401")
        )
        with pytest.raises(MgdioAuthError, match="validation failed"):
            _setup_server.run_headless_flow()
