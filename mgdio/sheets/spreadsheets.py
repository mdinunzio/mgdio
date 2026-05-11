"""Sheets ``spreadsheets.*`` API: create, fetch metadata, manage tabs.

Tab management (add/rename/delete) goes through ``spreadsheets.batchUpdate``;
``create`` and ``get`` are their own top-level verbs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

from googleapiclient.errors import HttpError

from mgdio.exceptions import MgdioAPIError
from mgdio.sheets.client import get_service

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SheetTab:
    """A single tab inside a spreadsheet.

    Attributes:
        id: Numeric sheet id (used by batchUpdate requests).
        title: Tab display name.
        index: Zero-based position among the tabs.
        row_count: Provisioned row count (not the populated count).
        column_count: Provisioned column count.
    """

    id: int
    title: str
    index: int
    row_count: int
    column_count: int


@dataclass(frozen=True, slots=True)
class Spreadsheet:
    """A spreadsheet's top-level metadata.

    Attributes:
        id: Spreadsheet id (the long string in its URL).
        title: Document title.
        url: ``https://docs.google.com/spreadsheets/d/<id>/edit``.
        tabs: Tuple of :class:`SheetTab`, in order.
        time_zone: Spreadsheet time zone (e.g. ``"America/New_York"``).
        locale: Spreadsheet locale (e.g. ``"en_US"``).
    """

    id: str
    title: str
    url: str
    tabs: tuple[SheetTab, ...]
    time_zone: str
    locale: str


def create_spreadsheet(
    title: str,
    *,
    sheet_names: Sequence[str] | None = None,
) -> Spreadsheet:
    """Create a new spreadsheet.

    Args:
        title: Document title.
        sheet_names: Optional initial tab names. If omitted, Google
            creates one tab named ``"Sheet1"``.

    Returns:
        A populated :class:`Spreadsheet` for the new document.

    Raises:
        MgdioAPIError: On any Sheets API HTTP error.
    """
    body: dict = {"properties": {"title": title}}
    if sheet_names:
        body["sheets"] = [
            {"properties": {"title": name, "index": idx}}
            for idx, name in enumerate(sheet_names)
        ]
    service = get_service()
    try:
        raw = service.spreadsheets().create(body=body).execute()
    except HttpError as exc:
        raise MgdioAPIError(f"Sheets create failed: {exc}") from exc
    return _to_spreadsheet(raw)


def fetch_spreadsheet(spreadsheet_id: str) -> Spreadsheet:
    """Fetch metadata for a spreadsheet (no cell values).

    Args:
        spreadsheet_id: The spreadsheet's id.

    Returns:
        A populated :class:`Spreadsheet`.

    Raises:
        MgdioAPIError: On any Sheets API HTTP error.
    """
    service = get_service()
    try:
        raw = (
            service.spreadsheets()
            .get(spreadsheetId=spreadsheet_id, includeGridData=False)
            .execute()
        )
    except HttpError as exc:
        raise MgdioAPIError(f"Sheets get {spreadsheet_id} failed: {exc}") from exc
    return _to_spreadsheet(raw)


def add_sheet(
    spreadsheet_id: str,
    title: str,
    *,
    index: int | None = None,
) -> SheetTab:
    """Add a tab to a spreadsheet.

    Args:
        spreadsheet_id: The spreadsheet's id.
        title: Name of the new tab.
        index: Optional zero-based position; default is "append at end".

    Returns:
        The new :class:`SheetTab`.

    Raises:
        MgdioAPIError: On any Sheets API HTTP error.
    """
    properties: dict = {"title": title}
    if index is not None:
        properties["index"] = index
    request = {"addSheet": {"properties": properties}}
    raw = _batch_update(spreadsheet_id, [request])
    reply = raw["replies"][0]["addSheet"]["properties"]
    return _to_sheet_tab(reply)


def rename_sheet(spreadsheet_id: str, sheet_id: int, new_title: str) -> None:
    """Rename a tab.

    Args:
        spreadsheet_id: The spreadsheet's id.
        sheet_id: The numeric sheet id (from :attr:`SheetTab.id`).
        new_title: New tab name.

    Raises:
        MgdioAPIError: On any Sheets API HTTP error.
    """
    request = {
        "updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "title": new_title},
            "fields": "title",
        }
    }
    _batch_update(spreadsheet_id, [request])


def delete_sheet(spreadsheet_id: str, sheet_id: int) -> None:
    """Delete a tab.

    Args:
        spreadsheet_id: The spreadsheet's id.
        sheet_id: The numeric sheet id (from :attr:`SheetTab.id`).

    Raises:
        MgdioAPIError: On any Sheets API HTTP error.
    """
    request = {"deleteSheet": {"sheetId": sheet_id}}
    _batch_update(spreadsheet_id, [request])


def _batch_update(spreadsheet_id: str, requests: list[dict]) -> dict:
    service = get_service()
    try:
        return (
            service.spreadsheets()
            .batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": requests})
            .execute()
        )
    except HttpError as exc:
        raise MgdioAPIError(
            f"Sheets batchUpdate {spreadsheet_id} failed: {exc}"
        ) from exc


def _to_spreadsheet(raw: dict) -> Spreadsheet:
    props = raw.get("properties", {})
    tabs = tuple(
        _to_sheet_tab(sheet.get("properties", {})) for sheet in raw.get("sheets", [])
    )
    spreadsheet_id = raw.get("spreadsheetId", "")
    return Spreadsheet(
        id=spreadsheet_id,
        title=props.get("title", ""),
        url=raw.get(
            "spreadsheetUrl",
            f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
        ),
        tabs=tabs,
        time_zone=props.get("timeZone", ""),
        locale=props.get("locale", ""),
    )


def _to_sheet_tab(properties: dict) -> SheetTab:
    grid = properties.get("gridProperties", {}) or {}
    return SheetTab(
        id=int(properties.get("sheetId", 0)),
        title=properties.get("title", ""),
        index=int(properties.get("index", 0)),
        row_count=int(grid.get("rowCount", 0)),
        column_count=int(grid.get("columnCount", 0)),
    )
