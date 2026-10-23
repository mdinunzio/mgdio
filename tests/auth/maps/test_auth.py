"""Unit tests for ``mgdio.auth.maps.auth``."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mgdio.auth.maps import auth as maps_auth
from mgdio.settings import MAPS_VAULT_KEY


class TestGetApiKey:
    def test_returns_in_process_cache_without_vault(self, fake_vault, monkeypatch):
        monkeypatch.setattr(maps_auth, "_api_key", "cached-key")
        run_setup = MagicMock()
        monkeypatch.setattr(maps_auth, "run_setup_flow", run_setup)

        assert maps_auth.get_api_key() == "cached-key"
        assert fake_vault.list_keys() == []
        run_setup.assert_not_called()

    def test_loads_from_vault(self, fake_vault, monkeypatch):
        fake_vault.set(MAPS_VAULT_KEY, "stored-key")
        run_setup = MagicMock()
        monkeypatch.setattr(maps_auth, "run_setup_flow", run_setup)

        assert maps_auth.get_api_key() == "stored-key"
        assert maps_auth._api_key == "stored-key"
        run_setup.assert_not_called()

    def test_runs_setup_flow_when_empty_and_persists(self, fake_vault, monkeypatch):
        run_setup = MagicMock(return_value="fresh-key")
        monkeypatch.setattr(maps_auth, "run_setup_flow", run_setup)

        result = maps_auth.get_api_key()

        assert result == "fresh-key"
        run_setup.assert_called_once()
        assert fake_vault.get(MAPS_VAULT_KEY) == "fresh-key"


class TestClearStoredToken:
    def test_removes_entry_and_resets_cache(self, fake_vault, monkeypatch):
        fake_vault.set(MAPS_VAULT_KEY, "x")
        monkeypatch.setattr(maps_auth, "_api_key", "x")

        maps_auth.clear_stored_token()

        assert not fake_vault.exists(MAPS_VAULT_KEY)
        assert maps_auth._api_key is None

    def test_swallows_missing_entry(self, fake_vault):
        maps_auth.clear_stored_token()  # must not raise
        assert maps_auth._api_key is None


class TestSettingsConsistency:
    def test_vault_key_namespaced_under_mgdio_maps(self):
        assert MAPS_VAULT_KEY == "mgdio/maps/api_key"


class TestNonInteractiveGuard:
    def test_implicit_flow_blocked(self, fake_vault, monkeypatch):
        from mgdio.exceptions import MgdioInteractionRequiredError

        monkeypatch.setenv("MGDIO_NONINTERACTIVE", "1")
        run_setup = MagicMock()
        monkeypatch.setattr(maps_auth, "run_setup_flow", run_setup)

        with pytest.raises(MgdioInteractionRequiredError, match="mgdio auth maps"):
            maps_auth.get_api_key()
        run_setup.assert_not_called()


class TestAuthorize:
    def test_bypasses_noninteractive_guard(self, fake_vault, monkeypatch):
        monkeypatch.setenv("MGDIO_NONINTERACTIVE", "1")
        run_setup = MagicMock(return_value="pasted-key")
        monkeypatch.setattr(maps_auth, "run_setup_flow", run_setup)

        assert maps_auth.authorize() == "pasted-key"
        run_setup.assert_called_once()
