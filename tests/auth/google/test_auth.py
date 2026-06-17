"""Unit tests for ``mgdio.auth.google.auth`` (per-profile)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from mgdio.auth.google import _profiles as google_profiles
from mgdio.auth.google import auth as google_auth
from mgdio.settings import (
    GOOGLE_CLIENT_SECRET_PATH,
    GOOGLE_KEYRING_USERNAME,
    GOOGLE_SCOPES,
    google_keyring_service,
)

SLUG = "svc"
SERVICE = google_keyring_service(SLUG)


def _make_creds(*, valid: bool = True, expired: bool = False) -> MagicMock:
    creds = MagicMock(name="Credentials")
    creds.valid = valid
    creds.expired = expired
    creds.refresh_token = "refresh-token"
    creds.to_json.return_value = json.dumps(
        {"token": "access", "refresh_token": "refresh-token"}
    )
    return creds


def _seed_token(fake_keyring, tmp_appdata, slug: str = SLUG) -> None:
    """Put a token in the fake keyring + index so the profile 'exists'."""
    fake_keyring[(google_keyring_service(slug), GOOGLE_KEYRING_USERNAME)] = json.dumps(
        {"token": "access", "refresh_token": "refresh-token"}
    )
    google_profiles.add_to_index(slug)


class TestGetCredentials:
    def test_returns_valid_in_process_cache_without_keyring_call(
        self, tmp_appdata, fake_keyring, monkeypatch
    ):
        _seed_token(fake_keyring, tmp_appdata)
        cached = _make_creds(valid=True)
        monkeypatch.setattr(google_auth, "_credentials", {SLUG: cached})

        from_authorized = MagicMock()
        monkeypatch.setattr(
            "mgdio.auth.google.auth.Credentials.from_authorized_user_info",
            from_authorized,
        )

        result = google_auth.get_credentials(SLUG)

        assert result is cached
        from_authorized.assert_not_called()

    def test_loads_fresh_token_from_keyring(
        self, tmp_appdata, fake_keyring, monkeypatch
    ):
        _seed_token(fake_keyring, tmp_appdata)
        loaded = _make_creds(valid=True)
        monkeypatch.setattr(
            "mgdio.auth.google.auth.Credentials.from_authorized_user_info",
            MagicMock(return_value=loaded),
        )

        result = google_auth.get_credentials(SLUG)

        assert result is loaded
        assert google_auth._credentials[SLUG] is loaded

    def test_refreshes_expired_token_and_writes_back_to_keyring(
        self, tmp_appdata, fake_keyring, monkeypatch
    ):
        _seed_token(fake_keyring, tmp_appdata)
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

        result = google_auth.get_credentials(SLUG)

        assert result is loaded
        loaded.refresh.assert_called_once()
        assert json.loads(fake_keyring[(SERVICE, GOOGLE_KEYRING_USERNAME)]) == {
            "token": "refreshed"
        }

    def test_per_profile_cache_isolation(self, tmp_appdata, fake_keyring, monkeypatch):
        _seed_token(fake_keyring, tmp_appdata, "alpha")
        _seed_token(fake_keyring, tmp_appdata, "beta")
        creds_a = _make_creds(valid=True)
        creds_b = _make_creds(valid=True)

        def fake_load(slug):
            return {"alpha": creds_a, "beta": creds_b}[slug]

        monkeypatch.setattr(google_auth, "_load_token_from_keyring", fake_load)

        assert google_auth.get_credentials("alpha") is creds_a
        assert google_auth.get_credentials("beta") is creds_b
        assert google_auth._credentials == {"alpha": creds_a, "beta": creds_b}


class TestAuthorizeProfile:
    def test_runs_setup_flow_and_persists_with_index(
        self, tmp_appdata, fake_keyring, monkeypatch
    ):
        new_creds = _make_creds(valid=True)
        run_setup = MagicMock(return_value=new_creds)
        monkeypatch.setattr(google_auth, "run_setup_flow", run_setup)

        result = google_auth.authorize_profile(SLUG)

        assert result is new_creds
        run_setup.assert_called_once()
        called_path, called_scopes = run_setup.call_args.args
        assert called_path.name == "client_secret.json"
        assert called_scopes == list(GOOGLE_SCOPES)
        assert len(called_scopes) == 4
        assert "https://www.googleapis.com/auth/drive" in called_scopes
        # Token persisted under the per-profile service, and indexed.
        assert (
            fake_keyring[(SERVICE, GOOGLE_KEYRING_USERNAME)]
            == new_creds.to_json.return_value
        )
        assert SLUG in google_profiles.read_index()

    def test_headless_dispatches_to_headless_flow(
        self, tmp_appdata, fake_keyring, monkeypatch
    ):
        new_creds = _make_creds(valid=True)
        run_setup = MagicMock()
        run_headless = MagicMock(return_value=new_creds)
        monkeypatch.setattr(google_auth, "run_setup_flow", run_setup)
        monkeypatch.setattr(google_auth, "run_headless_flow", run_headless)

        result = google_auth.authorize_profile(SLUG, headless=True)

        assert result is new_creds
        run_headless.assert_called_once()
        run_setup.assert_not_called()

    def test_default_uses_setup_flow_not_headless(
        self, tmp_appdata, fake_keyring, monkeypatch
    ):
        new_creds = _make_creds(valid=True)
        run_setup = MagicMock(return_value=new_creds)
        run_headless = MagicMock()
        monkeypatch.setattr(google_auth, "run_setup_flow", run_setup)
        monkeypatch.setattr(google_auth, "run_headless_flow", run_headless)

        google_auth.authorize_profile(SLUG)

        run_setup.assert_called_once()
        run_headless.assert_not_called()


class TestClearStoredToken:
    def test_removes_keyring_entry_index_and_cache(
        self, tmp_appdata, fake_keyring, monkeypatch
    ):
        _seed_token(fake_keyring, tmp_appdata)
        monkeypatch.setattr(google_auth, "_credentials", {SLUG: _make_creds()})

        google_auth.clear_stored_token(SLUG)

        assert (SERVICE, GOOGLE_KEYRING_USERNAME) not in fake_keyring
        assert SLUG not in google_profiles.read_index()
        assert SLUG not in google_auth._credentials

    def test_swallows_missing_entry_without_raising(self, tmp_appdata, fake_keyring):
        google_auth.clear_stored_token(SLUG)
        assert SLUG not in google_auth._credentials


class TestClearLegacyToken:
    def test_removes_legacy_entry(self, tmp_appdata, fake_keyring):
        from mgdio.settings import LEGACY_GOOGLE_KEYRING_SERVICE

        key = (LEGACY_GOOGLE_KEYRING_SERVICE, GOOGLE_KEYRING_USERNAME)
        fake_keyring[key] = "legacy-token"

        google_auth.clear_legacy_token()

        assert key not in fake_keyring

    def test_noop_when_absent(self, tmp_appdata, fake_keyring):
        google_auth.clear_legacy_token()  # must not raise
        # And it doesn't touch a per-profile entry.
        _seed_token(fake_keyring, tmp_appdata)
        google_auth.clear_legacy_token()
        assert (SERVICE, GOOGLE_KEYRING_USERNAME) in fake_keyring


class TestSettingsConsistency:
    def test_client_secret_path_lives_under_google_subdir(self):
        assert GOOGLE_CLIENT_SECRET_PATH.parent.name == "google"
        assert GOOGLE_CLIENT_SECRET_PATH.name == "client_secret.json"
