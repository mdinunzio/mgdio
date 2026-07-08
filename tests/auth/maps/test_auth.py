"""Unit tests for ``mgdio.auth.maps.auth``."""

from __future__ import annotations

from unittest.mock import MagicMock

from mgdio.auth.maps import auth as maps_auth
from mgdio.settings import MAPS_KEYRING_SERVICE, MAPS_KEYRING_USERNAME

KEY = (MAPS_KEYRING_SERVICE, MAPS_KEYRING_USERNAME)


class TestGetApiKey:
    def test_returns_in_process_cache_without_keyring(self, fake_keyring, monkeypatch):
        monkeypatch.setattr(maps_auth, "_api_key", "cached-key")
        run_setup = MagicMock()
        monkeypatch.setattr(maps_auth, "run_setup_flow", run_setup)

        assert maps_auth.get_api_key() == "cached-key"
        assert fake_keyring == {}
        run_setup.assert_not_called()

    def test_loads_from_keyring(self, fake_keyring, monkeypatch):
        fake_keyring[KEY] = "stored-key"
        run_setup = MagicMock()
        monkeypatch.setattr(maps_auth, "run_setup_flow", run_setup)

        assert maps_auth.get_api_key() == "stored-key"
        assert maps_auth._api_key == "stored-key"
        run_setup.assert_not_called()

    def test_runs_setup_flow_when_empty_and_persists(self, fake_keyring, monkeypatch):
        run_setup = MagicMock(return_value="fresh-key")
        monkeypatch.setattr(maps_auth, "run_setup_flow", run_setup)

        result = maps_auth.get_api_key()

        assert result == "fresh-key"
        run_setup.assert_called_once()
        assert fake_keyring[KEY] == "fresh-key"


class TestClearStoredToken:
    def test_removes_entry_and_resets_cache(self, fake_keyring, monkeypatch):
        fake_keyring[KEY] = "x"
        monkeypatch.setattr(maps_auth, "_api_key", "x")

        maps_auth.clear_stored_token()

        assert KEY not in fake_keyring
        assert maps_auth._api_key is None

    def test_swallows_missing_entry(self, fake_keyring):
        maps_auth.clear_stored_token()  # must not raise
        assert maps_auth._api_key is None
