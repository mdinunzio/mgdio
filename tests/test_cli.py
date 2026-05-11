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
    def test_top_level_help_lists_groups(self):
        result = CliRunner().invoke(cli_module.cli, ["--help"])
        assert result.exit_code == 0
        assert "auth" in result.output
        assert "gmail" in result.output
        assert "sheets" in result.output
        assert "calendar" in result.output

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
        fetch_mock.assert_called_once_with("sid", "Sheet1!A1:B2")

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
            "sid", "Sheet1!A1:B2", [["a", "b"], ["1", "2"]], raw=False
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
        create_mock.assert_called_once_with("Demo", sheet_names=["Alpha", "Beta"])


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
        delete_mock.assert_called_once_with("evt-1", calendar_id="primary")

    def test_quick_add_invokes_quick_add(self, monkeypatch):
        quick_mock = MagicMock(return_value=_sample_event_for_cli())
        monkeypatch.setattr(cli_module, "quick_add", quick_mock)

        result = CliRunner().invoke(
            cli_module.cli,
            ["calendar", "quick-add", "Lunch with Bob Tuesday 12pm"],
        )

        assert result.exit_code == 0, result.output
        quick_mock.assert_called_once_with(
            "Lunch with Bob Tuesday 12pm", calendar_id="primary"
        )
