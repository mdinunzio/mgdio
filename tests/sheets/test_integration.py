"""Opt-in integration tests that hit the real Sheets API.

Skipped unless ``MGDIO_RUN_INTEGRATION=1``. Creates a throwaway
spreadsheet, exercises read/write/append/clear and tab management,
then deletes a tab (the spreadsheet itself is left in your Drive --
delete it manually if you want a clean state).
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.integration

if os.getenv("MGDIO_RUN_INTEGRATION") != "1":
    pytest.skip(
        "MGDIO_RUN_INTEGRATION!=1; skipping real-API tests",
        allow_module_level=True,
    )


def test_full_cycle():
    from mgdio.sheets import (
        add_sheet,
        append_values,
        clear_values,
        create_spreadsheet,
        delete_sheet,
        fetch_spreadsheet,
        fetch_values,
        rename_sheet,
        write_values,
    )

    token = uuid.uuid4().hex[:8]
    title = f"mgdio integration {token}"
    spreadsheet = create_spreadsheet(title, sheet_names=["Data"])
    assert spreadsheet.title == title
    assert spreadsheet.tabs[0].title == "Data"

    write_values(
        spreadsheet.id,
        "Data!A1:B3",
        [["name", "age"], ["alice", 30], ["bob", 25]],
    )

    rows = fetch_values(spreadsheet.id, "Data!A1:B3")
    assert rows[0] == ["name", "age"]
    assert rows[1][0] == "alice"

    append_values(spreadsheet.id, "Data", [["carol", 28]])
    rows_after = fetch_values(spreadsheet.id, "Data!A1:B10")
    assert ["carol", "28"] in rows_after

    new_tab = add_sheet(spreadsheet.id, "Scratch")
    rename_sheet(spreadsheet.id, new_tab.id, "Scratch2")
    refreshed = fetch_spreadsheet(spreadsheet.id)
    assert any(t.title == "Scratch2" for t in refreshed.tabs)
    delete_sheet(spreadsheet.id, new_tab.id)

    clear_values(spreadsheet.id, "Data!A2:B10")
    rows_after_clear = fetch_values(spreadsheet.id, "Data!A1:B3")
    assert rows_after_clear == [["name", "age"]]
