"""Unit tests for ``mgdio.auth.ynab.auth``."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mgdio.auth.ynab import auth as ynab_auth
from mgdio.settings import YNAB_VAULT_KEY


class TestGetToken:
    def test_returns_in_process_cached_token_without_vault_call(
        self, fake_vault, monkeypatch
    ):
        monkeypatch.setattr(ynab_auth, "_token", "cached-token")
        run_setup = MagicMock()
        monkeypatch.setattr(ynab_auth, "run_setup_flow", run_setup)

        assert ynab_auth.get_token() == "cached-token"
        assert fake_vault.list_keys() == []
        run_setup.assert_not_called()

    def test_loads_token_from_vault(self, fake_vault, monkeypatch):
        fake_vault.set(YNAB_VAULT_KEY, "stored-token")
        run_setup = MagicMock()
        monkeypatch.setattr(ynab_auth, "run_setup_flow", run_setup)

        assert ynab_auth.get_token() == "stored-token"
        assert ynab_auth._token == "stored-token"
        run_setup.assert_not_called()

    def test_runs_setup_flow_when_vault_empty_and_persists_result(
        self, fake_vault, monkeypatch
    ):
        run_setup = MagicMock(return_value="freshly-pasted-token")
        monkeypatch.setattr(ynab_auth, "run_setup_flow", run_setup)

        result = ynab_auth.get_token()

        assert result == "freshly-pasted-token"
        run_setup.assert_called_once()
        assert fake_vault.get(YNAB_VAULT_KEY) == "freshly-pasted-token"


class TestClearStoredToken:
    def test_removes_vault_entry_and_resets_cache(self, fake_vault, monkeypatch):
        fake_vault.set(YNAB_VAULT_KEY, "x")
        monkeypatch.setattr(ynab_auth, "_token", "x")

        ynab_auth.clear_stored_token()

        assert not fake_vault.exists(YNAB_VAULT_KEY)
        assert ynab_auth._token is None

    def test_swallows_missing_entry_without_raising(self, fake_vault):
        ynab_auth.clear_stored_token()
        assert ynab_auth._token is None


class TestSettingsConsistency:
    def test_vault_key_namespaced_under_mgdio_ynab(self):
        assert YNAB_VAULT_KEY == "mgdio/ynab/token"


class TestNonInteractiveGuard:
    def test_implicit_flow_blocked(self, fake_vault, monkeypatch):
        from mgdio.exceptions import MgdioInteractionRequiredError

        monkeypatch.setenv("MGDIO_NONINTERACTIVE", "1")
        run_setup = MagicMock()
        monkeypatch.setattr(ynab_auth, "run_setup_flow", run_setup)

        with pytest.raises(MgdioInteractionRequiredError, match="mgdio auth ynab"):
            ynab_auth.get_token()
        run_setup.assert_not_called()


class TestAuthorize:
    def test_bypasses_noninteractive_guard(self, fake_vault, monkeypatch):
        monkeypatch.setenv("MGDIO_NONINTERACTIVE", "1")
        run_setup = MagicMock(return_value="pasted-token")
        monkeypatch.setattr(ynab_auth, "run_setup_flow", run_setup)

        assert ynab_auth.authorize() == "pasted-token"
        run_setup.assert_called_once()
