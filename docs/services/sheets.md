# Sheets

Read, write, append, and clear ranges; create spreadsheets; manage tabs. Uses
the shared Google login from [`mgdio auth google`](../auth.md#first-run-auth).

| | |
| --- | --- |
| Import | `from mgdio.sheets import fetch_values, write_values, append_values, ...` |
| Returns | lists of lists by default, or a pandas / polars DataFrame; [`Spreadsheet`](../reference/sheets.md) and `SheetTab` dataclasses for metadata |
| CLI | `mgdio sheets info / read / write / append / clear / create` |
| Reference | [mgdio.sheets](../reference/sheets.md) |
| Example | [`examples/sheets.py`](https://github.com/mdinunzio/mgdio/blob/main/examples/sheets.py) |

## Python

```python
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

# Read. Default is a list of lists.
rows = fetch_values("<spreadsheet_id>", "Sheet1!A1:C10")

# Read as pandas (needs the sheets-pandas extra) or polars (sheets-polars).
# Both treat the first row as the header.
df = fetch_values("<spreadsheet_id>", "Sheet1!A1:C10", as_="pandas")
pdf = fetch_values("<spreadsheet_id>", "Sheet1!A1:C10", as_="polars")

# Overwrite a range. USER_ENTERED by default: '=SUM(...)' becomes a formula.
write_values(
    "<spreadsheet_id>",
    "Sheet1!A1:B3",
    [["name", "age"], ["alice", 30], ["bob", 25]],
)
# raw=True stores strings literally (no formula / date / number parsing).
write_values("<spreadsheet_id>", "Sheet1!A1", [["=NOT A FORMULA"]], raw=True)

# Append rows to the end of an existing table.
append_values("<spreadsheet_id>", "Sheet1", [["carol", 28]])

# Clear values in a range (formatting preserved).
clear_values("<spreadsheet_id>", "Sheet1!A2:B100")

# Create a new spreadsheet with named tabs.
new = create_spreadsheet("Q1 plan", sheet_names=["Tasks", "Budget"])
print(new.id, new.url)

# Inspect metadata: title, tabs, locale, time_zone.
meta = fetch_spreadsheet(new.id)
for tab in meta.tabs:
    print(tab.id, tab.title, tab.index, tab.row_count, tab.column_count)

# Manage tabs by tab.id (not title).
scratch = add_sheet(new.id, "Scratch")
rename_sheet(new.id, scratch.id, "Scratch2")
delete_sheet(new.id, scratch.id)
```

Install a DataFrame backend with the matching extra:

```bash
uv add "mgdio[sheets-pandas] @ git+https://github.com/mdinunzio/mgdio.git"
uv add "mgdio[sheets-polars] @ git+https://github.com/mdinunzio/mgdio.git"
```

## CLI

```bash
mgdio sheets info <spreadsheet_id>
mgdio sheets read <spreadsheet_id> "Sheet1!A1:C10"
mgdio sheets write <spreadsheet_id> "Sheet1!A1:B2" --row "name,age" --row "alice,30"
mgdio sheets append <spreadsheet_id> Sheet1 --row "bob,25"
mgdio sheets clear <spreadsheet_id> "Sheet1!A2:B100"
mgdio sheets create --title "Q1 plan" --tab Tasks --tab Budget
```

Add `--profile <slug>` to any command to choose the Google account.
