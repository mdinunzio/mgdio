"""Unit tests for ``mgdio.calendar.events``."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from mgdio.calendar import events as events_mod
from mgdio.calendar.events import CLEAR
from mgdio.exceptions import MgdioAPIError


def _events_call(service):
    return service.events.return_value


def _sample_event_raw(
    *,
    id_: str = "evt-1",
    summary: str = "Lunch",
    start_dt: str = "2026-05-12T12:00:00-04:00",
    end_dt: str = "2026-05-12T13:00:00-04:00",
) -> dict:
    return {
        "id": id_,
        "summary": summary,
        "description": "with Bob",
        "location": "Cafe",
        "start": {"dateTime": start_dt, "timeZone": "America/New_York"},
        "end": {"dateTime": end_dt, "timeZone": "America/New_York"},
        "attendees": [{"email": "bob@example.com"}, {"email": "me@example.com"}],
        "creator": {"email": "me@example.com"},
        "organizer": {"email": "me@example.com"},
        "htmlLink": "https://www.google.com/calendar/event?eid=abc",
        "status": "confirmed",
        "created": "2026-05-09T10:00:00.000Z",
        "updated": "2026-05-09T10:05:00.000Z",
    }


def _sample_all_day_raw() -> dict:
    return {
        "id": "evt-allday",
        "summary": "Holiday",
        "description": "",
        "location": "",
        "start": {"date": "2026-07-04"},
        "end": {"date": "2026-07-05"},
        "creator": {"email": "me@example.com"},
        "organizer": {"email": "me@example.com"},
        "htmlLink": "https://www.google.com/calendar/event?eid=def",
        "status": "confirmed",
        "created": "2026-05-09T10:00:00Z",
        "updated": "2026-05-09T10:00:00Z",
    }


class TestFetchEvents:
    def test_passes_params_and_returns_dataclasses(self, mock_calendar_service):
        _events_call(mock_calendar_service).list.return_value.execute.return_value = {
            "items": [_sample_event_raw()]
        }

        result = events_mod.fetch_events(
            "primary",
            time_min=datetime(2026, 5, 1, tzinfo=timezone.utc),
            time_max=datetime(2026, 6, 1, tzinfo=timezone.utc),
            query="lunch",
            max_results=20,
        )

        assert len(result) == 1
        assert result[0].id == "evt-1"
        assert result[0].calendar_id == "primary"
        kwargs = _events_call(mock_calendar_service).list.call_args.kwargs
        assert kwargs["calendarId"] == "primary"
        assert kwargs["maxResults"] == 20
        assert kwargs["singleEvents"] is True
        assert kwargs["orderBy"] == "startTime"
        assert kwargs["q"] == "lunch"
        assert kwargs["timeMin"] == "2026-05-01T00:00:00+00:00"
        assert kwargs["timeMax"] == "2026-06-01T00:00:00+00:00"

    def test_uses_updated_orderby_when_single_events_false(self, mock_calendar_service):
        _events_call(mock_calendar_service).list.return_value.execute.return_value = {}
        events_mod.fetch_events(single_events=False)
        kwargs = _events_call(mock_calendar_service).list.call_args.kwargs
        assert kwargs["orderBy"] == "updated"
        assert kwargs["singleEvents"] is False

    def test_omits_q_and_time_bounds_when_unset(self, mock_calendar_service):
        _events_call(mock_calendar_service).list.return_value.execute.return_value = {}
        events_mod.fetch_events()
        kwargs = _events_call(mock_calendar_service).list.call_args.kwargs
        assert "q" not in kwargs
        assert "timeMin" not in kwargs
        assert "timeMax" not in kwargs

    def test_rejects_naive_time_min(self, mock_calendar_service):
        with pytest.raises(ValueError, match="time_min"):
            events_mod.fetch_events(time_min=datetime(2026, 5, 1))

    def test_rejects_naive_time_max(self, mock_calendar_service):
        with pytest.raises(ValueError, match="time_max"):
            events_mod.fetch_events(time_max=datetime(2026, 5, 1))

    def test_wraps_http_error(self, mock_calendar_service):
        _events_call(mock_calendar_service).list.return_value.execute.side_effect = (
            HttpError(resp=MagicMock(status=500, reason="boom"), content=b"err")
        )
        with pytest.raises(MgdioAPIError):
            events_mod.fetch_events()


class TestFetchEvent:
    def test_happy_path(self, mock_calendar_service):
        _events_call(mock_calendar_service).get.return_value.execute.return_value = (
            _sample_event_raw()
        )
        ev = events_mod.fetch_event("evt-1", calendar_id="cal-x")
        assert ev.id == "evt-1"
        assert ev.calendar_id == "cal-x"
        kwargs = _events_call(mock_calendar_service).get.call_args.kwargs
        assert kwargs == {"calendarId": "cal-x", "eventId": "evt-1"}

    def test_wraps_http_error(self, mock_calendar_service):
        _events_call(mock_calendar_service).get.return_value.execute.side_effect = (
            HttpError(resp=MagicMock(status=404, reason="nope"), content=b"err")
        )
        with pytest.raises(MgdioAPIError):
            events_mod.fetch_event("evt-1")


class TestToEvent:
    def test_parses_timed_event(self):
        ev = events_mod._to_event(_sample_event_raw(), "primary")
        assert ev.summary == "Lunch"
        assert ev.description == "with Bob"
        assert ev.location == "Cafe"
        assert ev.all_day is False
        assert ev.start.year == 2026 and ev.start.tzinfo is not None
        assert ev.attendees == ("bob@example.com", "me@example.com")
        assert ev.creator == "me@example.com"
        assert ev.organizer == "me@example.com"
        assert ev.html_link.startswith("https://")
        assert ev.created.tzinfo is not None
        assert ev.updated.tzinfo is not None

    def test_parses_all_day_event_with_utc_midnight(self):
        ev = events_mod._to_event(_sample_all_day_raw(), "primary")
        assert ev.all_day is True
        assert ev.start == datetime(2026, 7, 4, tzinfo=timezone.utc)
        assert ev.end == datetime(2026, 7, 5, tzinfo=timezone.utc)
        assert ev.attendees == ()

    def test_missing_optional_fields_default_to_empty_string(self):
        minimal = {
            "id": "x",
            "start": {"dateTime": "2026-05-12T12:00:00Z"},
            "end": {"dateTime": "2026-05-12T13:00:00Z"},
        }
        ev = events_mod._to_event(minimal, "primary")
        assert ev.summary == ""
        assert ev.location == ""
        assert ev.creator == ""
        assert ev.attendees == ()


class TestCreateEvent:
    def test_builds_timed_body(self, mock_calendar_service):
        _events_call(mock_calendar_service).insert.return_value.execute.return_value = (
            _sample_event_raw()
        )

        start = datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc)
        end = datetime(2026, 5, 12, 13, 0, tzinfo=timezone.utc)
        result = events_mod.create_event(
            "Lunch",
            start,
            end,
            description="with Bob",
            location="Cafe",
            attendees=["bob@example.com"],
        )

        assert result.id == "evt-1"
        body = _events_call(mock_calendar_service).insert.call_args.kwargs["body"]
        assert body["summary"] == "Lunch"
        assert body["description"] == "with Bob"
        assert body["location"] == "Cafe"
        assert body["start"]["dateTime"] == "2026-05-12T12:00:00+00:00"
        assert body["start"]["timeZone"] == "UTC"
        assert body["end"]["dateTime"] == "2026-05-12T13:00:00+00:00"
        assert body["attendees"] == [{"email": "bob@example.com"}]

    def test_builds_all_day_body(self, mock_calendar_service):
        _events_call(mock_calendar_service).insert.return_value.execute.return_value = (
            _sample_all_day_raw()
        )

        start = datetime(2026, 7, 4, tzinfo=timezone.utc)
        end = datetime(2026, 7, 5, tzinfo=timezone.utc)
        events_mod.create_event("Holiday", start, end, all_day=True)

        body = _events_call(mock_calendar_service).insert.call_args.kwargs["body"]
        assert body["start"] == {"date": "2026-07-04"}
        assert body["end"] == {"date": "2026-07-05"}
        assert "description" not in body
        assert "attendees" not in body

    def test_rejects_naive_start(self, mock_calendar_service):
        with pytest.raises(ValueError, match="start"):
            events_mod.create_event(
                "X",
                datetime(2026, 5, 12, 12),
                datetime(2026, 5, 12, 13, tzinfo=timezone.utc),
            )

    def test_rejects_naive_end(self, mock_calendar_service):
        with pytest.raises(ValueError, match="end"):
            events_mod.create_event(
                "X",
                datetime(2026, 5, 12, 12, tzinfo=timezone.utc),
                datetime(2026, 5, 12, 13),
            )

    def test_wraps_http_error(self, mock_calendar_service):
        _events_call(mock_calendar_service).insert.return_value.execute.side_effect = (
            HttpError(resp=MagicMock(status=500, reason="boom"), content=b"err")
        )
        with pytest.raises(MgdioAPIError):
            events_mod.create_event(
                "x",
                datetime(2026, 5, 12, 12, tzinfo=timezone.utc),
                datetime(2026, 5, 12, 13, tzinfo=timezone.utc),
            )


class TestUpdateEvent:
    def test_only_sends_provided_fields(self, mock_calendar_service):
        _events_call(mock_calendar_service).patch.return_value.execute.return_value = (
            _sample_event_raw()
        )

        events_mod.update_event("evt-1", summary="New Title")

        body = _events_call(mock_calendar_service).patch.call_args.kwargs["body"]
        assert body == {"summary": "New Title"}

    def test_clear_sentinel_emits_null(self, mock_calendar_service):
        _events_call(mock_calendar_service).patch.return_value.execute.return_value = (
            _sample_event_raw()
        )

        events_mod.update_event("evt-1", description=CLEAR, location=CLEAR)

        body = _events_call(mock_calendar_service).patch.call_args.kwargs["body"]
        assert body == {"description": None, "location": None}

    def test_attendees_clear_emits_empty_list(self, mock_calendar_service):
        _events_call(mock_calendar_service).patch.return_value.execute.return_value = (
            _sample_event_raw()
        )

        events_mod.update_event("evt-1", attendees=CLEAR)

        body = _events_call(mock_calendar_service).patch.call_args.kwargs["body"]
        assert body == {"attendees": []}

    def test_attendees_set_wraps_emails_in_dicts(self, mock_calendar_service):
        _events_call(mock_calendar_service).patch.return_value.execute.return_value = (
            _sample_event_raw()
        )

        events_mod.update_event("evt-1", attendees=["a@example.com", "b@example.com"])

        body = _events_call(mock_calendar_service).patch.call_args.kwargs["body"]
        assert body == {
            "attendees": [{"email": "a@example.com"}, {"email": "b@example.com"}]
        }

    def test_start_end_send_formatted_endpoints(self, mock_calendar_service):
        _events_call(mock_calendar_service).patch.return_value.execute.return_value = (
            _sample_event_raw()
        )

        events_mod.update_event(
            "evt-1",
            start=datetime(2026, 5, 12, 12, tzinfo=timezone.utc),
            end=datetime(2026, 5, 12, 13, tzinfo=timezone.utc),
        )

        body = _events_call(mock_calendar_service).patch.call_args.kwargs["body"]
        assert body["start"]["dateTime"] == "2026-05-12T12:00:00+00:00"
        assert body["end"]["dateTime"] == "2026-05-12T13:00:00+00:00"

    def test_rejects_naive_start_when_provided(self, mock_calendar_service):
        with pytest.raises(ValueError, match="start"):
            events_mod.update_event("evt-1", start=datetime(2026, 5, 12, 12))

    def test_noop_when_no_fields_provided(self, mock_calendar_service):
        _events_call(mock_calendar_service).patch.return_value.execute.return_value = (
            _sample_event_raw()
        )

        events_mod.update_event("evt-1")

        body = _events_call(mock_calendar_service).patch.call_args.kwargs["body"]
        assert body == {}

    def test_wraps_http_error(self, mock_calendar_service):
        _events_call(mock_calendar_service).patch.return_value.execute.side_effect = (
            HttpError(resp=MagicMock(status=500, reason="boom"), content=b"err")
        )
        with pytest.raises(MgdioAPIError):
            events_mod.update_event("evt-1", summary="x")


class TestDeleteEvent:
    def test_calls_delete(self, mock_calendar_service):
        _events_call(mock_calendar_service).delete.return_value.execute.return_value = (
            ""
        )
        events_mod.delete_event("evt-1", calendar_id="cal-x")
        kwargs = _events_call(mock_calendar_service).delete.call_args.kwargs
        assert kwargs == {"calendarId": "cal-x", "eventId": "evt-1"}

    def test_wraps_http_error(self, mock_calendar_service):
        _events_call(mock_calendar_service).delete.return_value.execute.side_effect = (
            HttpError(resp=MagicMock(status=500, reason="boom"), content=b"err")
        )
        with pytest.raises(MgdioAPIError):
            events_mod.delete_event("evt-1")


class TestQuickAdd:
    def test_calls_quick_add_with_text(self, mock_calendar_service):
        _events_call(
            mock_calendar_service
        ).quickAdd.return_value.execute.return_value = _sample_event_raw()

        ev = events_mod.quick_add("Lunch with Bob Tuesday 12pm")

        assert ev.id == "evt-1"
        kwargs = _events_call(mock_calendar_service).quickAdd.call_args.kwargs
        assert kwargs == {
            "calendarId": "primary",
            "text": "Lunch with Bob Tuesday 12pm",
        }

    def test_wraps_http_error(self, mock_calendar_service):
        _events_call(
            mock_calendar_service
        ).quickAdd.return_value.execute.side_effect = HttpError(
            resp=MagicMock(status=500, reason="boom"), content=b"err"
        )
        with pytest.raises(MgdioAPIError):
            events_mod.quick_add("x")


class TestClearSingleton:
    def test_clear_is_singleton(self):
        from mgdio.calendar.events import _ClearType

        assert _ClearType() is CLEAR
        assert _ClearType() is _ClearType()
        assert repr(CLEAR) == "CLEAR"
