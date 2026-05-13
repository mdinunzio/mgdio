---
name: mgdio-sheets
description: Read, write, append, and manage Google Sheets via the `mgdio
  sheets` CLI. Use this when the user wants to read a range from a
  spreadsheet, write tabular data to specific cells, append rows to a table,
  clear values, create a new spreadsheet, inspect spreadsheet/tab metadata,
  or add/rename/delete tabs. Handles A1 ranges, formula vs literal input,
  and optional pandas/polars DataFrame returns for analysis chaining.
---

# mgdio Sheets

Read and write Google Sheets through the user's account via the `mgdio` CLI.

## Prerequisite

The user must have authenticated once: `mgdio auth google`. The same token
covers Gmail, Calendar, and Sheets.

## Safety contract

**Read** operations (`info`, `read`) are safe to perform on user request.
**Write** operations (`write`, `append`, `clear`, `create`, plus tab
add/rename/delete via Python) MUST be confirmed with the user before
invocation. Paraphrase what you're about to do — target spreadsheet,
target range, what you're writing/clearing — and wait for explicit
approval, even if the user's prompt sounded like permission. Never chain
multiple writes without re-confirming each one.

## CLI: read

```bash
# Spreadsheet metadata: title, tabs, time-zone
mgdio sheets info <spreadsheet_id>

# Read a range (A1 notation). Whole tab if you omit the cell range.
mgdio sheets read <spreadsheet_id> "Sheet1!A1:C10"
mgdio sheets read <spreadsheet_id> "Data"
```

Output of `read` is tab-separated rows on stdout.

## CLI: write (REQUIRES CONFIRMATION)

```bash
# Overwrite a fixed range. --row is repeatable; cells are comma-separated.
mgdio sheets write <spreadsheet_id> "Sheet1!A1:B3" \
  --row "name,age" --row "alice,30" --row "bob,25"

# Append rows to the table at a range (typically just the tab name)
mgdio sheets append <spreadsheet_id> "Sheet1" --row "carol,28"

# Clear values in a range (formatting preserved)
mgdio sheets clear <spreadsheet_id> "Sheet1!A2:B100"

# Create a new spreadsheet, optionally with named initial tabs
mgdio sheets create --title "Q1 plan" --tab Tasks --tab Budget
```

By default writes use `valueInputOption=USER_ENTERED`: strings beginning
with `=` become real formulas, dates and numbers are parsed. Pass `--raw`
to store strings literally (useful when you want to display a formula
verbatim or you have user data that happens to start with `=`).

## Python (when chaining is needed)

```python
from mgdio.sheets import (
    fetch_values, write_values, append_values, clear_values,
    create_spreadsheet, fetch_spreadsheet,
    add_sheet, rename_sheet, delete_sheet,
    Spreadsheet, SheetTab,
)
```

`fetch_values(spreadsheet_id, range_, *, as_="list"|"pandas"|"polars")`
returns rows in the requested shape. **DataFrame modes treat the first
row as the header**; install the corresponding extra
(`mgdio[sheets-pandas]` or `mgdio[sheets-polars]`) before using them.

`write_values(..., values, *, raw=False) -> int` returns the cell count
updated. `append_values(..., values, *, raw=False) -> int` returns cells
appended. `clear_values(spreadsheet_id, range_) -> None`.

`create_spreadsheet(title, *, sheet_names=None) -> Spreadsheet` and
`fetch_spreadsheet(spreadsheet_id) -> Spreadsheet` return the metadata
dataclass:

- `Spreadsheet(id, title, url, tabs: tuple[SheetTab, ...], time_zone, locale)`
- `SheetTab(id: int, title, index, row_count, column_count)` — use the
  numeric `id` (not the title) with the tab-management functions.

`add_sheet(spreadsheet_id, title, *, index=None) -> SheetTab`,
`rename_sheet(spreadsheet_id, sheet_id, new_title) -> None`,
`delete_sheet(spreadsheet_id, sheet_id) -> None`.

## Gotchas

- **A1 notation**: `"Sheet1!A1:C10"` (range) or `"Sheet1"` (whole tab).
  Quote it when shell-escaping is in play.
- **USER_ENTERED vs RAW**: only pass `raw=True` / `--raw` when you
  genuinely want literal strings; the default parses dates/numbers/
  formulas like the Sheets web UI.
- **Tab management uses `sheet_id` (int)**, not the tab title — get it
  from `Spreadsheet.tabs[*].id` or `mgdio sheets info`.
- **`spreadsheet_id`** is the long opaque string in the spreadsheet URL,
  between `/d/` and `/edit`.
