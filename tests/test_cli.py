"""Smoke tests for ``mgdio.cli``."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from mgdio import cli as cli_module


class TestAuthGoogle:
    def test_bare_auth_google_errors_with_guidance(self, monkeypatch):
        authorize = MagicMock()
        monkeypatch.setattr(cli_module, "authorize_google_profile", authorize)

        result = CliRunner().invoke(cli_module.cli, ["auth", "google"])

        assert result.exit_code != 0
        assert "--profile" in result.output
        authorize.assert_not_called()

    def test_profile_authorizes_and_prints_message(self, monkeypatch):
        authorize = MagicMock()
        clear = MagicMock()
        monkeypatch.setattr(cli_module, "authorize_google_profile", authorize)
        monkeypatch.setattr(cli_module, "clear_google_token", clear)
        monkeypatch.setattr(cli_module, "detect_legacy_token", lambda: False)

        result = CliRunner().invoke(
            cli_module.cli, ["auth", "google", "--profile", "svc"]
        )

        assert result.exit_code == 0, result.output
        assert "Authenticated profile 'svc'." in result.output
        authorize.assert_called_once_with("svc", headless=False)
        clear.assert_not_called()

    def test_reset_clears_before_authorize(self, monkeypatch):
        parent = MagicMock()
        monkeypatch.setattr(cli_module, "clear_google_token", parent.clear)
        monkeypatch.setattr(cli_module, "authorize_google_profile", parent.authorize)
        monkeypatch.setattr(cli_module, "detect_legacy_token", lambda: False)

        result = CliRunner().invoke(
            cli_module.cli, ["auth", "google", "--profile", "svc", "--reset"]
        )

        assert result.exit_code == 0, result.output
        assert [c[0] for c in parent.mock_calls] == ["clear", "authorize"]
        parent.clear.assert_called_once_with("svc")

    def test_headless_flag_passes_through(self, monkeypatch):
        authorize = MagicMock()
        monkeypatch.setattr(cli_module, "authorize_google_profile", authorize)
        monkeypatch.setattr(cli_module, "clear_google_token", MagicMock())
        monkeypatch.setattr(cli_module, "detect_legacy_token", lambda: False)

        result = CliRunner().invoke(
            cli_module.cli, ["auth", "google", "--profile", "svc", "--headless"]
        )

        assert result.exit_code == 0, result.output
        authorize.assert_called_once_with("svc", headless=True)

    def test_help_lists_profile_and_headless_flags(self):
        result = CliRunner().invoke(cli_module.cli, ["auth", "google", "--help"])
        assert result.exit_code == 0
        assert "--headless" in result.output
        assert "--profile" in result.output

    def test_profiles_subcommand_lists_and_marks(self, monkeypatch):
        monkeypatch.setattr(cli_module, "live_profiles", lambda: ["alpha", "beta"])
        monkeypatch.setenv("MGDIO_GOOGLE_PROFILE", "beta")

        result = CliRunner().invoke(cli_module.cli, ["auth", "google", "profiles"])

        assert result.exit_code == 0, result.output
        assert "alpha" in result.output
        assert "beta" in result.output
        assert "env-default" in result.output  # beta marked

    def test_profiles_subcommand_empty(self, monkeypatch):
        monkeypatch.setattr(cli_module, "live_profiles", lambda: [])
        result = CliRunner().invoke(cli_module.cli, ["auth", "google", "profiles"])
        assert result.exit_code == 0, result.output
        assert "no Google profiles" in result.output

    def test_remove_requires_a_target(self, monkeypatch):
        clear = MagicMock()
        monkeypatch.setattr(cli_module, "clear_google_token", clear)
        result = CliRunner().invoke(cli_module.cli, ["auth", "google", "remove"])
        assert result.exit_code != 0
        assert "--profile" in result.output
        clear.assert_not_called()

    def test_remove_rejects_multiple_targets(self, monkeypatch):
        result = CliRunner().invoke(
            cli_module.cli,
            ["auth", "google", "remove", "--profile", "svc", "--legacy"],
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output

    def test_remove_profile_with_yes(self, monkeypatch):
        clear = MagicMock()
        monkeypatch.setattr(cli_module, "clear_google_token", clear)

        result = CliRunner().invoke(
            cli_module.cli,
            ["auth", "google", "remove", "--profile", "svc", "--yes"],
        )

        assert result.exit_code == 0, result.output
        clear.assert_called_once_with("svc")
        assert "Removed profile 'svc'." in result.output

    def test_remove_profile_confirm_abort(self, monkeypatch):
        clear = MagicMock()
        monkeypatch.setattr(cli_module, "clear_google_token", clear)

        # Answer 'n' to the confirmation prompt.
        result = CliRunner().invoke(
            cli_module.cli,
            ["auth", "google", "remove", "--profile", "svc"],
            input="n\n",
        )

        assert result.exit_code != 0  # aborted
        clear.assert_not_called()

    def test_remove_legacy(self, monkeypatch):
        clear_legacy = MagicMock()
        monkeypatch.setattr(cli_module, "clear_google_legacy_token", clear_legacy)

        result = CliRunner().invoke(
            cli_module.cli, ["auth", "google", "remove", "--legacy", "--yes"]
        )

        assert result.exit_code == 0, result.output
        clear_legacy.assert_called_once()
        assert "legacy" in result.output.lower()

    def test_remove_all(self, monkeypatch):
        clear = MagicMock()
        clear_legacy = MagicMock()
        monkeypatch.setattr(cli_module, "live_profiles", lambda: ["a", "b"])
        monkeypatch.setattr(cli_module, "detect_legacy_token", lambda: True)
        monkeypatch.setattr(cli_module, "clear_google_token", clear)
        monkeypatch.setattr(cli_module, "clear_google_legacy_token", clear_legacy)

        result = CliRunner().invoke(
            cli_module.cli, ["auth", "google", "remove", "--all", "--yes"]
        )

        assert result.exit_code == 0, result.output
        assert clear.call_count == 2
        clear_legacy.assert_called_once()


class TestAuthStatus:
    def test_lists_all_providers(self, monkeypatch):
        from mgdio.auth.status import ProviderStatus

        rows = [
            ProviderStatus("google", True, "1 profile(s): svc", "cmd-g"),
            ProviderStatus("ynab", False, "not authenticated", "mgdio auth ynab"),
            ProviderStatus("whoop", True, "token stored", "cmd-w"),
            ProviderStatus("maps", False, "not authenticated", "mgdio auth maps"),
        ]
        monkeypatch.setattr("mgdio.auth.status.get_auth_status", lambda: rows)

        result = CliRunner().invoke(cli_module.cli, ["auth", "status"])

        assert result.exit_code == 0, result.output
        assert "[x] google" in result.output
        assert "[ ] ynab" in result.output
        assert "[x] whoop" in result.output
        assert "[ ] maps" in result.output
        # Missing providers get their auth command listed.
        assert "mgdio auth ynab" in result.output
        assert "mgdio auth maps" in result.output

    def test_all_authenticated_no_remaining_section(self, monkeypatch):
        from mgdio.auth.status import ProviderStatus

        rows = [ProviderStatus("maps", True, "API key stored", "mgdio auth maps")]
        monkeypatch.setattr("mgdio.auth.status.get_auth_status", lambda: rows)

        result = CliRunner().invoke(cli_module.cli, ["auth", "status"])

        assert result.exit_code == 0, result.output
        assert "[x] maps" in result.output
        assert "remaining" not in result.output


class TestAuthYnab:
    def test_runs_get_token_and_prints_authenticated(self, monkeypatch):
        get_token = MagicMock()
        clear = MagicMock()
        monkeypatch.setattr(cli_module, "get_ynab_token", get_token)
        monkeypatch.setattr(cli_module, "clear_ynab_token", clear)

        result = CliRunner().invoke(cli_module.cli, ["auth", "ynab"])

        assert result.exit_code == 0, result.output
        assert "Authenticated." in result.output
        get_token.assert_called_once()
        clear.assert_not_called()

    def test_reset_clears_before_get_token(self, monkeypatch):
        parent = MagicMock()
        monkeypatch.setattr(cli_module, "clear_ynab_token", parent.clear)
        monkeypatch.setattr(cli_module, "get_ynab_token", parent.get)

        result = CliRunner().invoke(cli_module.cli, ["auth", "ynab", "--reset"])

        assert result.exit_code == 0, result.output
        assert [c[0] for c in parent.mock_calls] == ["clear", "get"]

    def test_headless_flag_passes_through(self, monkeypatch):
        get_token = MagicMock()
        monkeypatch.setattr(cli_module, "get_ynab_token", get_token)
        monkeypatch.setattr(cli_module, "clear_ynab_token", MagicMock())

        result = CliRunner().invoke(cli_module.cli, ["auth", "ynab", "--headless"])

        assert result.exit_code == 0, result.output
        get_token.assert_called_once_with(headless=True)


class TestAuthWhoop:
    def test_runs_get_token_and_prints_authenticated(self, monkeypatch):
        get_token = MagicMock()
        clear = MagicMock()
        monkeypatch.setattr(cli_module, "get_whoop_token", get_token)
        monkeypatch.setattr(cli_module, "clear_whoop_token", clear)

        result = CliRunner().invoke(cli_module.cli, ["auth", "whoop"])

        assert result.exit_code == 0, result.output
        assert "Authenticated." in result.output
        get_token.assert_called_once()
        clear.assert_not_called()

    def test_reset_clears_before_get_token(self, monkeypatch):
        parent = MagicMock()
        monkeypatch.setattr(cli_module, "clear_whoop_token", parent.clear)
        monkeypatch.setattr(cli_module, "get_whoop_token", parent.get)

        result = CliRunner().invoke(cli_module.cli, ["auth", "whoop", "--reset"])

        assert result.exit_code == 0, result.output
        assert [c[0] for c in parent.mock_calls] == ["clear", "get"]


class TestCliShape:
    def test_top_level_help_lists_groups(self):
        result = CliRunner().invoke(cli_module.cli, ["--help"])
        assert result.exit_code == 0
        assert "auth" in result.output
        assert "gmail" in result.output
        assert "sheets" in result.output
        assert "calendar" in result.output
        assert "ynab" in result.output
        assert "skills" in result.output
        assert "whoop" in result.output
        assert "drive" in result.output
        assert "maps" in result.output

    def test_python_m_mgdio_help_runs(self):
        """Sanity: ``python -m mgdio --help`` exits 0 (covers __main__.py)."""
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "mgdio", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "mgdio: personal connectivity tools." in result.stdout

    def test_auth_help_lists_subcommands(self):
        result = CliRunner().invoke(cli_module.cli, ["auth", "--help"])
        assert result.exit_code == 0
        assert "google" in result.output
        assert "ynab" in result.output
        assert "whoop" in result.output

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
        fetch_mock.assert_called_once_with("", 3, profile=None)

    def test_gmail_list_forwards_profile(self, monkeypatch):
        fetch_mock = MagicMock(return_value=[])
        monkeypatch.setattr(cli_module, "fetch_messages", fetch_mock)

        result = CliRunner().invoke(
            cli_module.cli, ["gmail", "list", "--profile", "svc"]
        )

        assert result.exit_code == 0, result.output
        assert fetch_mock.call_args.kwargs["profile"] == "svc"

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


class TestSheetsCommands:
    def test_sheets_help_lists_subcommands(self):
        result = CliRunner().invoke(cli_module.cli, ["sheets", "--help"])
        assert result.exit_code == 0
        for name in ("info", "read", "write", "append", "clear", "create"):
            assert name in result.output

    def test_sheets_read_prints_tab_separated(self, monkeypatch):
        fetch_mock = MagicMock(return_value=[["a", "b"], ["1", "2"]])
        monkeypatch.setattr(cli_module, "fetch_values", fetch_mock)

        result = CliRunner().invoke(
            cli_module.cli, ["sheets", "read", "sid", "Sheet1!A1:B2"]
        )

        assert result.exit_code == 0, result.output
        assert "a\tb" in result.output
        assert "1\t2" in result.output
        fetch_mock.assert_called_once_with("sid", "Sheet1!A1:B2", profile=None)

    def test_sheets_write_passes_rows(self, monkeypatch):
        write_mock = MagicMock(return_value=4)
        monkeypatch.setattr(cli_module, "write_values", write_mock)

        result = CliRunner().invoke(
            cli_module.cli,
            [
                "sheets",
                "write",
                "sid",
                "Sheet1!A1:B2",
                "--row",
                "a,b",
                "--row",
                "1,2",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Updated cells: 4" in result.output
        write_mock.assert_called_once_with(
            "sid", "Sheet1!A1:B2", [["a", "b"], ["1", "2"]], raw=False, profile=None
        )

    def test_sheets_create_prints_id_and_url(self, monkeypatch):
        from mgdio.sheets.spreadsheets import Spreadsheet

        new_sheet = Spreadsheet(
            id="new-sid",
            title="Demo",
            url="https://docs.google.com/spreadsheets/d/new-sid/edit",
            tabs=(),
            time_zone="UTC",
            locale="en_US",
        )
        create_mock = MagicMock(return_value=new_sheet)
        monkeypatch.setattr(cli_module, "create_spreadsheet", create_mock)

        result = CliRunner().invoke(
            cli_module.cli,
            ["sheets", "create", "--title", "Demo", "--tab", "Alpha", "--tab", "Beta"],
        )

        assert result.exit_code == 0, result.output
        assert "new-sid" in result.output
        assert "new-sid/edit" in result.output
        create_mock.assert_called_once_with(
            "Demo", sheet_names=["Alpha", "Beta"], profile=None
        )


def _sample_event_for_cli(**overrides):
    from datetime import datetime, timezone

    from mgdio.calendar import CalendarEvent

    defaults = dict(
        id="evt-1",
        calendar_id="primary",
        summary="Lunch",
        description="",
        location="",
        start=datetime(2026, 5, 12, 12, tzinfo=timezone.utc),
        end=datetime(2026, 5, 12, 13, tzinfo=timezone.utc),
        all_day=False,
        attendees=(),
        creator="me@example.com",
        organizer="me@example.com",
        html_link="https://www.google.com/calendar/event?eid=abc",
        status="confirmed",
        created=datetime(2026, 5, 9, tzinfo=timezone.utc),
        updated=datetime(2026, 5, 9, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return CalendarEvent(**defaults)


class TestCalendarCommands:
    def test_help_lists_subcommands(self):
        result = CliRunner().invoke(cli_module.cli, ["calendar", "--help"])
        assert result.exit_code == 0
        for name in (
            "list-cals",
            "list-events",
            "get",
            "create",
            "update",
            "delete",
            "quick-add",
        ):
            assert name in result.output

    def test_list_events_invokes_fetch_events(self, monkeypatch):
        fetch_mock = MagicMock(return_value=[_sample_event_for_cli()])
        monkeypatch.setattr(cli_module, "fetch_events", fetch_mock)

        result = CliRunner().invoke(
            cli_module.cli, ["calendar", "list-events", "--max", "3"]
        )

        assert result.exit_code == 0, result.output
        assert "Lunch" in result.output
        assert "evt-1" in result.output
        kwargs = fetch_mock.call_args.kwargs
        assert kwargs["calendar_id"] == "primary"
        assert kwargs["max_results"] == 3
        assert kwargs["time_min"] is None
        assert kwargs["time_max"] is None

    def test_list_events_passes_aware_time_bounds(self, monkeypatch):
        fetch_mock = MagicMock(return_value=[])
        monkeypatch.setattr(cli_module, "fetch_events", fetch_mock)

        result = CliRunner().invoke(
            cli_module.cli,
            [
                "calendar",
                "list-events",
                "--time-min",
                "2026-05-09T00:00:00-04:00",
                "--time-max",
                "2026-05-16T00:00:00-04:00",
            ],
        )

        assert result.exit_code == 0, result.output
        kwargs = fetch_mock.call_args.kwargs
        assert kwargs["time_min"] is not None
        assert kwargs["time_min"].tzinfo is not None
        assert kwargs["time_max"] is not None

    def test_list_events_rejects_naive_time_bound(self):
        result = CliRunner().invoke(
            cli_module.cli,
            ["calendar", "list-events", "--time-min", "2026-05-09T00:00:00"],
        )
        assert result.exit_code != 0
        assert "timezone offset" in result.output.lower()

    def test_create_invokes_create_event(self, monkeypatch):
        create_mock = MagicMock(return_value=_sample_event_for_cli())
        monkeypatch.setattr(cli_module, "create_event", create_mock)

        result = CliRunner().invoke(
            cli_module.cli,
            [
                "calendar",
                "create",
                "--summary",
                "Lunch",
                "--start",
                "2026-05-12T12:00:00-04:00",
                "--end",
                "2026-05-12T13:00:00-04:00",
                "--attendee",
                "bob@example.com",
                "--attendee",
                "alice@example.com",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Created:" in result.output
        kwargs = create_mock.call_args.kwargs
        assert kwargs["summary"] == "Lunch"
        assert kwargs["attendees"] == ["bob@example.com", "alice@example.com"]
        assert kwargs["start"].tzinfo is not None
        assert kwargs["all_day"] is False

    def test_delete_invokes_delete_event(self, monkeypatch):
        delete_mock = MagicMock()
        monkeypatch.setattr(cli_module, "delete_event", delete_mock)

        result = CliRunner().invoke(cli_module.cli, ["calendar", "delete", "evt-1"])

        assert result.exit_code == 0, result.output
        assert "Deleted." in result.output
        delete_mock.assert_called_once_with(
            "evt-1", calendar_id="primary", profile=None
        )

    def test_quick_add_invokes_quick_add(self, monkeypatch):
        quick_mock = MagicMock(return_value=_sample_event_for_cli())
        monkeypatch.setattr(cli_module, "quick_add", quick_mock)

        result = CliRunner().invoke(
            cli_module.cli,
            ["calendar", "quick-add", "Lunch with Bob Tuesday 12pm"],
        )

        assert result.exit_code == 0, result.output
        quick_mock.assert_called_once_with(
            "Lunch with Bob Tuesday 12pm", calendar_id="primary", profile=None
        )


def _sample_budget_for_cli(**overrides):
    from datetime import datetime, timezone

    from mgdio.ynab import Budget

    defaults = dict(
        id="b-1",
        name="Personal",
        last_modified_on=datetime(2026, 5, 8, tzinfo=timezone.utc),
        first_month="2024-01-01",
        last_month="2026-12-01",
        currency_iso_code="USD",
        currency_symbol="$",
        decimal_digits=2,
    )
    defaults.update(overrides)
    return Budget(**defaults)


def _sample_account_for_cli(**overrides):
    from mgdio.ynab import Account

    defaults = dict(
        id="acct-1",
        name="Checking",
        type="checking",
        on_budget=True,
        closed=False,
        balance_milliunits=12340,
        cleared_balance_milliunits=12000,
        uncleared_balance_milliunits=340,
        deleted=False,
    )
    defaults.update(overrides)
    return Account(**defaults)


def _sample_transaction_for_cli(**overrides):
    from mgdio.ynab import Transaction

    defaults = dict(
        id="tx-1",
        date="2026-05-08",
        amount_milliunits=-12340,
        memo="lunch",
        cleared="uncleared",
        approved=True,
        flag_color="",
        account_id="acct-1",
        account_name="Checking",
        payee_id="payee-1",
        payee_name="Bistro",
        category_id="cat-1",
        category_name="Restaurants",
        transfer_account_id="",
        deleted=False,
    )
    defaults.update(overrides)
    return Transaction(**defaults)


class TestYnabCommands:
    def test_help_lists_subcommands(self):
        result = CliRunner().invoke(cli_module.cli, ["ynab", "--help"])
        assert result.exit_code == 0
        for name in ("budgets", "accounts", "categories", "transactions", "update-tx"):
            assert name in result.output

    def test_budgets_prints_one_per_line(self, monkeypatch):
        fetch_mock = MagicMock(return_value=[_sample_budget_for_cli()])
        monkeypatch.setattr(cli_module, "fetch_budgets", fetch_mock)

        result = CliRunner().invoke(cli_module.cli, ["ynab", "budgets"])

        assert result.exit_code == 0, result.output
        assert "Personal" in result.output
        assert "b-1" in result.output
        fetch_mock.assert_called_once_with()

    def test_accounts_invokes_fetch_accounts(self, monkeypatch):
        fetch_mock = MagicMock(return_value=[_sample_account_for_cli()])
        monkeypatch.setattr(cli_module, "fetch_accounts", fetch_mock)

        result = CliRunner().invoke(
            cli_module.cli, ["ynab", "accounts", "--budget", "b-1"]
        )

        assert result.exit_code == 0, result.output
        assert "Checking" in result.output
        assert "12.34" in result.output
        fetch_mock.assert_called_once_with(budget_id="b-1")

    def test_transactions_invokes_fetch_transactions(self, monkeypatch):
        fetch_mock = MagicMock(return_value=[_sample_transaction_for_cli()])
        monkeypatch.setattr(cli_module, "fetch_transactions", fetch_mock)

        result = CliRunner().invoke(
            cli_module.cli,
            [
                "ynab",
                "transactions",
                "--budget",
                "b-1",
                "--since",
                "2026-04-01",
                "--account",
                "acct-1",
                "--max",
                "10",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Bistro" in result.output
        kwargs = fetch_mock.call_args.kwargs
        assert kwargs["budget_id"] == "b-1"
        assert kwargs["since_date"] == "2026-04-01"
        assert kwargs["account_id"] == "acct-1"

    def test_update_tx_with_memo(self, monkeypatch):
        update_mock = MagicMock(
            return_value=_sample_transaction_for_cli(memo="new memo")
        )
        monkeypatch.setattr(cli_module, "update_transaction", update_mock)

        result = CliRunner().invoke(
            cli_module.cli,
            ["ynab", "update-tx", "tx-1", "--memo", "new memo"],
        )

        assert result.exit_code == 0, result.output
        assert "new memo" in result.output
        kwargs = update_mock.call_args.kwargs
        assert kwargs["memo"] == "new memo"
        assert kwargs["budget_id"] == "last-used"

    def test_update_tx_with_clear_memo_passes_sentinel(self, monkeypatch):
        from mgdio.ynab import CLEAR as YNAB_CLEAR

        update_mock = MagicMock(return_value=_sample_transaction_for_cli(memo=""))
        monkeypatch.setattr(cli_module, "update_transaction", update_mock)

        result = CliRunner().invoke(
            cli_module.cli,
            ["ynab", "update-tx", "tx-1", "--clear-memo"],
        )

        assert result.exit_code == 0, result.output
        kwargs = update_mock.call_args.kwargs
        assert kwargs["memo"] is YNAB_CLEAR

    def test_update_tx_rejects_both_memo_and_clear_memo(self, monkeypatch):
        update_mock = MagicMock()
        monkeypatch.setattr(cli_module, "update_transaction", update_mock)

        result = CliRunner().invoke(
            cli_module.cli,
            [
                "ynab",
                "update-tx",
                "tx-1",
                "--memo",
                "new",
                "--clear-memo",
            ],
        )

        assert result.exit_code != 0
        assert "not both" in result.output.lower()
        update_mock.assert_not_called()


class TestWhoopCommands:
    def test_help_lists_subcommands(self):
        result = CliRunner().invoke(cli_module.cli, ["whoop", "--help"])
        assert result.exit_code == 0
        for name in ("recoveries", "sleeps", "workouts", "cycles", "profile", "body"):
            assert name in result.output

    def test_recoveries_invokes_fetch(self, monkeypatch):
        from datetime import datetime, timezone

        from mgdio.whoop import Recovery

        sample = Recovery(
            cycle_id=1,
            sleep_id="s",
            user_id=2,
            created_at=datetime(2026, 5, 12, tzinfo=timezone.utc),
            updated_at=datetime(2026, 5, 12, tzinfo=timezone.utc),
            score_state="SCORED",
            recovery_score=67,
            resting_heart_rate=52,
            hrv_rmssd_milli=48.5,
            spo2_percentage=96.0,
            skin_temp_celsius=33.2,
            user_calibrating=False,
        )
        fetch = MagicMock(return_value=[sample])
        monkeypatch.setattr(cli_module, "fetch_recoveries", fetch)

        result = CliRunner().invoke(
            cli_module.cli, ["whoop", "recoveries", "--max", "3"]
        )

        assert result.exit_code == 0, result.output
        assert "67%" in result.output
        kwargs = fetch.call_args.kwargs
        assert kwargs["max_records"] == 3
        assert kwargs["start"] is None

    def test_recoveries_rejects_naive_start(self, monkeypatch):
        monkeypatch.setattr(cli_module, "fetch_recoveries", MagicMock(return_value=[]))
        result = CliRunner().invoke(
            cli_module.cli, ["whoop", "recoveries", "--start", "2026-05-01T00:00:00"]
        )
        assert result.exit_code != 0
        assert "timezone offset" in result.output.lower()

    def test_profile_invokes_fetch(self, monkeypatch):
        from mgdio.whoop import Profile

        fetch = MagicMock(
            return_value=Profile(
                user_id=10, email="a@b.c", first_name="A", last_name="B"
            )
        )
        monkeypatch.setattr(cli_module, "fetch_profile", fetch)

        result = CliRunner().invoke(cli_module.cli, ["whoop", "profile"])

        assert result.exit_code == 0, result.output
        assert "a@b.c" in result.output
        fetch.assert_called_once()


def _sample_drive_file(**overrides):
    from datetime import datetime, timezone

    from mgdio.drive import DriveFile

    defaults = dict(
        id="f-1",
        name="report.pdf",
        mime_type="application/pdf",
        parents=("parent-1",),
        size_bytes=20480,
        created_time=datetime(2026, 5, 1, tzinfo=timezone.utc),
        modified_time=datetime(2026, 5, 12, tzinfo=timezone.utc),
        web_view_link="https://drive.google.com/file/d/f-1/view",
        web_content_link="",
        trashed=False,
        starred=True,
        shared=False,
        md5_checksum="abc",
        file_extension="pdf",
        icon_link="",
        owner_emails=("me@example.com",),
    )
    defaults.update(overrides)
    return DriveFile(**defaults)


class TestDriveCommands:
    def test_help_lists_subcommands(self):
        result = CliRunner().invoke(cli_module.cli, ["drive", "--help"])
        assert result.exit_code == 0
        for name in (
            "list",
            "get",
            "mkdir",
            "upload",
            "download",
            "export",
            "rename",
            "move",
            "copy",
            "trash",
            "delete",
            "share",
            "perms",
            "unshare",
        ):
            assert name in result.output

    def test_list_invokes_list_files(self, monkeypatch):
        fetch = MagicMock(return_value=[_sample_drive_file()])
        monkeypatch.setattr(cli_module, "list_files", fetch)

        result = CliRunner().invoke(
            cli_module.cli,
            ["drive", "list", "--query", "name contains 'r'", "--max", "5"],
        )

        assert result.exit_code == 0, result.output
        assert "report.pdf" in result.output
        assert "f-1" in result.output
        kwargs = fetch.call_args.kwargs
        assert kwargs["query"] == "name contains 'r'"
        assert kwargs["max_results"] == 5

    def test_get_prints_metadata(self, monkeypatch):
        fetch = MagicMock(return_value=_sample_drive_file())
        monkeypatch.setattr(cli_module, "fetch_file", fetch)

        result = CliRunner().invoke(cli_module.cli, ["drive", "get", "f-1"])

        assert result.exit_code == 0, result.output
        assert "report.pdf" in result.output
        assert "me@example.com" in result.output
        fetch.assert_called_once_with("f-1", profile=None)

    def test_mkdir_invokes_create_folder(self, monkeypatch):
        from mgdio.drive import FOLDER_MIME_TYPE

        create = MagicMock(
            return_value=_sample_drive_file(
                name="New", mime_type=FOLDER_MIME_TYPE, size_bytes=None
            )
        )
        monkeypatch.setattr(cli_module, "create_folder", create)

        result = CliRunner().invoke(
            cli_module.cli, ["drive", "mkdir", "New", "--parent", "root-1"]
        )

        assert result.exit_code == 0, result.output
        create.assert_called_once_with("New", parent_id="root-1", profile=None)

    def test_share_invokes_share_file(self, monkeypatch):
        from mgdio.drive import Permission

        share = MagicMock(
            return_value=Permission(
                id="perm-1",
                type="user",
                role="writer",
                email_address="bob@example.com",
                domain="",
                display_name="Bob",
            )
        )
        monkeypatch.setattr(cli_module, "share_file", share)

        result = CliRunner().invoke(
            cli_module.cli,
            ["drive", "share", "f-1", "--role", "writer", "--email", "bob@example.com"],
        )

        assert result.exit_code == 0, result.output
        assert "perm-1" in result.output
        kwargs = share.call_args.kwargs
        assert kwargs["role"] == "writer"
        assert kwargs["email"] == "bob@example.com"

    def test_delete_invokes_delete_file(self, monkeypatch):
        delete = MagicMock()
        monkeypatch.setattr(cli_module, "delete_file", delete)

        result = CliRunner().invoke(cli_module.cli, ["drive", "delete", "f-1"])

        assert result.exit_code == 0, result.output
        assert "Deleted." in result.output
        delete.assert_called_once_with("f-1", profile=None)


class TestAuthMaps:
    def test_runs_get_api_key_and_prints_authenticated(self, monkeypatch):
        get_key = MagicMock()
        clear = MagicMock()
        monkeypatch.setattr(cli_module, "get_maps_key", get_key)
        monkeypatch.setattr(cli_module, "clear_maps_key", clear)

        result = CliRunner().invoke(cli_module.cli, ["auth", "maps"])

        assert result.exit_code == 0, result.output
        assert "Authenticated." in result.output
        get_key.assert_called_once()
        clear.assert_not_called()

    def test_reset_clears_before_get_key(self, monkeypatch):
        parent = MagicMock()
        monkeypatch.setattr(cli_module, "clear_maps_key", parent.clear)
        monkeypatch.setattr(cli_module, "get_maps_key", parent.get)

        result = CliRunner().invoke(cli_module.cli, ["auth", "maps", "--reset"])

        assert result.exit_code == 0, result.output
        assert [c[0] for c in parent.mock_calls] == ["clear", "get"]

    def test_headless_flag_passes_through(self, monkeypatch):
        get_key = MagicMock()
        monkeypatch.setattr(cli_module, "get_maps_key", get_key)
        monkeypatch.setattr(cli_module, "clear_maps_key", MagicMock())

        result = CliRunner().invoke(cli_module.cli, ["auth", "maps", "--headless"])

        assert result.exit_code == 0, result.output
        get_key.assert_called_once_with(headless=True)


def _sample_geocode_result():
    from mgdio.maps import GeocodeResult

    return GeocodeResult(
        formatted_address="New York, NY, USA",
        latitude=40.7127753,
        longitude=-74.0059728,
        location_type="APPROXIMATE",
        place_id="ChIJ123",
        types=("locality",),
    )


def _sample_route():
    from mgdio.maps import Route, RouteStep

    return Route(
        distance_meters=8368,
        distance_text="5.2 mi",
        duration_seconds=720,
        duration_text="12 mins",
        start_address="New York, NY",
        end_address="Hoboken, NJ",
        summary="I-95 S",
        steps=(
            RouteStep(
                instruction="Head north on Broadway",
                distance_meters=161,
                distance_text="0.1 mi",
                duration_seconds=60,
                duration_text="1 min",
                travel_mode="DRIVING",
            ),
        ),
    )


class TestMapsCommands:
    def test_maps_help_lists_subcommands(self):
        result = CliRunner().invoke(cli_module.cli, ["maps", "--help"])
        assert result.exit_code == 0
        for name in ("geocode", "reverse", "distance", "duration", "directions"):
            assert name in result.output

    def test_geocode_prints_address_and_latlng(self, monkeypatch):
        geo = MagicMock(return_value=[_sample_geocode_result()])
        monkeypatch.setattr(cli_module, "geocode", geo)

        result = CliRunner().invoke(cli_module.cli, ["maps", "geocode", "New York"])

        assert result.exit_code == 0, result.output
        assert "New York, NY, USA" in result.output
        assert "40.7127753, -74.0059728" in result.output
        geo.assert_called_once_with("New York")

    def test_geocode_no_match(self, monkeypatch):
        monkeypatch.setattr(cli_module, "geocode", MagicMock(return_value=[]))
        result = CliRunner().invoke(cli_module.cli, ["maps", "geocode", "xyz"])
        assert result.exit_code == 0, result.output
        assert "No match" in result.output

    def test_reverse_prints_address(self, monkeypatch):
        rev = MagicMock(return_value=[_sample_geocode_result()])
        monkeypatch.setattr(cli_module, "reverse_geocode", rev)

        result = CliRunner().invoke(
            cli_module.cli, ["maps", "reverse", "40.714,-74.006"]
        )

        assert result.exit_code == 0, result.output
        assert "New York, NY, USA" in result.output
        rev.assert_called_once_with(40.714, -74.006)

    def test_distance_prints_text(self, monkeypatch):
        route = MagicMock(return_value=_sample_route())
        monkeypatch.setattr(cli_module, "fetch_route", route)

        result = CliRunner().invoke(
            cli_module.cli, ["maps", "distance", "NY 10005", "Hoboken NJ"]
        )

        assert result.exit_code == 0, result.output
        assert "5.2 mi" in result.output
        kwargs = route.call_args.kwargs
        assert kwargs["mode"] == "driving"
        assert kwargs["units"] == "imperial"

    def test_duration_prints_text(self, monkeypatch):
        route = MagicMock(return_value=_sample_route())
        monkeypatch.setattr(cli_module, "fetch_route", route)

        result = CliRunner().invoke(
            cli_module.cli,
            ["maps", "duration", "NY", "Hoboken", "--mode", "walking"],
        )

        assert result.exit_code == 0, result.output
        assert "12 mins" in result.output
        assert route.call_args.kwargs["mode"] == "walking"

    def test_directions_prints_steps(self, monkeypatch):
        route = MagicMock(return_value=_sample_route())
        monkeypatch.setattr(cli_module, "fetch_route", route)

        result = CliRunner().invoke(
            cli_module.cli, ["maps", "directions", "NY", "Hoboken"]
        )

        assert result.exit_code == 0, result.output
        assert "Head north on Broadway" in result.output
        assert "5.2 mi, 12 mins" in result.output


class TestMainEntryPoint:
    def test_mgdio_errors_print_one_line_message_not_traceback(
        self, monkeypatch, capsys
    ):
        from mgdio.exceptions import MgdioKeyringError

        boom = MagicMock(side_effect=MgdioKeyringError("vault refused; run X"))
        monkeypatch.setattr(cli_module, "cli", boom)

        with pytest.raises(SystemExit) as excinfo:
            cli_module.main()

        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "error: vault refused; run X" in captured.err
        assert "Traceback" not in captured.err

    def test_click_usage_errors_pass_through(self, monkeypatch):
        import sys

        monkeypatch.setattr(sys, "argv", ["mgdio", "not-a-command"])

        with pytest.raises(SystemExit) as excinfo:
            cli_module.main()

        assert excinfo.value.code == 2


class TestAuthWhoopHeadless:
    def test_headless_flag_passes_through(self, monkeypatch):
        get_tok = MagicMock()
        monkeypatch.setattr(cli_module, "get_whoop_token", get_tok)

        result = CliRunner().invoke(cli_module.cli, ["auth", "whoop", "--headless"])

        assert result.exit_code == 0, result.output
        assert get_tok.call_args.kwargs["headless"] is True

    def test_default_is_not_headless(self, monkeypatch):
        get_tok = MagicMock()
        monkeypatch.setattr(cli_module, "get_whoop_token", get_tok)

        result = CliRunner().invoke(cli_module.cli, ["auth", "whoop"])

        assert result.exit_code == 0, result.output
        assert get_tok.call_args.kwargs["headless"] is False
