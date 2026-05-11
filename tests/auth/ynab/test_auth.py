"""Unit tests for ``mgdio.auth.ynab.auth``."""

from __future__ import annotations

from unittest.mock import MagicMock

from mgdio.auth.ynab import auth as ynab_auth
from mgdio.settings import YNAB_KEYRING_SERVICE, YNAB_KEYRING_USERNAME


class TestGetToken:
    def test_returns_in_process_cached_token_without_keyring_call(
        self, fake_keyring, monkeypatch
    ):
        monkeypatch.setattr(ynab_auth, "_token", "cached-token")
        run_setup = MagicMock()
        monkeypatch.setattr(ynab_auth, "run_setup_flow", run_setup)

        assert ynab_auth.get_token() == "cached-token"
        assert fake_keyring == {}
        run_setup.assert_not_called()

    def test_loads_token_from_keyring(self, fake_keyring, monkeypatch):
        fake_keyring[(YNAB_KEYRING_SERVICE, YNAB_KEYRING_USERNAME)] = "stored-token"
        run_setup = MagicMock()
        monkeypatch.setattr(ynab_auth, "run_setup_flow", run_setup)

        assert ynab_auth.get_token() == "stored-token"
        assert ynab_auth._token == "stored-token"
        run_setup.assert_not_called()

    def test_runs_setup_flow_when_keyring_empty_and_persists_result(
        self, fake_keyring, monkeypatch
    ):
        run_setup = MagicMock(return_value="freshly-pasted-token")
        monkeypatch.setattr(ynab_auth, "run_setup_flow", run_setup)

        result = ynab_auth.get_token()

        assert result == "freshly-pasted-token"
        run_setup.assert_called_once()
        assert (
            fake_keyring[(YNAB_KEYRING_SERVICE, YNAB_KEYRING_USERNAME)]
            == "freshly-pasted-token"
        )


class TestClearStoredToken:
    def test_removes_keyring_entry_and_resets_cache(self, fake_keyring, monkeypatch):
        fake_keyring[(YNAB_KEYRING_SERVICE, YNAB_KEYRING_USERNAME)] = "x"
        monkeypatch.setattr(ynab_auth, "_token", "x")

        ynab_auth.clear_stored_token()

        assert (YNAB_KEYRING_SERVICE, YNAB_KEYRING_USERNAME) not in fake_keyring
        assert ynab_auth._token is None

    def test_swallows_missing_entry_without_raising(self, fake_keyring):
        ynab_auth.clear_stored_token()
        assert ynab_auth._token is None


class TestSettingsConsistency:
    def test_keyring_identifiers_namespace_under_mgdio_ynab(self):
        assert YNAB_KEYRING_SERVICE == "mgdio:ynab"
        assert YNAB_KEYRING_USERNAME == "personal_access_token"
