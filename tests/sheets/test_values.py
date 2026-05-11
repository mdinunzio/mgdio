"""Unit tests for ``mgdio.sheets.values``."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from mgdio.exceptions import MgdioAPIError
from mgdio.sheets import values as values_mod


def _values_calls(service):
    return service.spreadsheets.return_value.values.return_value


class TestFetchValues:
    def test_returns_list_by_default(self, mock_sheets_service):
        _values_calls(mock_sheets_service).get.return_value.execute.return_value = {
            "values": [["a", "b"], ["1", "2"]]
        }
        result = values_mod.fetch_values("sid", "Sheet1!A1:B2")
        assert result == [["a", "b"], ["1", "2"]]

    def test_returns_empty_list_when_api_returns_no_values_key(
        self, mock_sheets_service
    ):
        _values_calls(mock_sheets_service).get.return_value.execute.return_value = {}
        assert values_mod.fetch_values("sid", "Sheet1") == []

    def test_passes_range_to_api(self, mock_sheets_service):
        _values_calls(mock_sheets_service).get.return_value.execute.return_value = {}
        values_mod.fetch_values("sid-42", "Tab2!A:C")
        kwargs = _values_calls(mock_sheets_service).get.call_args.kwargs
        assert kwargs["spreadsheetId"] == "sid-42"
        assert kwargs["range"] == "Tab2!A:C"

    def test_wraps_http_error(self, mock_sheets_service):
        _values_calls(mock_sheets_service).get.return_value.execute.side_effect = (
            HttpError(resp=MagicMock(status=500, reason="boom"), content=b"err")
        )
        with pytest.raises(MgdioAPIError):
            values_mod.fetch_values("sid", "Sheet1!A1")

    def test_rejects_unknown_as_kwarg(self, mock_sheets_service):
        _values_calls(mock_sheets_service).get.return_value.execute.return_value = {
            "values": [["a"]]
        }
        with pytest.raises(ValueError):
            values_mod.fetch_values("sid", "Sheet1", as_="parquet")


class TestFetchValuesPandas:
    def test_returns_dataframe_with_header_row(self, mock_sheets_service):
        _values_calls(mock_sheets_service).get.return_value.execute.return_value = {
            "values": [["name", "age"], ["alice", "30"], ["bob", "25"]]
        }
        df = values_mod.fetch_values("sid", "Sheet1", as_="pandas")
        assert list(df.columns) == ["name", "age"]
        assert df.shape == (2, 2)
        assert df.iloc[0]["name"] == "alice"

    def test_pads_ragged_rows(self, mock_sheets_service):
        _values_calls(mock_sheets_service).get.return_value.execute.return_value = {
            "values": [["a", "b", "c"], ["1"], ["x", "y"]]
        }
        df = values_mod.fetch_values("sid", "Sheet1", as_="pandas")
        assert df.shape == (2, 3)
        assert df.iloc[0]["c"] is None
        assert df.iloc[1]["c"] is None

    def test_empty_response_returns_empty_dataframe(self, mock_sheets_service):
        _values_calls(mock_sheets_service).get.return_value.execute.return_value = {}
        df = values_mod.fetch_values("sid", "Sheet1", as_="pandas")
        assert df.empty


class TestFetchValuesPolars:
    def test_returns_dataframe_with_header_row(self, mock_sheets_service):
        _values_calls(mock_sheets_service).get.return_value.execute.return_value = {
            "values": [["name", "age"], ["alice", "30"], ["bob", "25"]]
        }
        df = values_mod.fetch_values("sid", "Sheet1", as_="polars")
        assert df.columns == ["name", "age"]
        assert df.shape == (2, 2)

    def test_pads_ragged_rows(self, mock_sheets_service):
        _values_calls(mock_sheets_service).get.return_value.execute.return_value = {
            "values": [["a", "b", "c"], ["1"], ["x", "y"]]
        }
        df = values_mod.fetch_values("sid", "Sheet1", as_="polars")
        assert df.shape == (2, 3)


class TestWriteValues:
    def test_overwrites_with_user_entered_by_default(self, mock_sheets_service):
        _values_calls(mock_sheets_service).update.return_value.execute.return_value = {
            "updatedCells": 4
        }

        updated = values_mod.write_values("sid", "Sheet1!A1:B2", [["a", "b"], ["1", 2]])

        assert updated == 4
        kwargs = _values_calls(mock_sheets_service).update.call_args.kwargs
        assert kwargs["spreadsheetId"] == "sid"
        assert kwargs["range"] == "Sheet1!A1:B2"
        assert kwargs["valueInputOption"] == "USER_ENTERED"
        assert kwargs["body"] == {"values": [["a", "b"], ["1", 2]]}

    def test_raw_flag_switches_value_input_option(self, mock_sheets_service):
        _values_calls(mock_sheets_service).update.return_value.execute.return_value = {
            "updatedCells": 1
        }
        values_mod.write_values("sid", "Sheet1!A1", [["=SUM(A1:A2)"]], raw=True)
        kwargs = _values_calls(mock_sheets_service).update.call_args.kwargs
        assert kwargs["valueInputOption"] == "RAW"

    def test_accepts_tuples_and_normalizes_to_lists(self, mock_sheets_service):
        _values_calls(mock_sheets_service).update.return_value.execute.return_value = {
            "updatedCells": 2
        }
        values_mod.write_values("sid", "Sheet1!A1:B1", [("a", "b")])
        body = _values_calls(mock_sheets_service).update.call_args.kwargs["body"]
        assert body == {"values": [["a", "b"]]}

    def test_wraps_http_error(self, mock_sheets_service):
        _values_calls(mock_sheets_service).update.return_value.execute.side_effect = (
            HttpError(resp=MagicMock(status=500, reason="boom"), content=b"err")
        )
        with pytest.raises(MgdioAPIError):
            values_mod.write_values("sid", "Sheet1!A1", [["x"]])


class TestAppendValues:
    def test_appends_with_insert_rows(self, mock_sheets_service):
        _values_calls(mock_sheets_service).append.return_value.execute.return_value = {
            "updates": {"updatedCells": 2}
        }

        updated = values_mod.append_values("sid", "Sheet1", [["new", "row"]])

        assert updated == 2
        kwargs = _values_calls(mock_sheets_service).append.call_args.kwargs
        assert kwargs["valueInputOption"] == "USER_ENTERED"
        assert kwargs["insertDataOption"] == "INSERT_ROWS"
        assert kwargs["body"] == {"values": [["new", "row"]]}

    def test_returns_zero_when_updates_missing(self, mock_sheets_service):
        _values_calls(mock_sheets_service).append.return_value.execute.return_value = {}
        assert values_mod.append_values("sid", "Sheet1", [["x"]]) == 0

    def test_wraps_http_error(self, mock_sheets_service):
        _values_calls(mock_sheets_service).append.return_value.execute.side_effect = (
            HttpError(resp=MagicMock(status=500, reason="boom"), content=b"err")
        )
        with pytest.raises(MgdioAPIError):
            values_mod.append_values("sid", "Sheet1", [["x"]])


class TestClearValues:
    def test_calls_clear_with_empty_body(self, mock_sheets_service):
        _values_calls(mock_sheets_service).clear.return_value.execute.return_value = {}
        values_mod.clear_values("sid", "Sheet1!A1:Z100")
        kwargs = _values_calls(mock_sheets_service).clear.call_args.kwargs
        assert kwargs["spreadsheetId"] == "sid"
        assert kwargs["range"] == "Sheet1!A1:Z100"
        assert kwargs["body"] == {}

    def test_wraps_http_error(self, mock_sheets_service):
        _values_calls(mock_sheets_service).clear.return_value.execute.side_effect = (
            HttpError(resp=MagicMock(status=500, reason="boom"), content=b"err")
        )
        with pytest.raises(MgdioAPIError):
            values_mod.clear_values("sid", "Sheet1!A1")
