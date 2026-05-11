"""Smoke tests for ``mgdio.cli``."""

from __future__ import annotations

from unittest.mock import MagicMock

from click.testing import CliRunner

from mgdio import cli as cli_module


class TestAuthGoogle:
    def test_runs_get_credentials_and_prints_authenticated(self, monkeypatch):
        get_creds = MagicMock()
        clear = MagicMock()
        monkeypatch.setattr(cli_module, "get_credentials", get_creds)
        monkeypatch.setattr(cli_module, "clear_stored_token", clear)

        result = CliRunner().invoke(cli_module.cli, ["auth", "google"])

        assert result.exit_code == 0, result.output
        assert "Authenticated." in result.output
        get_creds.assert_called_once()
        clear.assert_not_called()

    def test_reset_clears_before_get_credentials(self, monkeypatch):
        parent = MagicMock()
        monkeypatch.setattr(cli_module, "clear_stored_token", parent.clear)
        monkeypatch.setattr(cli_module, "get_credentials", parent.get)

        result = CliRunner().invoke(cli_module.cli, ["auth", "google", "--reset"])

        assert result.exit_code == 0, result.output
        assert [c[0] for c in parent.mock_calls] == ["clear", "get"]


class TestCliShape:
    def test_top_level_help_lists_auth_group(self):
        result = CliRunner().invoke(cli_module.cli, ["--help"])
        assert result.exit_code == 0
        assert "auth" in result.output
        assert "gmail" in result.output

    def test_auth_help_lists_google_subcommand(self):
        result = CliRunner().invoke(cli_module.cli, ["auth", "--help"])
        assert result.exit_code == 0
        assert "google" in result.output

    def test_gmail_help_lists_subcommands(self):
        result = CliRunner().invoke(cli_module.cli, ["gmail", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "send" in result.output
        assert "get" in result.output


class TestGmailCommands:
    def test_gmail_list_invokes_fetch_messages(self, monkeypatch):
        from datetime import datetime, timezone

        from mgdio.gmail.messages import GmailMessage

        sample = GmailMessage(
            id="abc",
            thread_id="t",
            subject="hi",
            sender="alice@example.com",
            to=("me@example.com",),
            cc=(),
            date=datetime(2026, 5, 8, 14, 30, tzinfo=timezone.utc),
            snippet="snip",
            body_text="body",
            body_html=None,
            label_ids=("INBOX",),
        )
        fetch_mock = MagicMock(return_value=[sample])
        monkeypatch.setattr(cli_module, "fetch_messages", fetch_mock)

        result = CliRunner().invoke(cli_module.cli, ["gmail", "list", "--max", "3"])

        assert result.exit_code == 0, result.output
        assert "hi" in result.output
        assert "abc" in result.output
        fetch_mock.assert_called_once_with("", 3)

    def test_gmail_send_invokes_send_email(self, monkeypatch):
        send_mock = MagicMock(return_value="sent-id-42")
        monkeypatch.setattr(cli_module, "send_email", send_mock)

        result = CliRunner().invoke(
            cli_module.cli,
            [
                "gmail",
                "send",
                "--to",
                "x@example.com",
                "--subject",
                "hi",
                "--body",
                "hello",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "sent-id-42" in result.output
        send_mock.assert_called_once()
        kwargs = send_mock.call_args.kwargs
        assert kwargs["to"] == "x@example.com"
        assert kwargs["subject"] == "hi"
        assert kwargs["body"] == "hello"
        assert kwargs["attachments"] is None
