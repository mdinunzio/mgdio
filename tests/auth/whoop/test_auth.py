"""Unit tests for ``mgdio.auth.whoop.auth``."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

import pytest

from mgdio.auth.whoop import auth as whoop_auth
from mgdio.exceptions import (
    MgdioAPIError,
    MgdioAuthError,
    MgdioInteractionRequiredError,
    MgdioTokenRejectedError,
)
from mgdio.settings import (
    WHOOP_KEYRING_SERVICE,
    WHOOP_KEYRING_USERNAME_APP,
    WHOOP_KEYRING_USERNAME_TOKEN,
)

_TOKEN_KEY = (WHOOP_KEYRING_SERVICE, WHOOP_KEYRING_USERNAME_TOKEN)
_APP_KEY = (WHOOP_KEYRING_SERVICE, WHOOP_KEYRING_USERNAME_APP)


def _valid_bundle(*, expires_in: float = 3600) -> dict:
    return {
        "access_token": "access-1",
        "refresh_token": "refresh-1",
        "expires_at": time.time() + expires_in,
        "scope": "offline read:recovery",
        "token_type": "bearer",
    }


class TestGetAccessToken:
    def test_returns_in_process_cached_token_without_keyring(
        self, fake_keyring, monkeypatch
    ):
        monkeypatch.setattr(whoop_auth, "_token", _valid_bundle())
        run_setup = MagicMock()
        monkeypatch.setattr(whoop_auth, "run_setup_flow", run_setup)

        assert whoop_auth.get_access_token() == "access-1"
        assert fake_keyring == {}
        run_setup.assert_not_called()

    def test_loads_valid_token_from_keyring(self, fake_keyring, monkeypatch):
        fake_keyring[_TOKEN_KEY] = json.dumps(_valid_bundle())
        run_setup = MagicMock()
        monkeypatch.setattr(whoop_auth, "run_setup_flow", run_setup)

        assert whoop_auth.get_access_token() == "access-1"
        run_setup.assert_not_called()

    def test_expired_token_is_refreshed_and_saved(self, fake_keyring, monkeypatch):
        fake_keyring[_TOKEN_KEY] = json.dumps(_valid_bundle(expires_in=-10))
        refreshed = _valid_bundle()
        refreshed["access_token"] = "access-2"
        refresh = MagicMock(return_value=refreshed)
        monkeypatch.setattr(whoop_auth, "_refresh", refresh)
        run_setup = MagicMock()
        monkeypatch.setattr(whoop_auth, "run_setup_flow", run_setup)

        assert whoop_auth.get_access_token() == "access-2"
        refresh.assert_called_once()
        run_setup.assert_not_called()
        assert json.loads(fake_keyring[_TOKEN_KEY])["access_token"] == "access-2"

    def test_rejected_refresh_token_falls_through_to_setup(
        self, fake_keyring, monkeypatch
    ):
        fake_keyring[_TOKEN_KEY] = json.dumps(_valid_bundle(expires_in=-10))
        monkeypatch.setattr(
            whoop_auth,
            "_refresh",
            MagicMock(side_effect=MgdioTokenRejectedError("HTTP 400: invalid_grant")),
        )
        new_bundle = _valid_bundle()
        new_bundle["access_token"] = "access-fresh"
        run_setup = MagicMock(return_value=new_bundle)
        monkeypatch.setattr(whoop_auth, "run_setup_flow", run_setup)

        assert whoop_auth.get_access_token() == "access-fresh"
        run_setup.assert_called_once()
        assert json.loads(fake_keyring[_TOKEN_KEY])["access_token"] == "access-fresh"

    def test_transient_refresh_failure_propagates_and_keeps_stored_token(
        self, fake_keyring, monkeypatch
    ):
        stale = json.dumps(_valid_bundle(expires_in=-10))
        fake_keyring[_TOKEN_KEY] = stale
        monkeypatch.setattr(
            whoop_auth,
            "_refresh",
            MagicMock(side_effect=MgdioAPIError("transport error: timeout")),
        )
        run_setup = MagicMock()
        monkeypatch.setattr(whoop_auth, "run_setup_flow", run_setup)

        with pytest.raises(MgdioAPIError):
            whoop_auth.get_access_token()

        run_setup.assert_not_called()
        assert fake_keyring[_TOKEN_KEY] == stale

    def test_noninteractive_session_errors_instead_of_setup_flow(
        self, fake_keyring, monkeypatch
    ):
        monkeypatch.setenv("MGDIO_NONINTERACTIVE", "1")
        run_setup = MagicMock()
        monkeypatch.setattr(whoop_auth, "run_setup_flow", run_setup)

        with pytest.raises(MgdioInteractionRequiredError, match="mgdio auth whoop"):
            whoop_auth.get_access_token()
        run_setup.assert_not_called()

    def test_headless_dispatches_to_headless_flow(self, fake_keyring, monkeypatch):
        new_bundle = _valid_bundle()
        run_headless = MagicMock(return_value=new_bundle)
        run_setup = MagicMock()
        monkeypatch.setattr(whoop_auth, "run_headless_flow", run_headless)
        monkeypatch.setattr(whoop_auth, "run_setup_flow", run_setup)

        assert whoop_auth.get_access_token(headless=True) == "access-1"
        run_headless.assert_called_once()
        run_setup.assert_not_called()

    def test_empty_keyring_runs_setup_and_persists(self, fake_keyring, monkeypatch):
        new_bundle = _valid_bundle()
        run_setup = MagicMock(return_value=new_bundle)
        monkeypatch.setattr(whoop_auth, "run_setup_flow", run_setup)

        assert whoop_auth.get_access_token() == "access-1"
        run_setup.assert_called_once()
        assert _TOKEN_KEY in fake_keyring


class TestIsExpired:
    def test_future_expiry_not_expired(self):
        assert whoop_auth._is_expired({"expires_at": time.time() + 100}) is False

    def test_past_expiry_is_expired(self):
        assert whoop_auth._is_expired({"expires_at": time.time() - 1}) is True

    def test_missing_expiry_treated_as_expired(self):
        assert whoop_auth._is_expired({}) is True


class TestRefresh:
    def test_posts_refresh_grant_and_carries_refresh_token(
        self, fake_keyring, monkeypatch
    ):
        fake_keyring[_APP_KEY] = json.dumps(
            {"client_id": "cid", "client_secret": "csec"}
        )
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "access_token": "new-access",
            # no refresh_token in response -> should carry forward the old one
            "expires_in": 3600,
            "scope": "offline",
            "token_type": "bearer",
        }
        post = MagicMock(return_value=resp)
        monkeypatch.setattr(whoop_auth.requests, "post", post)

        bundle = whoop_auth._refresh(
            {"refresh_token": "old-refresh", "access_token": "old"}
        )

        assert bundle["access_token"] == "new-access"
        assert bundle["refresh_token"] == "old-refresh"  # carried forward
        assert bundle["expires_at"] > time.time()
        data = post.call_args.kwargs["data"]
        assert data["grant_type"] == "refresh_token"
        assert data["refresh_token"] == "old-refresh"
        assert data["client_id"] == "cid"
        assert data["client_secret"] == "csec"

    def test_missing_app_creds_raises(self, fake_keyring):
        with pytest.raises(MgdioAuthError, match="app credentials missing"):
            whoop_auth._refresh({"refresh_token": "x"})

    @pytest.mark.parametrize("status", [400, 401])
    def test_definitive_rejection_raises_token_rejected(
        self, fake_keyring, monkeypatch, status
    ):
        fake_keyring[_APP_KEY] = json.dumps({"client_id": "c", "client_secret": "s"})
        resp = MagicMock()
        resp.status_code = status
        resp.text = "invalid_grant"
        monkeypatch.setattr(whoop_auth.requests, "post", MagicMock(return_value=resp))
        with pytest.raises(MgdioTokenRejectedError, match=f"HTTP {status}"):
            whoop_auth._refresh({"refresh_token": "x"})

    def test_server_error_raises_transient_api_error(self, fake_keyring, monkeypatch):
        fake_keyring[_APP_KEY] = json.dumps({"client_id": "c", "client_secret": "s"})
        resp = MagicMock()
        resp.status_code = 503
        resp.text = "unavailable"
        monkeypatch.setattr(whoop_auth.requests, "post", MagicMock(return_value=resp))
        with pytest.raises(MgdioAPIError, match="HTTP 503"):
            whoop_auth._refresh({"refresh_token": "x"})

    def test_transport_error_raises_transient_api_error(
        self, fake_keyring, monkeypatch
    ):
        import requests as requests_lib

        fake_keyring[_APP_KEY] = json.dumps({"client_id": "c", "client_secret": "s"})
        monkeypatch.setattr(
            whoop_auth.requests,
            "post",
            MagicMock(side_effect=requests_lib.ConnectionError("boom")),
        )
        with pytest.raises(MgdioAPIError, match="transport error"):
            whoop_auth._refresh({"refresh_token": "x"})


class TestClearStoredToken:
    def test_removes_token_entry_only_leaves_app_creds(self, fake_keyring, monkeypatch):
        fake_keyring[_TOKEN_KEY] = json.dumps(_valid_bundle())
        fake_keyring[_APP_KEY] = json.dumps({"client_id": "c", "client_secret": "s"})
        monkeypatch.setattr(whoop_auth, "_token", _valid_bundle())

        whoop_auth.clear_stored_token()

        assert _TOKEN_KEY not in fake_keyring
        assert _APP_KEY in fake_keyring  # app creds preserved
        assert whoop_auth._token is None

    def test_swallows_missing_entry(self, fake_keyring):
        whoop_auth.clear_stored_token()
        assert whoop_auth._token is None
