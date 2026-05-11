"""Google Sheets end-to-end demo for the mgdio package.

Run this after installing mgdio (``uv add mgdio`` or ``uv pip install -e .``)
and completing the one-time OAuth setup (``uv run mgdio auth google``).

Walks through the full surface:

1. Create a throwaway spreadsheet.
2. Write a header + data rows.
3. Read them back as plain list, then as pandas, then as polars (if installed).
4. Append a row.
5. Manage tabs: add, rename, delete.
6. Clear a range.
7. Print the URL so you can inspect the result; the spreadsheet is left
   in your Drive (delete manually if you want a clean state).

Usage:
    uv run python examples/sheets.py
"""

from __future__ import annotations

import uuid

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


def main() -> None:
    """Run the full Sheets demo cycle."""
    token = uuid.uuid4().hex[:8]
    title = f"mgdio demo {token}"

    print(f"== 1. Create spreadsheet: {title!r} ==")
    sheet = create_spreadsheet(title, sheet_names=["People"])
    print(f"   id:    {sheet.id}")
    print(f"   url:   {sheet.url}")
    print(f"   tabs:  {[t.title for t in sheet.tabs]}")

    print("\n== 2. Write header + 2 data rows to People!A1:B3 ==")
    written = write_values(
        sheet.id,
        "People!A1:B3",
        [["name", "age"], ["alice", 30], ["bob", 25]],
    )
    print(f"   cells written: {written}")

    print("\n== 3a. Read back as list of lists ==")
    rows = fetch_values(sheet.id, "People!A1:B3")
    for row in rows:
        print(f"   {row}")

    print("\n== 3b. Read back as pandas DataFrame ==")
    try:
        df = fetch_values(sheet.id, "People!A1:B3", as_="pandas")
        print(df.to_string(index=False))
    except ImportError as exc:
        print(f"   skipped: {exc}")

    print("\n== 3c. Read back as polars DataFrame ==")
    try:
        pdf = fetch_values(sheet.id, "People!A1:B3", as_="polars")
        print(pdf)
    except ImportError as exc:
        print(f"   skipped: {exc}")

    print("\n== 4. Append one row ==")
    appended = append_values(sheet.id, "People", [["carol", 28]])
    print(f"   cells appended: {appended}")
    print("   current contents:")
    for row in fetch_values(sheet.id, "People!A1:B10"):
        print(f"   {row}")

    print("\n== 5. Tab management: add, rename, delete ==")
    scratch = add_sheet(sheet.id, "Scratch")
    print(f"   added: {scratch.title} (sheetId={scratch.id})")
    rename_sheet(sheet.id, scratch.id, "Scratch2")
    refreshed = fetch_spreadsheet(sheet.id)
    print(f"   tabs after rename: {[t.title for t in refreshed.tabs]}")
    delete_sheet(sheet.id, scratch.id)
    final = fetch_spreadsheet(sheet.id)
    print(f"   tabs after delete: {[t.title for t in final.tabs]}")

    print("\n== 6. Clear data rows (keep the header) ==")
    clear_values(sheet.id, "People!A2:B100")
    print("   contents after clear:")
    for row in fetch_values(sheet.id, "People!A1:B5"):
        print(f"   {row}")

    print(f"\nDone. Open the sheet at:\n   {sheet.url}")


if __name__ == "__main__":
    main()
