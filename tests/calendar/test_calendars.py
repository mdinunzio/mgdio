"""Unit tests for ``mgdio.calendar.calendars``."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from mgdio.calendar import calendars as cal_mod
from mgdio.exceptions import MgdioAPIError


def _list_call(service):
    return service.calendarList.return_value.list.return_value


class TestFetchCalendars:
    def test_maps_response_to_dataclasses(self, mock_calendar_service):
        _list_call(mock_calendar_service).execute.return_value = {
            "items": [
                {
                    "id": "primary",
                    "summary": "Me",
                    "description": "",
                    "timeZone": "America/New_York",
                    "primary": True,
                    "accessRole": "owner",
                },
                {
                    "id": "team@group.calendar.google.com",
                    "summary": "Team",
                    "description": "Shared",
                    "timeZone": "UTC",
                    "accessRole": "writer",
                },
            ]
        }

        result = cal_mod.fetch_calendars()

        assert [c.id for c in result] == ["primary", "team@group.calendar.google.com"]
        assert result[0].primary is True
        assert result[0].access_role == "owner"
        assert result[1].primary is False
        assert result[1].description == "Shared"

    def test_empty_list_when_no_items_key(self, mock_calendar_service):
        _list_call(mock_calendar_service).execute.return_value = {}
        assert cal_mod.fetch_calendars() == []

    def test_wraps_http_error(self, mock_calendar_service):
        _list_call(mock_calendar_service).execute.side_effect = HttpError(
            resp=MagicMock(status=500, reason="boom"), content=b"err"
        )
        with pytest.raises(MgdioAPIError):
            cal_mod.fetch_calendars()
