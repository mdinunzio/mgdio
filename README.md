# mgdio

Personal connectivity tools (Gmail, Calendar, Sheets, YNAB, Twilio, ...) packaged
so they can be `pip` / `uv add`-ed into any other project with a uniform API.

> **Status** — Unified Google auth (`mgdio.auth.google`) plus Gmail
> (read/send), Google Sheets (read/write/append/clear, spreadsheet + tab
> management), Google Calendar (list calendars + event CRUD + quick-add), and
> Google Drive (list/search, upload/download/export, folders, move/copy,
> trash/delete, sharing). Plus Google Maps (geocoding + distance / duration /
> directions) via an API key, YNAB (budgets, accounts, categories,
> transactions, memo edits) via personal-access-token auth, and Whoop
> (recovery, sleep, workouts, cycles, profile, body) via OAuth 2.0. Both
> browser-based and headless (VPS-friendly) Google OAuth flows supported.
> Twilio next.

## Why a dedicated auth subsystem

- **Stable** — OAuth refresh tokens that don't expire (consent screen *Published*
  in Google Cloud Console).
- **Native** — Google's official `google-api-python-client`, not SMTP/IMAP.
- **Free** — works against a personal `@gmail.com`.
- **Vault-backed** — tokens live in the OS credential vault: Windows Credential
  Manager, macOS Keychain, or Linux Secret Service. No plaintext token files.
- **One consent for all Google services** — Gmail, Calendar, Sheets, and Drive
  share a single OAuth client. Consent once per account; every service
  subpackage just calls `get_credentials()`.
- **Multiple Google accounts** — each account is a named *profile* with its own
  token under `mgdio:google:<slug>`. Select one with `--profile`, the
  `MGDIO_GOOGLE_PROFILE` env var, or automatically when only one exists. See
  [Multiple Google accounts](#multiple-google-accounts-profiles).
- **Headless-friendly** — `mgdio auth google --headless` runs a copy-paste
  OAuth flow for machines without a browser (Linux VPS, containers, SSH-only
  hosts). See [Headless install](#headless-install-linux-vps-ssh-only-machines)
  below.

## Layout

```
mgdio/
├── auth/
│   ├── google/        # Gmail + Calendar + Sheets + Drive share one OAuth token
│   ├── maps/          # Google Maps API-key paste flow
│   ├── ynab/          # personal-access-token paste flow
│   ├── whoop/         # OAuth 2.0 code flow (paste Client ID/Secret + authorize)
│   └── twilio/        # planned
├── gmail/             # read + send on top of mgdio.auth.google
├── sheets/            # values + spreadsheets/tabs on top of mgdio.auth.google
├── calendar/          # calendars + events CRUD on top of mgdio.auth.google
├── drive/             # files/folders, upload/download, sharing on mgdio.auth.google
├── maps/              # geocoding + directions on an API key (mgdio.auth.maps)
├── ynab/              # budgets, accounts, categories, transactions
├── whoop/             # recovery, sleep, workouts, cycles, profile, body
├── settings.py
└── cli.py
```

Each provider exposes the same triple: `get_credentials()`,
`clear_stored_token()`, `reset_credentials_cache()`. (For Google these are
profile-aware: `get_credentials(profile=…)` and `clear_stored_token(profile)`.)

## One-time Google Cloud Console setup

You only do this once per Google account.

1. **Create or pick a project** at <https://console.cloud.google.com>.
2. **Enable the APIs** under *APIs & Services → Library*:
   - Gmail API
   - Google Calendar API
   - Google Sheets API
   - Google Drive API
3. **Configure the app** under *Google Auth Platform* in the left nav.
   The *Branding / Audience / Data Access* sidebar only appears once your
   project has an OAuth client — if you don't see it, open *APIs & Services →
   Credentials* and click any entry under *OAuth 2.0 Client IDs* (create one
   via step 4 first if the list is empty) to land on *Google Auth Platform*.
   - **Branding** — fill in app name and support email.
   - **Audience** — set User type to **External**, add yourself under
     *Test users*, then click **Publish app**. *Critical:* apps left in
     *Testing* mode have their refresh tokens revoked every 7 days.
   - **Data Access** — click *Add or remove scopes* and add all four:
     - `https://www.googleapis.com/auth/gmail.modify`
     - `https://www.googleapis.com/auth/calendar`
     - `https://www.googleapis.com/auth/spreadsheets`
     - `https://www.googleapis.com/auth/drive`
4. **Create an OAuth client ID** under *Google Auth Platform → Clients →
   Create client*:
   - Application type: **Desktop app**.
   - Click *Download JSON*. (You'll drop this into the mgdio setup page in a moment;
     no manual filesystem work.)

> **Already have a client but lost the JSON?** Google won't re-download the
> *original* secret, but you can mint a fresh one. Open the existing client
> under *APIs & Services → Credentials → OAuth 2.0 Client IDs*, then under
> *Client secrets* click **Add secret**. The new secret row has a **download
> (⬇) button** — click it to get a ready-made `client_secret.json` and drop
> that into the mgdio setup page. No need to create a new client or hand-build
> any JSON.

## Install

### Install into another project (from GitHub)

`mgdio` isn't on PyPI yet; install directly from this repo.

**With `uv` (recommended)** — from inside your target project:

```powershell
# HTTPS (works without an SSH key)
uv add "git+https://github.com/mdinunzio/mgdio.git"

# SSH (if your GitHub SSH key is set up)
uv add "git+ssh://git@github.com/mdinunzio/mgdio.git"

# Pin to a specific branch, tag, or commit
uv add "git+https://github.com/mdinunzio/mgdio.git@main"
uv add "git+https://github.com/mdinunzio/mgdio.git@v0.1.0"
uv add "git+https://github.com/mdinunzio/mgdio.git@<commit-sha>"

# Include an optional DataFrame backend for Sheets
uv add "mgdio[sheets-pandas] @ git+https://github.com/mdinunzio/mgdio.git"
uv add "mgdio[sheets-polars] @ git+https://github.com/mdinunzio/mgdio.git"
```

**With plain `pip`**:

```powershell
pip install "git+https://github.com/mdinunzio/mgdio.git"
pip install "git+ssh://git@github.com/mdinunzio/mgdio.git"

# Pin to a branch / tag / sha
pip install "git+https://github.com/mdinunzio/mgdio.git@main"

# With an extra
pip install "mgdio[sheets-pandas] @ git+https://github.com/mdinunzio/mgdio.git"
```

After install, `mgdio` is importable and the `mgdio` console script is on
your PATH:

```powershell
python -c "from mgdio.auth.google import get_credentials; print('OK')"
mgdio --help
```

Upgrading later (re-fetches the latest commit on the requested ref):

```powershell
uv add --upgrade "git+https://github.com/mdinunzio/mgdio.git"
# or
pip install --upgrade --force-reinstall "git+https://github.com/mdinunzio/mgdio.git"
```

### Making `mgdio` callable from anywhere

If you want to type `mgdio gmail list --max 5` directly — without `uv run` or
activating a venv — install mgdio as a **tool** rather than a project
dependency:

```powershell
# Recommended (uv): isolated, on PATH, upgradable
uv tool install "git+https://github.com/mdinunzio/mgdio.git"

# Or pipx (same idea, different tool)
pipx install "git+https://github.com/mdinunzio/mgdio.git"
```

Both place `mgdio` on your global PATH inside an isolated environment.
Upgrade with `uv tool upgrade mgdio` (or `pipx upgrade mgdio`).

**Other invocations**:

```powershell
# Inside a uv project that depends on mgdio:
uv run mgdio gmail list --max 5

# Inside an activated venv (also works without uv):
python -m mgdio gmail list --max 5
mgdio gmail list --max 5            # if the venv's Scripts/bin is on PATH
```

`python -m mgdio ...` is provided by [mgdio/__main__.py](mgdio/__main__.py)
and is equivalent to the `mgdio` console script.

### Develop on this repo

Clone first, then editable-install with the dev extra:

```powershell
git clone git@github.com:mdinunzio/mgdio.git
cd mgdio
uv sync --extra dev
uv pip install -e .
```

`uv pip install -e .` registers the `mgdio` console script so
`uv run mgdio ...` works during development.

## First-run auth

```powershell
uv run mgdio auth google --profile mdinunziosvc
```

`--profile <slug>` names the Google account (slug = lowercase letters, digits,
`-`, `_`). A localhost setup page opens in your browser. Drag-and-drop the
`client_secret.json` you downloaded above, click **Authorize**, and approve the
single consent screen covering all four Google scopes. The resulting token is
written to your OS credential vault under `mgdio:google:<slug>`; future calls
read from the vault and refresh transparently. With only one profile
configured, you never have to name it again — see
[Multiple Google accounts](#multiple-google-accounts-profiles).

To force a fresh consent flow for that profile (e.g. after rotating
credentials or changing scopes):

```powershell
uv run mgdio auth google --profile mdinunziosvc --reset
```

### Checking what's authenticated

`mgdio auth status` reports, at a glance, which providers are set up on this
machine and what's left to do (it only reads the keyring — no network calls,
no setup flows triggered):

```powershell
uv run mgdio auth status
```

```text
[x] google  1 profile(s): mdinunziosvc
[x] ynab    token stored
[x] whoop   token stored
[ ] maps    not authenticated

To authenticate the remaining provider(s):
  mgdio auth maps
```

### Headless install (Linux VPS, SSH-only machines)

On a machine without a browser — a Linux VPS, a container, or any
environment where `webbrowser.open()` is a no-op — pass `--headless`
(still with `--profile`):

```bash
mgdio auth google --profile mdinunziosvc --headless
```

mgdio prints the Google authorization URL on the terminal. You open it
on **any** device that has a browser (your laptop, your phone), grant
consent, and Google redirects to `http://localhost/?state=...&code=...`.
That redirect **will fail to load** in your browser because nothing's
listening on `localhost` over there — **this is expected**. Copy
the entire failed-redirect URL out of the address bar, paste it back
into the VPS terminal, and press Enter. mgdio extracts the auth code,
exchanges it for credentials, and stores them in the keyring as usual.

If `client_secret.json` isn't on the VPS yet, mgdio prompts you to
paste the JSON contents on stdin (end with a blank line). Or, if you
prefer, `scp` it ahead of time to:

- Linux: `~/.local/share/mgdio/google/client_secret.json`
- macOS: `~/Library/Application Support/mgdio/google/client_secret.json`

Once authenticated, every subsequent `mgdio gmail / sheets / calendar / drive`
call reads the cached token from the keyring — no further interaction.

> **Linux keyring — handled automatically.** A minimal VPS image often
> has no Secret Service daemon (`gnome-keyring`, `kwallet`,
> `dbus-secret-service`), so the OS `keyring` can't store a token. mgdio
> detects this at startup and **falls back to a file-based store on its
> own** — no manual backend setup, no `PYTHON_KEYRING_BACKEND`, no
> `.bashrc` edits. The fallback backends (`keyrings.alt`) install
> automatically on Linux as a dependency.
>
> By default the fallback store is **unencrypted** (a file at
> `~/.local/share/mgdio/keyring/mgdio_plaintext.cfg`, `chmod 600` and
> re-locked after every write, inside a `chmod 700` dir). This is
> deliberate: it never prompts for a password, so **cron and other
> unattended jobs work without hanging**. mgdio logs a one-time `WARNING`
> **only when it writes a credential** (i.e. during `mgdio auth ...`) —
> read-only commands like `mgdio drive list` stay silent, so your normal
> functionality and cron logs aren't cluttered.
>
> If you'd rather encrypt it, set `MGDIO_KEYRING_PLAINTEXT=0`. mgdio then
> uses an encrypted file backend — but note it prompts for the encryption
> password on **every** process, so it's unsuitable for cron. To force a
> specific backend yourself, set `PYTHON_KEYRING_BACKEND` (or
> `MGDIO_KEYRING_BACKEND`) and mgdio won't override your choice.
>
> **Cron tip:** because the default needs no password and no shell-rc
> setup, a cron entry is just the absolute path to the `mgdio` binary —
> e.g. `*/15 * * * * /path/to/venv/bin/mgdio drive list --max 5`. No
> environment wiring required.

## Where credentials live

- **OAuth token**: OS credential vault under service `mgdio:google:<profile>`,
  username `oauth_token` (one entry per Google account). On Windows: *Credential
  Manager → Windows Credentials*; macOS: *Keychain*; Linux: *Secret Service*. On
  a headless Linux box with no Secret Service, mgdio falls back to a `chmod 600`
  file at `~/.local/share/mgdio/keyring/mgdio_plaintext.cfg` (see the
  [Linux keyring callout](#headless-install-linux-vps-ssh-only-machines)).
- **Profile index**: the list of known profile slugs lives at
  `~/.local/share/mgdio/google/profiles.json` (keyring has no portable list
  API). The keyring remains the source of truth for the token bytes.
- **`client_secret.json`**: a single shared file (app identity, not per-account)
  at the platform-appropriate path:
  - Windows: `%LOCALAPPDATA%\mgdio\google\client_secret.json`
  - macOS: `~/Library/Application Support/mgdio/google/client_secret.json`
  - Linux: `~/.local/share/mgdio/google/client_secret.json`

This is application configuration, not a per-session secret.

## Multiple Google accounts (profiles)

mgdio holds one OAuth token per Google account, each named by a *profile* slug
and stored at `mgdio:google:<slug>`. There is no stored "default" — which
profile a given environment uses is set by the `MGDIO_GOOGLE_PROFILE` env var
(e.g. in a project's `.env`).

```powershell
# Authorize two accounts
uv run mgdio auth google --profile personal
uv run mgdio auth google --profile mdinunziosvc

# List configured profiles (marks the env-default and the auto-selected one)
uv run mgdio auth google profiles

# Remove credentials when cleaning up (confirms unless --yes)
uv run mgdio auth google remove --profile personal
uv run mgdio auth google remove --legacy    # the pre-profiles mgdio:google token
uv run mgdio auth google remove --all        # every profile + legacy

# Use a specific profile for one command
uv run mgdio drive list --profile mdinunziosvc --max 5

# Or set a default for the whole environment (.env or shell)
$env:MGDIO_GOOGLE_PROFILE = "mdinunziosvc"
uv run mgdio gmail list --max 5            # uses mdinunziosvc
```

**Profile resolution waterfall** (most specific wins), applied to every Google
call:

1. An explicit `--profile <slug>` (CLI) or `profile="<slug>"` (Python).
2. The `MGDIO_GOOGLE_PROFILE` env var.
3. The sole profile, if exactly one is configured (so single-account use is
   zero-config).
4. Otherwise an error telling you to pick one.

A missing/typo'd profile raises a clear error rather than silently using the
wrong account. In Python, every Google function takes an optional trailing
`profile=` keyword:

```python
from mgdio.drive import list_files
from mgdio.gmail import send_email

list_files(max_results=5, profile="mdinunziosvc")
send_email(to="a@b.com", subject="hi", body="…", profile="personal")
# Omit profile= to use the env var / sole profile.
```

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

## Drive

After `mgdio auth google`, Drive is ready too. Public API covers listing /
searching, file metadata, creating folders, uploading, downloading (binary
files) / exporting (Google-native Docs/Sheets/Slides), renaming, moving,
copying, trashing / restoring, permanent delete, emptying trash, and sharing
(list / grant / update / revoke permissions).

> **One-time re-consent.** Drive added a new OAuth scope
> (`https://www.googleapis.com/auth/drive`). If you authorized *before* Drive
> landed, your stored token won't carry it — the first Drive call falls back to
> the setup flow. Run `mgdio auth google --profile <slug> --reset` and
> re-approve the consent screen (now showing the Drive scope) once.

```python
from pathlib import Path

from mgdio.drive import (
    list_files, fetch_file, create_folder, upload_file,
    download_file, export_file, update_file, move_file, copy_file,
    trash_file, delete_file, empty_trash,
    list_permissions, share_file, update_permission, unshare_file,
)

# List / search. Listing auto-paginates up to max_results.
recent = list_files(order_by="modifiedTime desc", max_results=10)
for f in recent:
    print("DIR " if f.is_folder else "FILE", f.name, f.id)

# `query` is the raw Drive `q` parameter.
pdfs = list_files(query="mimeType='application/pdf'", max_results=20)
hits = list_files(query="name contains 'invoice'")
children = list_files(parent_id="<folder_id>")          # contents of a folder
trashed = list_files(include_trashed=True)              # include trashed items

# Metadata for one file.
meta = fetch_file("<file_id>")
print(meta.name, meta.size_bytes, meta.modified_time, meta.web_view_link)

# Create a folder (optionally nested under a parent).
folder = create_folder("Reports", parent_id="<parent_folder_id>")

# Upload a local file into the folder.
up = upload_file(Path("report.pdf"), name="Q1.pdf", parent_id=folder.id)

# Download a BINARY file's content to disk.
download_file(up.id, Path("./Q1-local.pdf"))

# Google-native docs (Docs/Sheets/Slides) have NO raw bytes -- export instead.
export_file("<google_doc_id>", Path("./out.pdf"), mime_type="application/pdf")
export_file("<google_sheet_id>", Path("./out.csv"), mime_type="text/csv")

# Rename / star (update_file leaves unspecified fields untouched).
update_file(up.id, name="Q1-final.pdf")
update_file(up.id, starred=True)

# Move (re-parents: removes the old parent by default), copy.
move_file(up.id, "<new_folder_id>")
copy_file(up.id, name="Q1-copy.pdf", parent_id=folder.id)

# Trash is recoverable; delete is PERMANENT (skips the trash).
trash_file(up.id)                  # recoverable
trash_file(up.id, trashed=False)   # restore
delete_file(up.id)                 # irreversible
empty_trash()                      # irreversible

# Sharing. Exactly one grantee: email, domain, or anyone-with-the-link.
perm = share_file(folder.id, role="reader", email="alice@example.com")
share_file(folder.id, role="writer", anyone=True)
share_file(folder.id, role="reader", domain="example.com")
for p in list_permissions(folder.id):
    print(p.role, p.type, p.email_address or p.domain or p.type, p.id)
update_permission(folder.id, perm.id, role="writer")
unshare_file(folder.id, perm.id)
```

CLI equivalents:

```powershell
uv run mgdio drive list --max 25
uv run mgdio drive list --query "name contains 'invoice'" --max 10
uv run mgdio drive list --parent <folder_id>
uv run mgdio drive get <file_id>
uv run mgdio drive mkdir "Reports" --parent <folder_id>
uv run mgdio drive upload ./report.pdf --name "Q1.pdf" --parent <folder_id>
uv run mgdio drive download <file_id> ./local.pdf
uv run mgdio drive export <doc_id> ./out.pdf --mime application/pdf
uv run mgdio drive rename <file_id> "new name.pdf"
uv run mgdio drive move <file_id> <new_parent_folder_id>
uv run mgdio drive copy <file_id> --name "copy" --parent <folder_id>
uv run mgdio drive trash <file_id>            # recoverable
uv run mgdio drive trash <file_id> --restore  # un-trash
uv run mgdio drive delete <file_id>           # PERMANENT
uv run mgdio drive empty-trash                # PERMANENT
uv run mgdio drive perms <file_id>
uv run mgdio drive share <file_id> --role reader --email alice@example.com
uv run mgdio drive unshare <file_id> <permission_id>
```

## Maps

Google Maps uses an **API key**, not the shared Google OAuth login. Run
`mgdio auth maps` once: a localhost setup page walks you through creating a key
in the Cloud Console (enable the **Geocoding API** and **Directions API**;
billing must be enabled, even for the free tier), then validates the pasted key
with a test geocode and stores it in your keyring under `mgdio:maps`. On a
machine without a browser, use `mgdio auth maps --headless` to paste the key on
the terminal instead. This covers the common `GOOGLEMAPS_*` Google Sheets
helpers.

```python
from mgdio.maps import geocode, reverse_geocode, fetch_route

# Address / place -> coordinates (list, best match first).
hit = geocode("10 Hanover Square, NY")[0]
print(hit.formatted_address, hit.latitude, hit.longitude)
print(hit.latlng)                       # "40.70..., -74.01..." (Sheets-style)

# Formatted address of a place.
print(geocode("Statue of Liberty")[0].formatted_address)

# Coordinate -> postal address.
print(reverse_geocode(40.7127753, -74.0059728)[0].formatted_address)

# Distance / duration / directions between two locations.
route = fetch_route("NY 10005", "Hoboken NJ", mode="driving")  # or walking/…
print(route.distance_text, route.duration_text)   # "5.2 mi" "12 mins"
print(route.distance_meters, route.duration_seconds)  # raw SI, always present
print(route.distance_miles, route.duration_minutes)   # converted numbers
for step in route.instructions:                   # HTML-stripped steps
    print(step)
```

`fetch_route` returns the best route and raises `MgdioAPIError` if none exists
(matching the Sheets "No route found!" behavior); `fetch_routes(...)` returns a
list (empty on no result) and takes `alternatives=True`. `mode` is
`driving` (default), `walking`, `bicycling`, or `transit`; `units` is
`imperial` (default) or `metric` and only affects the `*_text` fields.

CLI equivalents:

```powershell
uv run mgdio maps geocode "10 Hanover Square, NY"
uv run mgdio maps reverse "40.714,-74.006"    # one "lat,lng" token
uv run mgdio maps distance "NY 10005" "Hoboken NJ"
uv run mgdio maps duration "NY 10005" "Hoboken NJ" --mode walking
uv run mgdio maps directions "NY 10005" "Hoboken NJ"
```

## YNAB

YNAB uses a personal access token (not OAuth). Run `mgdio auth ynab` once and
a localhost setup page opens with instructions for minting a token at
<https://app.ynab.com/settings/developer>. Paste it into the page; mgdio
validates it against `GET /v1/user` before saving to your OS keyring under
`mgdio:ynab`. On a browserless machine, use `mgdio auth ynab --headless` to
paste the token on the terminal instead.

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

## Whoop

Whoop uses OAuth 2.0 (authorization-code flow). Run `mgdio auth whoop` once
and a localhost setup page walks you through it.

**One-time Whoop developer-app setup:**

1. Open <https://developer-dashboard.whoop.com> and sign in with your Whoop account.
2. Create a **Team**, then create an **App**.
3. Set the app's **Redirect URI** to exactly
   `http://localhost:8765/callback` (the default — see the override note
   below if you want a different port).
4. Select the scopes: `offline read:recovery read:sleep read:workout
   read:cycles read:profile read:body_measurement` (the `offline` scope is
   required so mgdio gets a refresh token).
5. Copy the **Client ID** and **Client Secret**.

Then `mgdio auth whoop` opens a page where you paste the Client ID +
Secret (saved to the keyring under `mgdio:whoop`), click **Authorize with
Whoop**, and approve. The resulting access+refresh token bundle is stored
and **refreshed automatically** on expiry — no further interaction.

> **Redirect URI override.** The callback defaults to
> `http://localhost:8765/callback`. To use a different port/path, set
> `MGDIO_WHOOP_REDIRECT_URI` in your environment or `.env` **and** register
> the same value in your Whoop app. The setup page always shows the
> effective value.

The data API is **read-only**. Money-free, SI units; HRV in milliseconds,
energy in kilojoules (`Workout.calories` converts to kcal), distance in
meters. All collection fetches auto-paginate up to `max_records`.

```python
from datetime import datetime, timedelta, timezone

from mgdio.whoop import (
    fetch_recoveries, fetch_sleeps, fetch_workouts, fetch_cycles,
    fetch_profile, fetch_body_measurement,
)

# Profile + body
me = fetch_profile()
body = fetch_body_measurement()

# Recovery is a MORNING metric -- a record appears after the night's
# sleep cycle closes, so "today" may be empty before you wake up.
for r in fetch_recoveries(max_records=7):
    print(r.created_at, r.recovery_score, r.hrv_rmssd_milli, r.resting_heart_rate)

# Sleep, workouts, cycles -- same signature; start/end must be tz-aware.
now = datetime.now(timezone.utc)
recent_sleep = fetch_sleeps(start=now - timedelta(days=7), max_records=25)
for w in fetch_workouts(max_records=10):
    print(w.sport_name, w.strain, w.calories)   # calories = kJ / 4.184
```

CLI equivalents:

```powershell
uv run mgdio whoop profile
uv run mgdio whoop body
uv run mgdio whoop recoveries --max 7
uv run mgdio whoop sleeps --max 7
uv run mgdio whoop workouts --max 7
uv run mgdio whoop cycles --max 7
# Bounded (tz-aware ISO datetimes):
uv run mgdio whoop sleeps --start "2026-05-01T00:00:00-04:00" `
  --end "2026-05-12T00:00:00-04:00" --max 25
```

## Building your own Google API client

If you need a different Google API that doesn't have a subpackage yet, the
shared auth is one call away:

```python
from googleapiclient.discovery import build

from mgdio.auth.google import get_credentials

service = build("docs", "v1", credentials=get_credentials(),
                cache_discovery=False)
```

No scopes argument, no per-service auth dance.

## Claude Code skills

`mgdio` ships with seven [Claude Code](https://claude.com/claude-code) skills
— one per service — that teach Claude how to drive the CLI for you. Once
deployed, you can ask Claude things like *"list my 5 most recent emails,"
"what's on my calendar this week," "edit transaction abc-123's memo to
'grocery run,'" "upload this file to my Reports folder in Drive," "how far is
it from here to the airport,"* or *"write this data to row 2 of my budget
sheet,"* and it'll reach for `mgdio` instead of inventing API calls from
scratch.

```powershell
# Preview what's bundled
mgdio skills list

# Deploy to the CURRENT project (./.claude/skills/)
mgdio skills deploy

# Deploy GLOBALLY (~/.claude/skills/), so every project sees the skills
mgdio skills deploy --global

# Re-deploy after a mgdio upgrade
mgdio skills deploy --force
```

After deploying, restart Claude Code or run `/clear` to load the skills.

The bundled skills are:

- **`mgdio-gmail`** — list / search / read / send email.
- **`mgdio-sheets`** — read / write / append / clear values, manage tabs,
  create spreadsheets.
- **`mgdio-calendar`** — list calendars, list / fetch / create / update /
  delete events, natural-language quick-add.
- **`mgdio-drive`** — list / search files, get metadata, create folders,
  upload / download / export, rename / move / copy, trash / delete, and
  manage sharing permissions.
- **`mgdio-ynab`** — list budgets / accounts / categories / transactions,
  edit a transaction's memo, cleared status, flag, or category.
- **`mgdio-whoop`** — read recovery, sleep, workouts, cycles, profile, and
  body measurements (read-only).
- **`mgdio-maps`** — geocode addresses, reverse-geocode coordinates, and
  compute distance / duration / directions between locations (read-only).

**Safety contract**: every skill instructs Claude that reads are
auto-fine but writes (sending email, creating/updating/deleting events,
writing to sheets, editing YNAB transactions, uploading/moving/deleting
Drive files, changing sharing) **must be confirmed with you before
invocation**. Drive's `delete` and `empty-trash` are flagged as
irreversible, so Claude is told to prefer the recoverable `trash`. Claude paraphrases the action and waits for
your explicit approval — even if the conversation sounded like
permission was implicit. Writes are never chained without re-confirming.

## Quick test commands

End-to-end walkthrough of the new auth flow (PowerShell). Run these from the
project root after completing the one-time Cloud Console setup above.

```powershell
# 1. Install deps + editable mgdio
uv sync --extra dev
uv pip install -e .

# 2. Confirm the CLI surface
uv run mgdio --help                       # shows the `auth` group
uv run mgdio auth --help                  # shows the `google` subcommand
uv run mgdio auth google --help           # shows --profile / --reset / --headless

# 3. Run the unit suite (no real APIs touched)
uv run pytest -ra

# 4. First-time setup: drag-and-drop client_secret.json, then Authorize
uv run mgdio auth google --profile svc    # opens browser, completes consent
# Expect: "Authenticated profile 'svc'." printed when consent finishes
uv run mgdio auth google profiles         # lists configured profiles

# 5. Verify the on-disk + vault state landed where expected
Get-ChildItem $env:LOCALAPPDATA\mgdio\google\
# Expect: client_secret.json and profiles.json present

# Inspect the OS keyring entry from Python (per-profile service)
uv run python -c "import keyring; t = keyring.get_password('mgdio:google:svc', 'oauth_token'); print('present:', bool(t), 'len:', len(t or ''))"
# Expect: present: True, len: 500+ (a JSON blob)

# 6. Confirm the cached token actually carries all four scopes
uv run python -c "from mgdio.auth.google import get_credentials; c = get_credentials('svc'); print('valid:', c.valid); [print(' -', s) for s in sorted(c.scopes)]"
# Expect four URLs: gmail.modify, calendar, spreadsheets, drive

# 7. Second call is cheap: no browser, no prompt -- hits in-process cache
uv run python -c "from mgdio.auth.google import get_credentials; get_credentials('svc'); print('OK')"

# 8. Verify cross-process persistence: new Python, still no prompt
uv run python -c "from mgdio.auth.google import get_credentials; c = get_credentials('svc'); print('valid (from keyring):', c.valid)"

# 9. Reset and re-auth (forces a fresh consent flow for that profile)
uv run mgdio auth google --profile svc --reset   # opens browser again

# 10. Inspect Credential Manager visually (optional)
#     Start -> "Credential Manager" -> Windows Credentials -> search "mgdio:google:svc"
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

### Drive quick-test commands

After step 4 above, exercise the Drive surface. These create a throwaway
folder + file and clean up after themselves. If you authorized before the
Drive scope was added, run `uv run mgdio auth google --profile svc --reset` first.

```powershell
# Smoke: import the public Drive API
uv run python -c "from mgdio.drive import list_files, upload_file, create_folder, share_file, DriveFile; print('imports OK')"

# List your 10 most recently modified files
uv run mgdio drive list --order "modifiedTime desc" --max 10

# Search with raw Drive query syntax
uv run mgdio drive list --query "name contains 'mgdio'" --max 5

# Create a throwaway folder and capture its id
$fid = (uv run mgdio drive mkdir "mgdio-smoke" | Select-String "\[" | ForEach-Object { ($_ -split "[][]")[1] })
Write-Output "folder id: $fid"

# Upload a small file into it
"hello from mgdio drive" | Out-File -Encoding utf8 drive_smoke.txt
$gid = (uv run mgdio drive upload drive_smoke.txt --parent $fid | Select-String "\[" | ForEach-Object { ($_ -split "[][]")[1] })
Write-Output "file id: $gid"

# List the folder's contents
uv run mgdio drive list --parent $fid

# Metadata + download the content back
uv run mgdio drive get $gid
uv run mgdio drive download $gid drive_roundtrip.txt
Get-Content drive_roundtrip.txt

# Share with anyone who has the link, then inspect permissions
uv run mgdio drive share $gid --role reader --anyone
uv run mgdio drive perms $gid

# Clean up (delete the folder + its contents; PERMANENT)
uv run mgdio drive delete $fid
Remove-Item drive_smoke.txt, drive_roundtrip.txt

# End-to-end demo (creates its own throwaway folder + cleans up)
uv run python examples/drive_demo.py

# Opt-in real-API integration tests
$env:MGDIO_RUN_INTEGRATION = "1"
uv run pytest tests/drive/test_integration.py -ra
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

### Maps quick-test commands

Maps has its own API key (not the Google OAuth login).

```powershell
# 1. Create a key + paste it via the setup page (enable Geocoding + Directions)
uv run mgdio auth maps
# Expect: "Authenticated." once the page verifies the key.

# 2. Confirm the key landed in the OS keyring
uv run python -c "import keyring; k = keyring.get_password('mgdio:maps', 'api_key'); print('present:', bool(k))"

# 3. Smoke: import the public Maps API
uv run python -c "from mgdio.maps import geocode, reverse_geocode, fetch_route, GeocodeResult, Route; print('imports OK')"

# 4. Geocode + reverse-geocode
uv run mgdio maps geocode "10 Hanover Square, NY"
uv run mgdio maps reverse "40.714,-74.006"

# 5. Distance / duration / directions
uv run mgdio maps distance "NY 10005" "Hoboken NJ"
uv run mgdio maps duration "NY 10005" "Hoboken NJ" --mode walking
uv run mgdio maps directions "NY 10005" "Hoboken NJ"

# 6. End-to-end demo
uv run python examples/maps_demo.py

# 7. Reset and re-auth (forces a fresh paste flow)
uv run mgdio auth maps --reset
```

## Troubleshooting

- **Refresh token expired / revoked** — verify the Google Auth Platform consent
  screen is *Published*, then `mgdio auth google --profile <slug> --reset`.
- **`no Google profiles` / `multiple Google profiles` error** — pick an account:
  pass `--profile <slug>` (or set `MGDIO_GOOGLE_PROFILE`), or authorize one with
  `mgdio auth google --profile <slug>`. List existing ones with
  `mgdio auth google profiles`.
- **Scope mismatch after upgrade** — if a future release adds a new Google scope,
  the first call will fall back to the setup flow. Approve the new scope on the
  consent screen.
- **Test the package without Google APIs** — `uv run pytest -ra`. The unit suite
  uses an in-memory keyring fixture and never touches your real vault.
- **YNAB token rejected** — `mgdio auth ynab --reset` to paste a new one. The
  setup page calls `GET /v1/user` before saving so common typos surface
  immediately instead of on first use.
- **Maps `REQUEST_DENIED`** — the API key is invalid, or the Geocoding /
  Directions API isn't enabled for its project, or billing isn't enabled on the
  project. Fix it in the Cloud Console, then `mgdio auth maps --reset`.
- **Maps `reverse` says "No such option"** — pass the coordinate as a single
  quoted `"lat,lng"` token (e.g. `"40.714,-74.006"`) so the negative longitude
  isn't parsed as a CLI option.
- **`mismatching_state` in `--headless` mode** — you pasted a redirect URL
  from a *different* mgdio session. State is rotated every run; finish the
  paste in the same terminal session that printed the auth URL. Re-run
  `mgdio auth google --profile <slug> --headless` and try again.
- **`keyring.errors.NoKeyringError` on a Linux VPS** — mgdio normally
  handles this automatically by falling back to a file-based store (see
  the keyring callout in [Headless install](#headless-install-linux-vps-ssh-only-machines)).
  If you still hit it, the `keyrings.alt` dependency may be missing
  (`pip install keyrings.alt`) or a stale `PYTHON_KEYRING_BACKEND` env var
  is forcing an unusable backend — unset it and let mgdio choose.
- **Headless auth hangs on a keyring password prompt** — you have
  `MGDIO_KEYRING_PLAINTEXT=0` (or an `EncryptedKeyring` env var) set, which
  prompts for a password every run and blocks cron. Unset it to use the
  default no-prompt plaintext fallback.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the current backlog. Next up: Twilio (SMS +
voice) following the YNAB paste-token UX.
