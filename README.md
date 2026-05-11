# mgdio

Personal connectivity tools (Gmail, Calendar, Sheets, YNAB, Twilio, ...) packaged
so they can be `pip` / `uv add`-ed into any other project with a uniform API.

> **Status** — Unified Google auth (`mgdio.auth.google`) plus Gmail
> (read/send), Google Sheets (read/write/append/clear, spreadsheet + tab
> management), and Google Calendar (list calendars + event CRUD + quick-add).
> Plus YNAB (budgets, accounts, categories, transactions, memo edits) via
> personal-access-token auth. Twilio next.

## Why a dedicated auth subsystem

- **Stable** — OAuth refresh tokens that don't expire (consent screen *Published*
  in Google Cloud Console).
- **Native** — Google's official `google-api-python-client`, not SMTP/IMAP.
- **Free** — works against a personal `@gmail.com`.
- **Vault-backed** — tokens live in the OS credential vault: Windows Credential
  Manager, macOS Keychain, or Linux Secret Service. No plaintext token files.
- **One consent for all Google services** — Gmail, Calendar, and Sheets share a
  single OAuth client and a single token under `mgdio:google`. Consent once;
  every service subpackage just calls `get_credentials()`.

## Layout

```
mgdio/
├── auth/
│   ├── google/        # Gmail + Calendar + Sheets share one OAuth token
│   ├── ynab/          # personal-access-token paste flow
│   └── twilio/        # planned
├── gmail/             # read + send on top of mgdio.auth.google
├── sheets/            # values + spreadsheets/tabs on top of mgdio.auth.google
├── calendar/          # calendars + events CRUD on top of mgdio.auth.google
├── ynab/              # budgets, accounts, categories, transactions
├── settings.py
└── cli.py
```

Each provider exposes the same triple: `get_credentials()`,
`clear_stored_token()`, `reset_credentials_cache()`.

## One-time Google Cloud Console setup

You only do this once per Google account.

1. **Create or pick a project** at <https://console.cloud.google.com>.
2. **Enable the APIs** under *APIs & Services → Library*:
   - Gmail API
   - Google Calendar API
   - Google Sheets API
3. **Configure the app** under *Google Auth Platform* in the left nav:
   - **Branding** — fill in app name and support email.
   - **Audience** — set User type to **External**, add yourself under
     *Test users*, then click **Publish app**. *Critical:* apps left in
     *Testing* mode have their refresh tokens revoked every 7 days.
   - **Data Access** — click *Add or remove scopes* and add all three:
     - `https://www.googleapis.com/auth/gmail.modify`
     - `https://www.googleapis.com/auth/calendar`
     - `https://www.googleapis.com/auth/spreadsheets`
4. **Create an OAuth client ID** under *Google Auth Platform → Clients →
   Create client*:
   - Application type: **Desktop app**.
   - Click *Download JSON*. (You'll drop this into the mgdio setup page in a moment;
     no manual filesystem work.)

## Install

For development on this repo:

```powershell
uv sync --extra dev
uv pip install -e .
```

## First-run auth

```powershell
uv run mgdio auth google
```

A localhost setup page opens in your browser. Drag-and-drop the
`client_secret.json` you downloaded above, click **Authorize**, and approve the
single consent screen covering all three Google scopes. The resulting token is
written to your OS credential vault; future calls read from the vault and
refresh transparently.

To force a fresh consent flow (e.g. after rotating credentials or changing
scopes):

```powershell
uv run mgdio auth google --reset
```

## Where credentials live

- **OAuth token**: OS credential vault under service `mgdio:google`, username
  `oauth_token`. On Windows: *Credential Manager → Windows Credentials*.
- **`client_secret.json`**: plain file at the platform-appropriate path:
  - Windows: `%LOCALAPPDATA%\mgdio\google\client_secret.json`
  - macOS: `~/Library/Application Support/mgdio/google/client_secret.json`
  - Linux: `~/.local/share/mgdio/google/client_secret.json`

This is application configuration, not a per-session secret.

## Gmail

After running `mgdio auth google` once, Gmail is ready. Public API:

```python
from pathlib import Path

from mgdio.gmail import fetch_messages, fetch_message, send_email

# List the 5 most recent messages.
for m in fetch_messages(max_results=5):
    print(m.date, m.sender, m.subject, m.id)

# Search with Gmail's query syntax.
hits = fetch_messages(query="from:foo@bar.com after:2026/01/01", max_results=20)

# Fetch a single message's full content (headers, snippet, plain + HTML body).
msg = fetch_message("199a8b3c...")
print(msg.body_text)

# Send plain text.
send_email(to="someone@example.com", subject="hi", body="hello from mgdio")

# Send HTML + attachment, with cc/bcc.
send_email(
    to=["a@example.com", "b@example.com"],
    subject="weekly report",
    body="See attached. Plain-text fallback.",
    html="<p>See <b>attached</b>.</p>",
    cc="boss@example.com",
    attachments=[Path("report.pdf")],
)
```

CLI equivalents:

```powershell
uv run mgdio gmail list --max 5
uv run mgdio gmail list --query "from:noreply@github.com" --max 3
uv run mgdio gmail get <message_id>
uv run mgdio gmail send --to me@example.com --subject hi --body "hello"
uv run mgdio gmail send --to me@example.com --subject report `
  --body "see attached" --attach report.pdf --attach summary.csv
```

## Sheets

After `mgdio auth google`, Sheets is ready too. Public API covers reading,
writing, appending, clearing, creating spreadsheets, and managing tabs.

```python
from mgdio.sheets import (
    fetch_values, write_values, append_values, clear_values,
    create_spreadsheet, fetch_spreadsheet,
    add_sheet, rename_sheet, delete_sheet,
)

# Read -- default is list of lists.
rows = fetch_values("<spreadsheet_id>", "Sheet1!A1:C10")

# Read as pandas (requires the sheets-pandas extra).
df = fetch_values("<spreadsheet_id>", "Sheet1!A1:C10", as_="pandas")

# Read as polars (requires the sheets-polars extra).
pdf = fetch_values("<spreadsheet_id>", "Sheet1!A1:C10", as_="polars")
# Both DataFrame backends treat the first row as the header.

# Overwrite a range. USER_ENTERED by default ('=SUM(...)' becomes a formula).
write_values(
    "<spreadsheet_id>",
    "Sheet1!A1:B3",
    [["name", "age"], ["alice", 30], ["bob", 25]],
)
# Pass raw=True to store strings literally (no formula/date/number parsing).
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

# Manage tabs (use tab.id from above, not the title).
scratch = add_sheet(new.id, "Scratch")
rename_sheet(new.id, scratch.id, "Scratch2")
delete_sheet(new.id, scratch.id)
```

DataFrame backends are optional. Install with one of:

```powershell
uv pip install -e ".[sheets-pandas]"
uv pip install -e ".[sheets-polars]"
```

CLI equivalents:

```powershell
uv run mgdio sheets info <spreadsheet_id>
uv run mgdio sheets read <spreadsheet_id> "Sheet1!A1:C10"
uv run mgdio sheets write <spreadsheet_id> "Sheet1!A1:B2" --row "name,age" --row "alice,30"
uv run mgdio sheets append <spreadsheet_id> Sheet1 --row "bob,25"
uv run mgdio sheets clear <spreadsheet_id> "Sheet1!A2:B100"
uv run mgdio sheets create --title "Q1 plan" --tab Tasks --tab Budget
```

## Calendar

After `mgdio auth google`, Calendar is ready too. Public API covers listing
calendars, listing events, full event CRUD, and Google's natural-language
"quick add".

```python
from datetime import datetime, timedelta, timezone

from mgdio.calendar import (
    CLEAR,
    create_event, delete_event, fetch_event, fetch_events,
    fetch_calendars, quick_add, update_event,
)

# List every calendar you can access (primary + secondary + shared).
for cal in fetch_calendars():
    print(cal.id, cal.summary, "primary" if cal.primary else cal.access_role)

# List events in a time window. Datetimes must be tz-aware; naive
# datetimes raise ValueError on purpose (boundary validation).
now = datetime.now(timezone.utc)
events = fetch_events(
    time_min=now,
    time_max=now + timedelta(days=7),
    query="lunch",
    max_results=20,
)
for ev in events:
    when = f"{ev.start:%Y-%m-%d}" if ev.all_day else f"{ev.start:%Y-%m-%d %H:%M}"
    print(when, ev.summary, ev.id)

# Create a timed event.
created = create_event(
    summary="Coffee with Bob",
    start=now + timedelta(days=2, hours=10),
    end=now + timedelta(days=2, hours=11),
    description="check in on Q2 plans",
    location="The Spot",
    attendees=["bob@example.com"],
)

# Create an all-day event. Calendar's end-date is exclusive.
create_event(
    summary="Holiday",
    start=datetime(2026, 7, 4, tzinfo=timezone.utc),
    end=datetime(2026, 7, 5, tzinfo=timezone.utc),
    all_day=True,
)

# Update with tri-state PATCH semantics:
#   None (default) -> field is left alone
#   CLEAR sentinel -> field is nulled on the server
#   any value      -> field is set
update_event(created.id, summary="Coffee with Bob (rescheduled)")
update_event(created.id, description=CLEAR, location=CLEAR)

# Natural-language event creation; Google parses the text.
quick_add("Lunch with Alice Tuesday 12pm")

# Delete when done.
delete_event(created.id)
```

CLI equivalents:

```powershell
uv run mgdio calendar list-cals
uv run mgdio calendar list-events --max 10
uv run mgdio calendar list-events --time-min "2026-05-09T00:00:00-04:00" `
  --time-max "2026-05-16T00:00:00-04:00" --query lunch
uv run mgdio calendar get <event_id>
uv run mgdio calendar create --summary "Coffee with Bob" `
  --start "2026-05-12T10:00:00-04:00" --end "2026-05-12T11:00:00-04:00" `
  --attendee bob@example.com --location "The Spot"
uv run mgdio calendar update <event_id> --summary "renamed"
uv run mgdio calendar delete <event_id>
uv run mgdio calendar quick-add "Lunch with Alice Tuesday 12pm"
```

## YNAB

YNAB uses a personal access token (not OAuth). Run `mgdio auth ynab` once and
a localhost setup page opens with instructions for minting a token at
<https://app.ynab.com/settings/developer>. Paste it into the page; mgdio
validates it against `GET /v1/user` before saving to your OS keyring under
`mgdio:ynab`.

Money is stored as integer **milliunits** on the wire (`$12.34` -> `12340`).
All dataclasses expose both the raw milliunit field and a `..._dollars`
convenience property, so you can stay precise or get a float for display.

```python
from datetime import date

from mgdio.ynab import (
    CLEAR,
    fetch_accounts, fetch_budgets, fetch_categories, fetch_transactions,
    update_transaction,
)

# Discover budgets. The "last-used" alias also works in every API below.
for b in fetch_budgets():
    print(b.id, b.name, b.currency_iso_code)

# Accounts + balances on a budget.
for acct in fetch_accounts(budget_id="last-used"):
    print(acct.name, acct.balance_dollars, "on-budget" if acct.on_budget else "tracking")

# This month's categories with budgeted / activity / balance.
for group in fetch_categories():
    for cat in group.categories:
        if cat.hidden or cat.deleted:
            continue
        print(group.name, cat.name, cat.balance_dollars)

# List transactions, optionally filtered.
txns = fetch_transactions(since_date=date(2026, 4, 1), account_id="<acct-id>")

# Edit a transaction's memo (the headline use case).
update_transaction(txns[0].id, memo="grocery run")
update_transaction(txns[0].id, memo=CLEAR)   # explicit clear
# Other fields work the same way:
update_transaction(txns[0].id, cleared="cleared", flag_color="blue")
```

CLI equivalents:

```powershell
uv run mgdio ynab budgets
uv run mgdio ynab accounts --budget last-used
uv run mgdio ynab categories --budget last-used
uv run mgdio ynab transactions --since 2026-04-01 --max 20
uv run mgdio ynab transactions --account <acct-id>
uv run mgdio ynab update-tx <tx-id> --memo "new note"
uv run mgdio ynab update-tx <tx-id> --clear-memo
uv run mgdio ynab update-tx <tx-id> --cleared cleared --flag blue
```

## Building your own Google API client

If you need a different Google API that doesn't have a subpackage yet, the
shared auth is one call away:

```python
from googleapiclient.discovery import build

from mgdio.auth.google import get_credentials

service = build("drive", "v3", credentials=get_credentials(),
                cache_discovery=False)
```

No scopes argument, no per-service auth dance.

## Quick test commands

End-to-end walkthrough of the new auth flow (PowerShell). Run these from the
project root after completing the one-time Cloud Console setup above.

```powershell
# 1. Install deps + editable mgdio
uv sync --extra dev
uv pip install -e .

# 2. Confirm the CLI surface
uv run mgdio --help                # shows the `auth` group
uv run mgdio auth --help           # shows the `google` subcommand
uv run mgdio auth google --help    # shows the --reset flag

# 3. Run the unit suite (no real APIs touched)
uv run pytest -ra

# 4. First-time setup: drag-and-drop client_secret.json, then Authorize
uv run mgdio auth google           # opens browser, completes consent
# Expect: "Authenticated." printed when consent finishes

# 5. Verify the on-disk + vault state landed where expected
Get-ChildItem $env:LOCALAPPDATA\mgdio\google\
# Expect: client_secret.json present

# Inspect the OS keyring entry from Python
uv run python -c "import keyring; t = keyring.get_password('mgdio:google', 'oauth_token'); print('present:', bool(t), 'len:', len(t or ''))"
# Expect: present: True, len: 500+ (a JSON blob)

# 6. Confirm the cached token actually carries all three scopes
uv run python -c "from mgdio.auth.google import get_credentials; c = get_credentials(); print('valid:', c.valid); [print(' -', s) for s in sorted(c.scopes)]"
# Expect three URLs: gmail.modify, calendar, spreadsheets

# 7. Second call is cheap: no browser, no prompt -- hits in-process cache
uv run python -c "from mgdio.auth.google import get_credentials; get_credentials(); print('OK')"

# 8. Verify cross-process persistence: new Python, still no prompt
uv run python -c "from mgdio.auth.google import get_credentials; c = get_credentials(); print('valid (from keyring):', c.valid)"

# 9. Reset and re-auth (forces a fresh consent flow)
uv run mgdio auth google --reset   # opens browser again

# 10. Inspect Credential Manager visually (optional)
#     Start -> "Credential Manager" -> Windows Credentials -> search "mgdio:google"
```

### Gmail quick-test commands

After step 4 above (you've authenticated), exercise the Gmail surface:

```powershell
# Smoke: import the public Gmail API
uv run python -c "from mgdio.gmail import fetch_messages, send_email, fetch_message, GmailMessage; print('imports OK')"

# List your 5 most recent inbox messages
uv run mgdio gmail list --max 5

# Search with Gmail's query syntax
uv run mgdio gmail list --query "is:unread" --max 5
uv run mgdio gmail list --query "from:noreply@github.com newer_than:30d" --max 3

# Pick an id from the list above and view the full message
uv run mgdio gmail get <message_id>

# Send a plain-text email to yourself
uv run mgdio gmail send --to mdinunzio@gmail.com --subject "mgdio smoke" --body "hello"

# Send with cc/bcc/html/attachment
"demo content" | Out-File -Encoding utf8 demo.txt
uv run mgdio gmail send --to mdinunzio@gmail.com --subject "rich smoke" `
  --body "plain fallback" --html "<p><b>html</b> body</p>" --attach demo.txt
Remove-Item demo.txt

# End-to-end demo script (auth + list + search + send plain + send html+attach)
uv run python examples/gmail.py

# Opt-in real-API integration tests (sends a tagged email, then searches for it)
$env:MGDIO_RUN_INTEGRATION = "1"
uv run pytest tests/gmail/test_integration.py -ra
Remove-Item Env:\MGDIO_RUN_INTEGRATION
```

### Sheets quick-test commands

After step 4 above, exercise the Sheets surface. The first command creates a
throwaway spreadsheet you can delete from Drive afterwards.

```powershell
# Smoke: import the public Sheets API
uv run python -c "from mgdio.sheets import fetch_values, write_values, create_spreadsheet, Spreadsheet; print('imports OK')"

# Create a throwaway spreadsheet and capture its id
$sid = (uv run mgdio sheets create --title "mgdio smoke" --tab Data | Select-String "Created:" | ForEach-Object { ($_ -split " ")[-1] })
Write-Output "spreadsheet id: $sid"

# Inspect metadata
uv run mgdio sheets info $sid

# Write a header + 2 rows
uv run mgdio sheets write $sid "Data!A1:B3" --row "name,age" --row "alice,30" --row "bob,25"

# Read it back (default list-of-lists)
uv run mgdio sheets read $sid "Data!A1:B3"

# Read back as a DataFrame from Python
uv run python -c "from mgdio.sheets import fetch_values; df = fetch_values('$sid', 'Data!A1:B3', as_='pandas'); print(df)"
uv run python -c "from mgdio.sheets import fetch_values; df = fetch_values('$sid', 'Data!A1:B3', as_='polars'); print(df)"

# Append a row
uv run mgdio sheets append $sid Data --row "carol,28"

# Clear data rows (header stays)
uv run mgdio sheets clear $sid "Data!A2:B100"

# End-to-end demo (creates its own throwaway spreadsheet)
uv run python examples/sheets.py

# Opt-in real-API integration tests
$env:MGDIO_RUN_INTEGRATION = "1"
uv run pytest tests/sheets/test_integration.py -ra
Remove-Item Env:\MGDIO_RUN_INTEGRATION
```

### Calendar quick-test commands

After step 4 above, exercise the Calendar surface. The create commands make
real events on your calendar; delete them when done (or run the demo script,
which cleans up after itself).

```powershell
# Smoke: import the public Calendar API
uv run python -c "from mgdio.calendar import fetch_events, create_event, CalendarEvent, CLEAR; print('imports OK')"

# List every calendar you can access
uv run mgdio calendar list-cals

# Show the next 10 events on your primary calendar
uv run mgdio calendar list-events --max 10

# Search by free-text query
uv run mgdio calendar list-events --query "standup" --max 5

# Bounded list (must be tz-aware ISO datetimes)
uv run mgdio calendar list-events `
  --time-min "2026-05-09T00:00:00-04:00" `
  --time-max "2026-05-16T00:00:00-04:00"

# Create a throwaway event and capture its id
$eid = (uv run mgdio calendar create --summary "mgdio smoke" `
  --start "2026-05-15T14:00:00-04:00" --end "2026-05-15T15:00:00-04:00" `
  --location "Localhost" | Select-String "Created:" | ForEach-Object { ($_ -split " ")[-1] })
Write-Output "event id: $eid"

# Get it back
uv run mgdio calendar get $eid

# Update it (only --summary changes; other fields untouched)
uv run mgdio calendar update $eid --summary "mgdio smoke (renamed)"

# Delete it
uv run mgdio calendar delete $eid

# Natural-language create (Google parses the string)
uv run mgdio calendar quick-add "mgdio quickadd smoke tomorrow 3pm for 30 minutes"

# End-to-end demo (creates + updates + quick-adds + deletes its own events).
# Note: the file is named calendar_demo.py, NOT calendar.py -- a script
# literally named "calendar.py" would shadow the stdlib `calendar` module
# that google-auth imports transitively.
uv run python examples/calendar_demo.py

# Opt-in real-API integration tests
$env:MGDIO_RUN_INTEGRATION = "1"
uv run pytest tests/calendar/test_integration.py -ra
Remove-Item Env:\MGDIO_RUN_INTEGRATION
```

### YNAB quick-test commands

YNAB doesn't share Google's auth, so it has its own one-time onboarding.

```powershell
# 1. Mint a personal access token + paste it via the setup web page
uv run mgdio auth ynab
# Expect: "Authenticated." printed once the page reports success.

# 2. Confirm the token landed in the OS keyring
uv run python -c "import keyring; t = keyring.get_password('mgdio:ynab', 'personal_access_token'); print('present:', bool(t), 'len:', len(t or ''))"

# 3. Smoke: import the public YNAB API
uv run python -c "from mgdio.ynab import fetch_budgets, fetch_accounts, fetch_categories, fetch_transactions, update_transaction, Budget, Account, Transaction, CLEAR; print('imports OK')"

# 4. List budgets and capture the first id
$bid = (uv run mgdio ynab budgets | Select-Object -First 1 | ForEach-Object { ($_ -split "\s+")[0] })
Write-Output "budget: $bid"

# 5. Inspect the budget
uv run mgdio ynab accounts --budget $bid
uv run mgdio ynab categories --budget $bid
uv run mgdio ynab transactions --budget $bid --max 5

# 6. Round-trip a memo edit on the most recent transaction (demo restores it)
uv run python examples/ynab_demo.py

# 7. Reset and re-auth (forces a fresh paste flow)
uv run mgdio auth ynab --reset

# 8. Opt-in real-API integration tests
$env:MGDIO_RUN_INTEGRATION = "1"
uv run pytest tests/ynab/test_integration.py -ra
Remove-Item Env:\MGDIO_RUN_INTEGRATION
```

## Troubleshooting

- **Refresh token expired / revoked** — verify the Google Auth Platform consent
  screen is *Published*, then `mgdio auth google --reset`.
- **Scope mismatch after upgrade** — if a future release adds a new Google scope,
  the first call will fall back to the setup flow. Approve the new scope on the
  consent screen.
- **Test the package without Google APIs** — `uv run pytest -ra`. The unit suite
  uses an in-memory keyring fixture and never touches your real vault.
- **YNAB token rejected** — `mgdio auth ynab --reset` to paste a new one. The
  setup page calls `GET /v1/user` before saving so common typos surface
  immediately instead of on first use.

## Roadmap

Future subpackages, each per the same auth pattern:

- `mgdio.auth.twilio` + `mgdio.twilio`
