"""Unit tests for ``mgdio.gmail.auth``."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from mgdio.exceptions import MissingClientSecretError
from mgdio.gmail import auth as gmail_auth
from mgdio.settings import KEYRING_SERVICE_GMAIL, KEYRING_USERNAME_GMAIL


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
        monkeypatch.setattr(gmail_auth, "_credentials", cached)

        from_authorized = MagicMock()
        monkeypatch.setattr(
            "mgdio.gmail.auth.Credentials.from_authorized_user_info", from_authorized
        )

        result = gmail_auth.get_credentials()

        assert result is cached
        assert fake_keyring == {}
        from_authorized.assert_not_called()

    def test_loads_fresh_token_from_keyring(self, fake_keyring, monkeypatch):
        fake_keyring[(KEYRING_SERVICE_GMAIL, KEYRING_USERNAME_GMAIL)] = json.dumps(
            {"token": "access", "refresh_token": "refresh-token"}
        )
        loaded = _make_creds(valid=True)
        monkeypatch.setattr(
            "mgdio.gmail.auth.Credentials.from_authorized_user_info",
            MagicMock(return_value=loaded),
        )

        result = gmail_auth.get_credentials()

        assert result is loaded
        assert gmail_auth._credentials is loaded

    def test_refreshes_expired_token_and_writes_back_to_keyring(
        self, fake_keyring, monkeypatch
    ):
        fake_keyring[(KEYRING_SERVICE_GMAIL, KEYRING_USERNAME_GMAIL)] = "{}"
        loaded = _make_creds(valid=False, expired=True)

        def fake_refresh(_request) -> None:
            loaded.valid = True
            loaded.expired = False
            loaded.to_json.return_value = json.dumps({"token": "refreshed"})

        loaded.refresh.side_effect = fake_refresh
        monkeypatch.setattr(
            "mgdio.gmail.auth.Credentials.from_authorized_user_info",
            MagicMock(return_value=loaded),
        )

        result = gmail_auth.get_credentials()

        assert result is loaded
        loaded.refresh.assert_called_once()
        assert json.loads(
            fake_keyring[(KEYRING_SERVICE_GMAIL, KEYRING_USERNAME_GMAIL)]
        ) == {"token": "refreshed"}

    def test_missing_client_secret_raises_and_opens_help_page(
        self, tmp_appdata, fake_keyring, monkeypatch
    ):
        opened = MagicMock()
        monkeypatch.setattr(gmail_auth, "render_to_temp_and_open", opened)

        with pytest.raises(MissingClientSecretError):
            gmail_auth.get_credentials()

        opened.assert_called_once()
        assert fake_keyring == {}

    def test_runs_oauth_flow_when_secret_present_and_persists_token(
        self, tmp_appdata, fake_keyring, monkeypatch
    ):
        client_secret = tmp_appdata / "client_secret.json"
        client_secret.write_text("{}", encoding="utf-8")

        flow = MagicMock()
        new_creds = _make_creds(valid=True)
        flow.run_local_server.return_value = new_creds
        monkeypatch.setattr(
            "mgdio.gmail.auth.InstalledAppFlow.from_client_secrets_file",
            MagicMock(return_value=flow),
        )

        result = gmail_auth.get_credentials()

        assert result is new_creds
        flow.run_local_server.assert_called_once_with(port=0, open_browser=True)
        assert (
            fake_keyring[(KEYRING_SERVICE_GMAIL, KEYRING_USERNAME_GMAIL)]
            == new_creds.to_json.return_value
        )


class TestClearStoredToken:
    def test_removes_keyring_entry_and_resets_cache(self, fake_keyring, monkeypatch):
        fake_keyring[(KEYRING_SERVICE_GMAIL, KEYRING_USERNAME_GMAIL)] = "x"
        monkeypatch.setattr(gmail_auth, "_credentials", _make_creds())

        gmail_auth.clear_stored_token()

        assert (KEYRING_SERVICE_GMAIL, KEYRING_USERNAME_GMAIL) not in fake_keyring
        assert gmail_auth._credentials is None

    def test_swallows_missing_entry_without_raising(self, fake_keyring):
        gmail_auth.clear_stored_token()
        assert gmail_auth._credentials is None


class TestSetupPage:
    def test_render_writes_temp_html_with_path(self, tmp_path, monkeypatch):
        from mgdio.gmail import _setup_page

        monkeypatch.setattr(_setup_page.webbrowser, "open", lambda _url: None)
        target = tmp_path / "client_secret.json"

        out = _setup_page.render_to_temp_and_open(target)

        contents = out.read_text(encoding="utf-8")
        assert str(target) in contents
        assert "OAuth consent screen" in contents
