"""Unit tests for ``mgdio.sheets.spreadsheets``."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from mgdio.exceptions import MgdioAPIError
from mgdio.sheets import spreadsheets as sheets_mod


def _spreadsheets_call(service):
    return service.spreadsheets.return_value


def _sample_raw_spreadsheet(
    *,
    spreadsheet_id: str = "sid-1",
    title: str = "My Sheet",
    tabs: tuple[tuple[int, str, int, int, int], ...] = ((0, "Sheet1", 0, 1000, 26),),
) -> dict:
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
    return {
        "spreadsheetId": spreadsheet_id,
        "spreadsheetUrl": url,
        "properties": {
            "title": title,
            "locale": "en_US",
            "timeZone": "America/New_York",
        },
        "sheets": [
            {
                "properties": {
                    "sheetId": sid,
                    "title": stitle,
                    "index": idx,
                    "gridProperties": {"rowCount": rows, "columnCount": cols},
                }
            }
            for sid, stitle, idx, rows, cols in tabs
        ],
    }


class TestCreateSpreadsheet:
    def test_sends_title_and_returns_spreadsheet(self, mock_sheets_service):
        _spreadsheets_call(
            mock_sheets_service
        ).create.return_value.execute.return_value = _sample_raw_spreadsheet(
            spreadsheet_id="new-sid", title="Brand New"
        )

        result = sheets_mod.create_spreadsheet("Brand New")

        assert result.id == "new-sid"
        assert result.title == "Brand New"
        assert result.url.endswith("/new-sid/edit")
        assert len(result.tabs) == 1
        body = _spreadsheets_call(mock_sheets_service).create.call_args.kwargs["body"]
        assert body == {"properties": {"title": "Brand New"}}

    def test_seeds_initial_tab_names(self, mock_sheets_service):
        _spreadsheets_call(
            mock_sheets_service
        ).create.return_value.execute.return_value = _sample_raw_spreadsheet(
            tabs=((1, "Alpha", 0, 100, 10), (2, "Beta", 1, 100, 10))
        )

        result = sheets_mod.create_spreadsheet("X", sheet_names=["Alpha", "Beta"])

        body = _spreadsheets_call(mock_sheets_service).create.call_args.kwargs["body"]
        assert body["sheets"] == [
            {"properties": {"title": "Alpha", "index": 0}},
            {"properties": {"title": "Beta", "index": 1}},
        ]
        assert [t.title for t in result.tabs] == ["Alpha", "Beta"]

    def test_wraps_http_error(self, mock_sheets_service):
        _spreadsheets_call(
            mock_sheets_service
        ).create.return_value.execute.side_effect = HttpError(
            resp=MagicMock(status=500, reason="boom"), content=b"err"
        )
        with pytest.raises(MgdioAPIError):
            sheets_mod.create_spreadsheet("X")


class TestFetchSpreadsheet:
    def test_populates_dataclass(self, mock_sheets_service):
        _spreadsheets_call(
            mock_sheets_service
        ).get.return_value.execute.return_value = _sample_raw_spreadsheet(
            tabs=(
                (10, "Data", 0, 1000, 26),
                (20, "Notes", 1, 500, 10),
            )
        )

        result = sheets_mod.fetch_spreadsheet("sid-1")

        assert result.id == "sid-1"
        assert result.title == "My Sheet"
        assert result.locale == "en_US"
        assert result.time_zone == "America/New_York"
        assert [(t.id, t.title, t.index) for t in result.tabs] == [
            (10, "Data", 0),
            (20, "Notes", 1),
        ]
        kwargs = _spreadsheets_call(mock_sheets_service).get.call_args.kwargs
        assert kwargs["spreadsheetId"] == "sid-1"
        assert kwargs["includeGridData"] is False

    def test_wraps_http_error(self, mock_sheets_service):
        _spreadsheets_call(mock_sheets_service).get.return_value.execute.side_effect = (
            HttpError(resp=MagicMock(status=404, reason="nope"), content=b"err")
        )
        with pytest.raises(MgdioAPIError):
            sheets_mod.fetch_spreadsheet("sid-1")


class TestTabManagement:
    def test_add_sheet_returns_new_tab(self, mock_sheets_service):
        _spreadsheets_call(
            mock_sheets_service
        ).batchUpdate.return_value.execute.return_value = {
            "replies": [
                {
                    "addSheet": {
                        "properties": {
                            "sheetId": 99,
                            "title": "New",
                            "index": 2,
                            "gridProperties": {"rowCount": 1000, "columnCount": 26},
                        }
                    }
                }
            ]
        }

        new_tab = sheets_mod.add_sheet("sid-1", "New")

        assert new_tab.id == 99
        assert new_tab.title == "New"
        assert new_tab.index == 2
        body = _spreadsheets_call(mock_sheets_service).batchUpdate.call_args.kwargs[
            "body"
        ]
        assert body == {"requests": [{"addSheet": {"properties": {"title": "New"}}}]}

    def test_add_sheet_passes_index_when_given(self, mock_sheets_service):
        _spreadsheets_call(
            mock_sheets_service
        ).batchUpdate.return_value.execute.return_value = {
            "replies": [{"addSheet": {"properties": {"sheetId": 1, "title": "X"}}}]
        }
        sheets_mod.add_sheet("sid-1", "X", index=0)
        body = _spreadsheets_call(mock_sheets_service).batchUpdate.call_args.kwargs[
            "body"
        ]
        assert body["requests"][0]["addSheet"]["properties"]["index"] == 0

    def test_rename_sheet_sends_update_properties(self, mock_sheets_service):
        _spreadsheets_call(
            mock_sheets_service
        ).batchUpdate.return_value.execute.return_value = {"replies": [{}]}

        sheets_mod.rename_sheet("sid-1", 42, "Renamed")

        body = _spreadsheets_call(mock_sheets_service).batchUpdate.call_args.kwargs[
            "body"
        ]
        assert body == {
            "requests": [
                {
                    "updateSheetProperties": {
                        "properties": {"sheetId": 42, "title": "Renamed"},
                        "fields": "title",
                    }
                }
            ]
        }

    def test_delete_sheet_sends_delete_request(self, mock_sheets_service):
        _spreadsheets_call(
            mock_sheets_service
        ).batchUpdate.return_value.execute.return_value = {"replies": [{}]}

        sheets_mod.delete_sheet("sid-1", 42)

        body = _spreadsheets_call(mock_sheets_service).batchUpdate.call_args.kwargs[
            "body"
        ]
        assert body == {"requests": [{"deleteSheet": {"sheetId": 42}}]}

    def test_batch_update_wraps_http_error(self, mock_sheets_service):
        _spreadsheets_call(
            mock_sheets_service
        ).batchUpdate.return_value.execute.side_effect = HttpError(
            resp=MagicMock(status=400, reason="bad"), content=b"err"
        )
        with pytest.raises(MgdioAPIError):
            sheets_mod.delete_sheet("sid-1", 42)
