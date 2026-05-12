"""Unit tests for ``mgdio.auth.google._headless_flow``."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from mgdio.auth.google import _headless_flow
from mgdio.auth.google._headless_flow import HEADLESS_REDIRECT_URI
from mgdio.exceptions import MissingClientSecretError
from mgdio.settings import GOOGLE_SCOPES


def _valid_client_secret_json() -> str:
    return json.dumps(
        {
            "installed": {
                "client_id": "abc.apps.googleusercontent.com",
                "client_secret": "shhh",
                "redirect_uris": ["http://localhost"],
            }
        }
    )


def _make_creds_mock() -> MagicMock:
    creds = MagicMock(name="Credentials")
    creds.valid = True
    creds.to_json.return_value = json.dumps({"token": "abc"})
    return creds


def _make_flow_mock(creds: MagicMock | None = None) -> MagicMock:
    """Build a Flow mock whose authorization_url + credentials work as wired."""
    flow = MagicMock(name="Flow")
    flow.authorization_url.return_value = (
        "https://accounts.google.com/o/oauth2/auth?fake=1",
        "state-xyz",
    )
    flow.credentials = creds or _make_creds_mock()
    # fetch_token is a no-op by default; tests override side_effect when needed.
    flow.fetch_token.return_value = None
    return flow


def _feed_inputs(monkeypatch, values: list[str]) -> list[str]:
    """Patch builtins.input to return successive items from ``values``.

    Returns the (mutable) list so tests can inspect remaining items.
    """
    iterator = iter(values)
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: next(iterator))
    return values


class TestRunHeadlessFlow:
    def test_happy_path_writes_token(self, tmp_appdata, monkeypatch):
        secret_path = tmp_appdata / "google" / "client_secret.json"
        secret_path.write_text(_valid_client_secret_json(), encoding="utf-8")

        flow = _make_flow_mock()
        from_secrets = MagicMock(return_value=flow)
        monkeypatch.setattr(
            "mgdio.auth.google._headless_flow.Flow.from_client_secrets_file",
            from_secrets,
        )
        _feed_inputs(
            monkeypatch,
            [f"{HEADLESS_REDIRECT_URI}?state=state-xyz&code=auth-code-1"],
        )

        result = _headless_flow.run_headless_flow(secret_path, list(GOOGLE_SCOPES))

        assert result is flow.credentials
        flow.fetch_token.assert_called_once()
        kwargs = flow.fetch_token.call_args.kwargs
        assert kwargs["authorization_response"].endswith("code=auth-code-1")

    def test_flow_built_with_correct_scopes_and_redirect(
        self, tmp_appdata, monkeypatch
    ):
        secret_path = tmp_appdata / "google" / "client_secret.json"
        secret_path.write_text(_valid_client_secret_json(), encoding="utf-8")

        flow = _make_flow_mock()
        from_secrets = MagicMock(return_value=flow)
        monkeypatch.setattr(
            "mgdio.auth.google._headless_flow.Flow.from_client_secrets_file",
            from_secrets,
        )
        _feed_inputs(monkeypatch, [f"{HEADLESS_REDIRECT_URI}?code=x&state=y"])

        _headless_flow.run_headless_flow(secret_path, list(GOOGLE_SCOPES))

        from_secrets.assert_called_once()
        # First positional arg is the client_secret_path (stringified).
        args = from_secrets.call_args.args
        kwargs = from_secrets.call_args.kwargs
        assert args[0] == str(secret_path)
        assert kwargs["scopes"] == list(GOOGLE_SCOPES)
        assert kwargs["redirect_uri"] == HEADLESS_REDIRECT_URI

    def test_authorization_url_requests_offline_access(self, tmp_appdata, monkeypatch):
        secret_path = tmp_appdata / "google" / "client_secret.json"
        secret_path.write_text(_valid_client_secret_json(), encoding="utf-8")

        flow = _make_flow_mock()
        monkeypatch.setattr(
            "mgdio.auth.google._headless_flow.Flow.from_client_secrets_file",
            MagicMock(return_value=flow),
        )
        _feed_inputs(monkeypatch, [f"{HEADLESS_REDIRECT_URI}?code=x&state=y"])

        _headless_flow.run_headless_flow(secret_path, list(GOOGLE_SCOPES))

        kwargs = flow.authorization_url.call_args.kwargs
        assert kwargs["access_type"] == "offline"
        assert kwargs["prompt"] == "consent"
        assert kwargs["include_granted_scopes"] == "true"

    def test_auth_url_printed_to_stderr(self, tmp_appdata, monkeypatch, capsys):
        secret_path = tmp_appdata / "google" / "client_secret.json"
        secret_path.write_text(_valid_client_secret_json(), encoding="utf-8")

        flow = _make_flow_mock()
        monkeypatch.setattr(
            "mgdio.auth.google._headless_flow.Flow.from_client_secrets_file",
            MagicMock(return_value=flow),
        )
        _feed_inputs(monkeypatch, [f"{HEADLESS_REDIRECT_URI}?code=x&state=y"])

        _headless_flow.run_headless_flow(secret_path, list(GOOGLE_SCOPES))

        captured = capsys.readouterr()
        assert "https://accounts.google.com/o/oauth2/auth?fake=1" in captured.err
        # Sanity: nothing went to stdout.
        assert captured.out == ""

    def test_empty_paste_raises_runtime_error(self, tmp_appdata, monkeypatch):
        secret_path = tmp_appdata / "google" / "client_secret.json"
        secret_path.write_text(_valid_client_secret_json(), encoding="utf-8")

        flow = _make_flow_mock()
        monkeypatch.setattr(
            "mgdio.auth.google._headless_flow.Flow.from_client_secrets_file",
            MagicMock(return_value=flow),
        )
        _feed_inputs(monkeypatch, [""])

        with pytest.raises(RuntimeError, match="No URL pasted"):
            _headless_flow.run_headless_flow(secret_path, list(GOOGLE_SCOPES))

        flow.fetch_token.assert_not_called()

    def test_fetch_token_failure_wraps_with_helpful_message(
        self, tmp_appdata, monkeypatch
    ):
        secret_path = tmp_appdata / "google" / "client_secret.json"
        secret_path.write_text(_valid_client_secret_json(), encoding="utf-8")

        flow = _make_flow_mock()
        flow.fetch_token.side_effect = Exception("mismatching_state")
        monkeypatch.setattr(
            "mgdio.auth.google._headless_flow.Flow.from_client_secrets_file",
            MagicMock(return_value=flow),
        )
        _feed_inputs(monkeypatch, [f"{HEADLESS_REDIRECT_URI}?code=x&state=wrong"])

        with pytest.raises(RuntimeError) as exc_info:
            _headless_flow.run_headless_flow(secret_path, list(GOOGLE_SCOPES))

        msg = str(exc_info.value)
        assert "Failed to exchange" in msg
        assert "mismatching_state" in msg


class TestPromptAndSaveClientSecret:
    def test_prompts_for_client_secret_when_missing(self, tmp_appdata, monkeypatch):
        secret_path = tmp_appdata / "google" / "client_secret.json"
        assert not secret_path.exists()

        flow = _make_flow_mock()
        monkeypatch.setattr(
            "mgdio.auth.google._headless_flow.Flow.from_client_secrets_file",
            MagicMock(return_value=flow),
        )
        # Feed: JSON line 1, JSON line 2, blank terminator, then the URL paste.
        client_secret = _valid_client_secret_json()
        _feed_inputs(
            monkeypatch,
            [
                client_secret,
                "",  # blank-line terminator
                f"{HEADLESS_REDIRECT_URI}?code=x&state=y",
            ],
        )

        _headless_flow.run_headless_flow(secret_path, list(GOOGLE_SCOPES))

        assert secret_path.exists()
        saved = json.loads(secret_path.read_text(encoding="utf-8"))
        assert "installed" in saved
        assert saved["installed"]["client_id"].endswith("googleusercontent.com")

    def test_rejects_garbage_paste(self, tmp_appdata, monkeypatch):
        secret_path = tmp_appdata / "google" / "client_secret.json"

        _feed_inputs(monkeypatch, ["not valid json at all", ""])

        with pytest.raises(MissingClientSecretError, match="not valid JSON"):
            _headless_flow._prompt_and_save_client_secret(secret_path)

        assert not secret_path.exists()

    def test_rejects_non_oauth_json(self, tmp_appdata, monkeypatch):
        secret_path = tmp_appdata / "google" / "client_secret.json"
        _feed_inputs(
            monkeypatch,
            [json.dumps({"some_other": "shape"}), ""],
        )

        with pytest.raises(MissingClientSecretError, match="doesn't look like"):
            _headless_flow._prompt_and_save_client_secret(secret_path)

        assert not secret_path.exists()

    def test_rejects_empty_paste(self, tmp_appdata, monkeypatch):
        secret_path = tmp_appdata / "google" / "client_secret.json"

        def _raise_eof(*_a, **_k):
            raise EOFError()

        monkeypatch.setattr("builtins.input", _raise_eof)

        with pytest.raises(MissingClientSecretError, match="No client_secret"):
            _headless_flow._prompt_and_save_client_secret(secret_path)
