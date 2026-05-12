"""Unit tests for ``mgdio.auth.google.auth``."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from mgdio.auth.google import auth as google_auth
from mgdio.settings import (
    GOOGLE_CLIENT_SECRET_PATH,
    GOOGLE_KEYRING_SERVICE,
    GOOGLE_KEYRING_USERNAME,
    GOOGLE_SCOPES,
)


def _make_creds(*, valid: bool = True, expired: bool = False) -> MagicMock:
    creds = MagicMock(name="Credentials")
    creds.valid = valid
    creds.expired = expired
    creds.refresh_token = "refresh-token"
    creds.to_json.return_value = json.dumps(
        {"token": "access", "refresh_token": "refresh-token"}
    )
    return creds


class TestGetCredentials:
    def test_returns_valid_in_process_cache_without_keyring_call(
        self, fake_keyring, monkeypatch
    ):
        cached = _make_creds(valid=True)
        monkeypatch.setattr(google_auth, "_credentials", cached)

        from_authorized = MagicMock()
        monkeypatch.setattr(
            "mgdio.auth.google.auth.Credentials.from_authorized_user_info",
            from_authorized,
        )

        result = google_auth.get_credentials()

        assert result is cached
        assert fake_keyring == {}
        from_authorized.assert_not_called()

    def test_loads_fresh_token_from_keyring(self, fake_keyring, monkeypatch):
        fake_keyring[(GOOGLE_KEYRING_SERVICE, GOOGLE_KEYRING_USERNAME)] = json.dumps(
            {"token": "access", "refresh_token": "refresh-token"}
        )
        loaded = _make_creds(valid=True)
        monkeypatch.setattr(
            "mgdio.auth.google.auth.Credentials.from_authorized_user_info",
            MagicMock(return_value=loaded),
        )

        result = google_auth.get_credentials()

        assert result is loaded
        assert google_auth._credentials is loaded

    def test_refreshes_expired_token_and_writes_back_to_keyring(
        self, fake_keyring, monkeypatch
    ):
        fake_keyring[(GOOGLE_KEYRING_SERVICE, GOOGLE_KEYRING_USERNAME)] = "{}"
        loaded = _make_creds(valid=False, expired=True)

        def fake_refresh(_request) -> None:
            loaded.valid = True
            loaded.expired = False
            loaded.to_json.return_value = json.dumps({"token": "refreshed"})

        loaded.refresh.side_effect = fake_refresh
        monkeypatch.setattr(
            "mgdio.auth.google.auth.Credentials.from_authorized_user_info",
            MagicMock(return_value=loaded),
        )

        result = google_auth.get_credentials()

        assert result is loaded
        loaded.refresh.assert_called_once()
        assert json.loads(
            fake_keyring[(GOOGLE_KEYRING_SERVICE, GOOGLE_KEYRING_USERNAME)]
        ) == {"token": "refreshed"}

    def test_runs_setup_flow_when_no_token_and_persists_result(
        self, tmp_appdata, fake_keyring, monkeypatch
    ):
        new_creds = _make_creds(valid=True)
        run_setup = MagicMock(return_value=new_creds)
        monkeypatch.setattr(google_auth, "run_setup_flow", run_setup)

        result = google_auth.get_credentials()

        assert result is new_creds
        run_setup.assert_called_once()
        called_path, called_scopes = run_setup.call_args.args
        assert called_path.name == "client_secret.json"
        assert called_scopes == list(GOOGLE_SCOPES)
        assert len(called_scopes) == 3
        assert "https://www.googleapis.com/auth/gmail.modify" in called_scopes
        assert "https://www.googleapis.com/auth/calendar" in called_scopes
        assert "https://www.googleapis.com/auth/spreadsheets" in called_scopes
        assert (
            fake_keyring[(GOOGLE_KEYRING_SERVICE, GOOGLE_KEYRING_USERNAME)]
            == new_creds.to_json.return_value
        )

    def test_dispatches_to_run_headless_flow_when_headless_true(
        self, tmp_appdata, fake_keyring, monkeypatch
    ):
        new_creds = _make_creds(valid=True)
        run_setup = MagicMock()
        run_headless = MagicMock(return_value=new_creds)
        monkeypatch.setattr(google_auth, "run_setup_flow", run_setup)
        monkeypatch.setattr(google_auth, "run_headless_flow", run_headless)

        result = google_auth.get_credentials(headless=True)

        assert result is new_creds
        run_headless.assert_called_once()
        run_setup.assert_not_called()
        # Same args as the non-headless path: (client_secret_path, scopes).
        called_path, called_scopes = run_headless.call_args.args
        assert called_path.name == "client_secret.json"
        assert called_scopes == list(GOOGLE_SCOPES)

    def test_default_uses_run_setup_flow_not_headless(
        self, tmp_appdata, fake_keyring, monkeypatch
    ):
        new_creds = _make_creds(valid=True)
        run_setup = MagicMock(return_value=new_creds)
        run_headless = MagicMock()
        monkeypatch.setattr(google_auth, "run_setup_flow", run_setup)
        monkeypatch.setattr(google_auth, "run_headless_flow", run_headless)

        google_auth.get_credentials()  # default: headless=False

        run_setup.assert_called_once()
        run_headless.assert_not_called()


class TestClearStoredToken:
    def test_removes_keyring_entry_and_resets_cache(self, fake_keyring, monkeypatch):
        fake_keyring[(GOOGLE_KEYRING_SERVICE, GOOGLE_KEYRING_USERNAME)] = "x"
        monkeypatch.setattr(google_auth, "_credentials", _make_creds())

        google_auth.clear_stored_token()

        assert (GOOGLE_KEYRING_SERVICE, GOOGLE_KEYRING_USERNAME) not in fake_keyring
        assert google_auth._credentials is None

    def test_swallows_missing_entry_without_raising(self, fake_keyring):
        google_auth.clear_stored_token()
        assert google_auth._credentials is None


class TestSettingsConsistency:
    def test_client_secret_path_lives_under_google_subdir(self):
        assert GOOGLE_CLIENT_SECRET_PATH.parent.name == "google"
        assert GOOGLE_CLIENT_SECRET_PATH.name == "client_secret.json"
