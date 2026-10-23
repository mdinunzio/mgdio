"""Unit tests for ``mgdio.auth.google.auth`` (per-profile)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from mgdio.auth.google import auth as google_auth
from mgdio.settings import GOOGLE_CLIENT_SECRET_PATH, GOOGLE_SCOPES, google_vault_key

SLUG = "svc"
KEY = google_vault_key(SLUG)


def _make_creds(*, valid: bool = True, expired: bool = False) -> MagicMock:
    creds = MagicMock(name="Credentials")
    creds.valid = valid
    creds.expired = expired
    creds.refresh_token = "refresh-token"
    creds.to_json.return_value = json.dumps(
        {"token": "access", "refresh_token": "refresh-token"}
    )
    return creds


def _seed_token(fake_vault, slug: str = SLUG) -> None:
    """Put a token in the fake vault so the profile 'exists'."""
    fake_vault.set(
        google_vault_key(slug),
        json.dumps({"token": "access", "refresh_token": "refresh-token"}),
    )


class TestGetCredentials:
    def test_returns_valid_in_process_cache_without_vault_parse(
        self, tmp_appdata, fake_vault, monkeypatch
    ):
        _seed_token(fake_vault)
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

    def test_loads_fresh_token_from_vault(self, tmp_appdata, fake_vault, monkeypatch):
        _seed_token(fake_vault)
        loaded = _make_creds(valid=True)
        monkeypatch.setattr(
            "mgdio.auth.google.auth.Credentials.from_authorized_user_info",
            MagicMock(return_value=loaded),
        )

        result = google_auth.get_credentials(SLUG)

        assert result is loaded
        assert google_auth._credentials[SLUG] is loaded

    def test_refreshes_expired_token_and_writes_back_to_vault(
        self, tmp_appdata, fake_vault, monkeypatch
    ):
        _seed_token(fake_vault)
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
        assert json.loads(fake_vault.get(KEY)) == {"token": "refreshed"}

    def test_refresh_goes_through_locked_update(
        self, tmp_appdata, fake_vault, monkeypatch
    ):
        """Write-back must use mgdvault.update (locked read-modify-write)."""
        _seed_token(fake_vault)
        loaded = _make_creds(valid=False, expired=True)

        def fake_refresh(_request) -> None:
            loaded.valid, loaded.expired = True, False

        loaded.refresh.side_effect = fake_refresh
        monkeypatch.setattr(
            "mgdio.auth.google.auth.Credentials.from_authorized_user_info",
            MagicMock(return_value=loaded),
        )
        update = MagicMock(wraps=google_auth.mgdvault.update)
        monkeypatch.setattr(google_auth.mgdvault, "update", update)
        plain_set = MagicMock(wraps=google_auth.mgdvault.set)
        monkeypatch.setattr(google_auth.mgdvault, "set", plain_set)

        google_auth.get_credentials(SLUG)

        update.assert_called_once()
        assert update.call_args.args[0] == KEY
        plain_set.assert_not_called()

    def test_adopts_token_refreshed_by_another_process(
        self, tmp_appdata, fake_vault, monkeypatch
    ):
        """If the vault already holds a fresh token inside the lock, no refresh."""
        _seed_token(fake_vault)
        stale = _make_creds(valid=False, expired=True)
        fresh = _make_creds(valid=True, expired=False)
        # First parse (outside the lock) sees the stale token; the re-read
        # inside update() sees a token another process already refreshed.
        monkeypatch.setattr(
            "mgdio.auth.google.auth.Credentials.from_authorized_user_info",
            MagicMock(side_effect=[stale, fresh]),
        )

        result = google_auth.get_credentials(SLUG)

        assert result is fresh
        stale.refresh.assert_not_called()
        fresh.refresh.assert_not_called()

    def test_per_profile_cache_isolation(self, tmp_appdata, fake_vault, monkeypatch):
        _seed_token(fake_vault, "alpha")
        _seed_token(fake_vault, "beta")
        creds_a = _make_creds(valid=True)
        creds_b = _make_creds(valid=True)

        def fake_load(slug):
            return {"alpha": creds_a, "beta": creds_b}[slug]

        monkeypatch.setattr(google_auth, "_load_token", fake_load)

        assert google_auth.get_credentials("alpha") is creds_a
        assert google_auth.get_credentials("beta") is creds_b
        assert google_auth._credentials == {"alpha": creds_a, "beta": creds_b}


class TestAuthorizeProfile:
    def test_runs_setup_flow_and_persists(self, tmp_appdata, fake_vault, monkeypatch):
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
        # Token persisted under the per-profile key; the key IS the index.
        assert fake_vault.get(KEY) == new_creds.to_json.return_value
        assert fake_vault.list_keys("mgdio/google") == [KEY]

    def test_invalid_slug_rejected_before_flow(self, tmp_appdata, monkeypatch):
        from mgdio.exceptions import MgdioAuthError

        run_setup = MagicMock()
        monkeypatch.setattr(google_auth, "run_setup_flow", run_setup)

        with pytest.raises(MgdioAuthError):
            google_auth.authorize_profile("Bad Slug")
        run_setup.assert_not_called()

    def test_headless_dispatches_to_headless_flow(
        self, tmp_appdata, fake_vault, monkeypatch
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
        self, tmp_appdata, fake_vault, monkeypatch
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
    def test_removes_vault_entry_and_cache(self, tmp_appdata, fake_vault, monkeypatch):
        _seed_token(fake_vault)
        monkeypatch.setattr(google_auth, "_credentials", {SLUG: _make_creds()})

        google_auth.clear_stored_token(SLUG)

        assert not fake_vault.exists(KEY)
        assert SLUG not in google_auth._credentials

    def test_swallows_missing_entry_without_raising(self, tmp_appdata, fake_vault):
        google_auth.clear_stored_token(SLUG)
        assert SLUG not in google_auth._credentials


class TestSettingsConsistency:
    def test_client_secret_path_lives_under_google_subdir(self):
        assert GOOGLE_CLIENT_SECRET_PATH.parent.name == "google"
        assert GOOGLE_CLIENT_SECRET_PATH.name == "client_secret.json"

    def test_vault_key_namespaced_under_mgdio_google(self):
        assert google_vault_key("svc") == "mgdio/google/svc"


class TestRefreshErrorHandling:
    def _expired_creds(self, monkeypatch, refresh_exc):
        loaded = _make_creds(valid=False, expired=True)
        loaded.refresh.side_effect = refresh_exc
        monkeypatch.setattr(
            "mgdio.auth.google.auth.Credentials.from_authorized_user_info",
            MagicMock(return_value=loaded),
        )
        return loaded

    def test_invalid_grant_falls_through_to_consent_flow(
        self, tmp_appdata, fake_vault, monkeypatch
    ):
        from google.auth.exceptions import RefreshError

        _seed_token(fake_vault)
        self._expired_creds(
            monkeypatch,
            RefreshError("invalid_grant: Token has been expired or revoked."),
        )
        fresh = _make_creds(valid=True)
        run_setup = MagicMock(return_value=fresh)
        monkeypatch.setattr(google_auth, "run_setup_flow", run_setup)

        assert google_auth.get_credentials(SLUG) is fresh
        run_setup.assert_called_once()

    def test_transient_refresh_error_propagates_without_flow(
        self, tmp_appdata, fake_vault, monkeypatch
    ):
        from google.auth.exceptions import RefreshError

        from mgdio.exceptions import MgdioAPIError

        _seed_token(fake_vault)
        before = fake_vault.get(KEY)
        self._expired_creds(monkeypatch, RefreshError("internal_failure"))
        run_setup = MagicMock()
        monkeypatch.setattr(google_auth, "run_setup_flow", run_setup)

        with pytest.raises(MgdioAPIError, match="transient"):
            google_auth.get_credentials(SLUG)
        run_setup.assert_not_called()
        assert fake_vault.get(KEY) == before  # stored token untouched

    def test_retryable_refresh_error_is_transient_even_with_invalid_grant(
        self, tmp_appdata, fake_vault, monkeypatch
    ):
        from google.auth.exceptions import RefreshError

        from mgdio.exceptions import MgdioAPIError

        _seed_token(fake_vault)
        exc = RefreshError("invalid_grant-ish flake", retryable=True)
        self._expired_creds(monkeypatch, exc)
        run_setup = MagicMock()
        monkeypatch.setattr(google_auth, "run_setup_flow", run_setup)

        with pytest.raises(MgdioAPIError):
            google_auth.get_credentials(SLUG)
        run_setup.assert_not_called()


class TestNonInteractiveGuard:
    def test_implicit_flow_blocked_without_tty(
        self, tmp_appdata, fake_vault, monkeypatch
    ):
        from mgdio.exceptions import MgdioInteractionRequiredError

        _seed_token(fake_vault)
        # Stored token loads but is unusable (invalid, not refreshable),
        # forcing the implicit-flow fallback.
        dead = _make_creds(valid=False, expired=False)
        monkeypatch.setattr(
            "mgdio.auth.google.auth.Credentials.from_authorized_user_info",
            MagicMock(return_value=dead),
        )
        monkeypatch.setenv("MGDIO_NONINTERACTIVE", "1")
        run_setup = MagicMock()
        monkeypatch.setattr(google_auth, "run_setup_flow", run_setup)

        with pytest.raises(
            MgdioInteractionRequiredError, match="mgdio auth google --profile svc"
        ):
            google_auth.get_credentials(SLUG)
        run_setup.assert_not_called()


class TestVaultNotConfigured:
    def test_missing_vault_password_surfaces_mgdvault_error(
        self, tmp_appdata, monkeypatch
    ):
        """Without a vault, the first secret read raises mgdvault's own error."""
        import mgdvault
        from mgdvault import VaultConfigurationError

        mgdvault.reset_default_vault()  # fall back to (stripped) env resolution
        with pytest.raises(VaultConfigurationError, match="MGDVAULT_PASSWORD"):
            google_auth.get_credentials(SLUG)
