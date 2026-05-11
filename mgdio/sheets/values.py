"""Sheets ``values.*`` API: fetch/write/append/clear ranges.

Read functions accept an ``as_`` parameter selecting the return shape:

* ``"list"`` (default) -- ``list[list[Any]]``, the raw API shape.
* ``"pandas"`` -- ``pandas.DataFrame``, requires the ``sheets-pandas`` extra.
* ``"polars"`` -- ``polars.DataFrame``, requires the ``sheets-polars`` extra.

When a DataFrame is requested, the first row of the range is treated as
the header. If the range is empty an empty DataFrame is returned.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, Sequence

from googleapiclient.errors import HttpError

from mgdio.exceptions import MgdioAPIError
from mgdio.sheets.client import get_service

logger = logging.getLogger(__name__)

ReturnAs = Literal["list", "pandas", "polars"]
ValueInputOption = Literal["USER_ENTERED", "RAW"]


def fetch_values(
    spreadsheet_id: str,
    range_: str,
    *,
    as_: ReturnAs = "list",
) -> Any:
    """Read a range from a spreadsheet.

    Args:
        spreadsheet_id: The spreadsheet's id (from its URL).
        range_: A1-style range, e.g. ``"Sheet1!A1:C10"``. Omit the cell
            range to grab the whole tab, e.g. ``"Sheet1"``.
        as_: Return shape -- ``"list"`` (default), ``"pandas"``, or
            ``"polars"``. The DataFrame options treat the first row as
            the header.

    Returns:
        ``list[list[Any]]`` when ``as_="list"``; a DataFrame otherwise.

    Raises:
        MgdioAPIError: On any Sheets API HTTP error.
        ImportError: If the requested ``as_`` backend is not installed.
    """
    service = get_service()
    try:
        resp = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_)
            .execute()
        )
    except HttpError as exc:
        raise MgdioAPIError(
            f"Sheets values.get {spreadsheet_id} {range_!r} failed: {exc}"
        ) from exc

    values: list[list[Any]] = resp.get("values", [])
    if as_ == "list":
        return values
    if as_ == "pandas":
        return _to_pandas(values)
    if as_ == "polars":
        return _to_polars(values)
    raise ValueError(f"Unknown as_={as_!r}; expected 'list', 'pandas', or 'polars'.")


def write_values(
    spreadsheet_id: str,
    range_: str,
    values: Sequence[Sequence[Any]],
    *,
    raw: bool = False,
) -> int:
    """Overwrite a range with ``values``.

    Args:
        spreadsheet_id: The spreadsheet's id.
        range_: A1-style range. If ``values`` is smaller than the range,
            only the corresponding cells are written; if larger, the
            extra cells are ignored unless the range is open-ended.
        values: Rows of cell values. Strings starting with ``=`` are
            treated as formulas unless ``raw=True``.
        raw: If ``True``, use ``valueInputOption=RAW`` -- the cells store
            the literal strings. Default ``USER_ENTERED`` parses formulas,
            dates, and numbers.

    Returns:
        Number of cells updated, per the Sheets API response.

    Raises:
        MgdioAPIError: On any Sheets API HTTP error.
    """
    option: ValueInputOption = "RAW" if raw else "USER_ENTERED"
    body = {"values": [list(row) for row in values]}
    service = get_service()
    try:
        resp = (
            service.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=range_,
                valueInputOption=option,
                body=body,
            )
            .execute()
        )
    except HttpError as exc:
        raise MgdioAPIError(
            f"Sheets values.update {spreadsheet_id} {range_!r} failed: {exc}"
        ) from exc
    return int(resp.get("updatedCells", 0))


def append_values(
    spreadsheet_id: str,
    range_: str,
    values: Sequence[Sequence[Any]],
    *,
    raw: bool = False,
) -> int:
    """Append rows to the end of a table.

    The Sheets API finds the table that overlaps ``range_`` and inserts
    the new rows after the last non-empty row.

    Args:
        spreadsheet_id: The spreadsheet's id.
        range_: Range used to locate the target table (typically just
            the tab name, e.g. ``"Sheet1"``, or a column range like
            ``"Sheet1!A:C"``).
        values: Rows to append.
        raw: If ``True``, use ``valueInputOption=RAW`` instead of
            ``USER_ENTERED``.

    Returns:
        Number of cells updated.

    Raises:
        MgdioAPIError: On any Sheets API HTTP error.
    """
    option: ValueInputOption = "RAW" if raw else "USER_ENTERED"
    body = {"values": [list(row) for row in values]}
    service = get_service()
    try:
        resp = (
            service.spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=range_,
                valueInputOption=option,
                insertDataOption="INSERT_ROWS",
                body=body,
            )
            .execute()
        )
    except HttpError as exc:
        raise MgdioAPIError(
            f"Sheets values.append {spreadsheet_id} {range_!r} failed: {exc}"
        ) from exc
    updates = resp.get("updates", {})
    return int(updates.get("updatedCells", 0))


def clear_values(spreadsheet_id: str, range_: str) -> None:
    """Clear all values in ``range_`` (formatting is preserved).

    Args:
        spreadsheet_id: The spreadsheet's id.
        range_: A1-style range to clear.

    Raises:
        MgdioAPIError: On any Sheets API HTTP error.
    """
    service = get_service()
    try:
        service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id, range=range_, body={}
        ).execute()
    except HttpError as exc:
        raise MgdioAPIError(
            f"Sheets values.clear {spreadsheet_id} {range_!r} failed: {exc}"
        ) from exc


def _to_pandas(values: list[list[Any]]):
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - exercised via import-error test
        raise ImportError(
            "pandas is required for as_='pandas'. "
            "Install with: pip install 'mgdio[sheets-pandas]'"
        ) from exc
    if not values:
        return pd.DataFrame()
    header, *rows = values
    width = len(header)
    normalized = [row + [None] * (width - len(row)) for row in rows]
    return pd.DataFrame(normalized, columns=header)


def _to_polars(values: list[list[Any]]):
    try:
        import polars as pl
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "polars is required for as_='polars'. "
            "Install with: pip install 'mgdio[sheets-polars]'"
        ) from exc
    if not values:
        return pl.DataFrame()
    header, *rows = values
    width = len(header)
    normalized = [row + [None] * (width - len(row)) for row in rows]
    # orient='row' so each element of normalized is a row, not a column.
    return pl.DataFrame(normalized, schema=header, orient="row")
