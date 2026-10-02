# mgdio

**Personal connectivity tools you can `uv add` into any Python project.**
One install, one auth command per provider, then a handful of plain functions
for Gmail, Google Sheets, Google Calendar, Google Drive, Google Maps, YNAB, and
Whoop. Tokens live in your OS credential vault and refresh themselves, so a
script that works today still works in six months, including from cron.

## Quick start

Three steps from an empty project to your inbox.

### 1. Install

```bash
uv add "git+https://github.com/mdinunzio/mgdio.git"
```

`pip install "git+https://github.com/mdinunzio/mgdio.git"` works too. Pinning,
extras, and a global `mgdio` command are covered in [Installation](install.md).

### 2. Authenticate once

All Google services share a single login. The first run needs a
`client_secret.json` from Google Cloud Console (a *Desktop app* OAuth client
with the consent screen **published**). That takes about five minutes and is
spelled out step by step in
[Google Cloud Console setup](auth.md#google-cloud-console-setup). With the
file downloaded:

```bash
uv run mgdio auth google --profile me
```

A setup page opens in your browser. Drag in `client_secret.json`, click
**Authorize**, and approve the consent screen. The token is stored in your OS
keyring under `mgdio:google:me` and refreshes transparently from now on.

!!! tip "No browser on this machine?"
    Add `--headless` to run a copy-paste flow from a Linux VPS or SSH
    session. See [Headless auth](auth.md#headless-auth).

### 3. Use it

From the shell:

```bash
uv run mgdio gmail list --max 5
```

Or from Python:

```python
from mgdio.gmail import fetch_messages

for message in fetch_messages(max_results=5):
    print(message.date, message.sender, message.subject)
```

That is the whole setup. Sheets, Calendar, and Drive were authorized by the same
consent screen, so they work immediately:

```python
from datetime import datetime, timedelta, timezone

from mgdio.calendar import fetch_events
from mgdio.drive import list_files
from mgdio.sheets import fetch_values

now = datetime.now(timezone.utc)
for event in fetch_events(time_min=now, time_max=now + timedelta(days=7)):
    print(event.start, event.summary)

rows = fetch_values("<spreadsheet_id>", "Sheet1!A1:C10")

for file in list_files(order_by="modifiedTime desc", max_results=10):
    print(file.name, file.id)
```

Check what is set up at any time with `mgdio auth status`.

## What's in the box

| Service | Auth | Import | Guide |
| --- | --- | --- | --- |
| Gmail | Google OAuth (shared) | `mgdio.gmail` | [Gmail](services/gmail.md) |
| Google Sheets | Google OAuth (shared) | `mgdio.sheets` | [Sheets](services/sheets.md) |
| Google Calendar | Google OAuth (shared) | `mgdio.calendar` | [Calendar](services/calendar.md) |
| Google Drive | Google OAuth (shared) | `mgdio.drive` | [Drive](services/drive.md) |
| Google Maps | API key | `mgdio.maps` | [Maps](services/maps.md) |
| YNAB | Personal access token | `mgdio.ynab` | [YNAB](services/ynab.md) |
| Whoop | OAuth 2.0 (auto-refresh) | `mgdio.whoop` | [Whoop](services/whoop.md) |

Every provider also has a CLI group (`mgdio gmail`, `mgdio sheets`, ...) and a
one-time `mgdio auth <provider>` command.

## How it is designed

- **Functions, not clients.** Each service is a module of plain functions that
  return frozen dataclasses. There is no object to construct or pass around.
- **Readable names.** `fetch_*` hits the network, `get_*` returns something
  cheap and cached, and everything else is a verb (`send_email`,
  `create_event`, `share_file`).
- **One consent for Google.** Gmail, Sheets, Calendar, and Drive share one
  OAuth client and one token per Google account. Multiple accounts are
  [profiles](auth.md#multiple-google-accounts-profiles).
- **Vault-backed, never plaintext.** Windows Credential Manager, macOS
  Keychain, or Linux Secret Service, with an automatic file fallback on
  headless Linux.
- **Safe when unattended.** A stale token on a cron host raises a clear error
  naming the `mgdio auth` command to run instead of hanging on a browser that
  will never open.

## Where next

- [Authentication](auth.md): Cloud Console setup, multiple accounts, headless
  flows, and where credentials live.
- The service guides in the sidebar, each with Python and CLI examples.
- [API reference](reference/index.md): every public function and dataclass,
  generated from the docstrings.
- [Claude Code skills](claude-skills.md): let Claude drive the CLI for you.
- The [`examples/`](https://github.com/mdinunzio/mgdio/tree/main/examples)
  folder on GitHub: runnable end-to-end demos for each service.
