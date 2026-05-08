"""Unit tests for ``mgdio.gmail.auth``."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

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

    def test_runs_setup_flow_when_no_token_and_persists_result(
        self, tmp_appdata, fake_keyring, monkeypatch
    ):
        new_creds = _make_creds(valid=True)
        run_setup = MagicMock(return_value=new_creds)
        monkeypatch.setattr(gmail_auth, "run_setup_flow", run_setup)

        result = gmail_auth.get_credentials()

        assert result is new_creds
        run_setup.assert_called_once()
        # First positional arg is the client_secret_path; second is the scopes list.
        called_path, called_scopes = run_setup.call_args.args
        assert called_path.name == "client_secret.json"
        assert called_scopes == list(gmail_auth.GMAIL_SCOPES)
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


class TestSetupServer:
    def test_render_page_includes_target_path_and_instructions(self, tmp_path):
        from mgdio.gmail import _setup_server

        target = tmp_path / "client_secret.json"
        page = _setup_server._render_page(target)

        assert str(target) in page
        assert "Google Auth Platform" in page
        assert "Drag &amp; drop" in page

    def test_looks_like_client_secret_accepts_installed_and_web(self):
        from mgdio.gmail._setup_server import _looks_like_client_secret

        assert _looks_like_client_secret(
            {"installed": {"client_id": "x", "client_secret": "y"}}
        )
        assert _looks_like_client_secret(
            {"web": {"client_id": "x", "client_secret": "y"}}
        )

    def test_looks_like_client_secret_rejects_garbage(self):
        from mgdio.gmail._setup_server import _looks_like_client_secret

        assert not _looks_like_client_secret({})
        assert not _looks_like_client_secret({"installed": {"client_id": "x"}})
        assert not _looks_like_client_secret("not a dict")
        assert not _looks_like_client_secret({"installed": "string-not-dict"})
