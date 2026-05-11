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

    def test_auth_help_lists_google_subcommand(self):
        result = CliRunner().invoke(cli_module.cli, ["auth", "--help"])
        assert result.exit_code == 0
        assert "google" in result.output

    def test_old_gmail_command_is_gone(self):
        result = CliRunner().invoke(cli_module.cli, ["auth", "gmail"])
        assert result.exit_code != 0
