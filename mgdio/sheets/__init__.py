"""Google Sheets subpackage public API.

Built on top of :mod:`mgdio.auth.google` -- the unified Google OAuth flow
provides the credentials; this subpackage just wraps the Sheets v4 API.
"""

from __future__ import annotations

from mgdio.sheets.client import get_service
from mgdio.sheets.spreadsheets import (
    SheetTab,
    Spreadsheet,
    add_sheet,
    create_spreadsheet,
    delete_sheet,
    fetch_spreadsheet,
    rename_sheet,
)
from mgdio.sheets.values import (
    append_values,
    clear_values,
    fetch_values,
    write_values,
)

__all__ = [
    "SheetTab",
    "Spreadsheet",
    "add_sheet",
    "append_values",
    "clear_values",
    "create_spreadsheet",
    "delete_sheet",
    "fetch_spreadsheet",
    "fetch_values",
    "get_service",
    "rename_sheet",
    "write_values",
]
