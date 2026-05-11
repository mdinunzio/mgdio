# mgdio

Personal connectivity tools (Gmail, Calendar, Sheets, YNAB, Twilio, ...) packaged
so they can be `pip` / `uv add`-ed into any other project with a uniform API.

> **Status — auth foundation only.** This release ships the unified
> authentication subsystem. The previous Gmail surface has been removed and
> will return in follow-up PRs on top of [`mgdio.auth.google`](mgdio/auth/google/).

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
│   ├── google/        # Gmail + Calendar + Sheets (this PR)
│   ├── ynab/          # planned
│   └── twilio/        # planned
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

## Programmatic use (planned service subpackages)

When the service modules return in follow-up PRs, they'll call into the auth
subsystem like this:

```python
from googleapiclient.discovery import build

from mgdio.auth.google import get_credentials

service = build("gmail", "v1", credentials=get_credentials(),
                cache_discovery=False)
# ... or "calendar" v3, "sheets" v4 -- same credentials object
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

## Troubleshooting

- **Refresh token expired / revoked** — verify the Google Auth Platform consent
  screen is *Published*, then `mgdio auth google --reset`.
- **Scope mismatch after upgrade** — if a future release adds a new Google scope,
  the first call will fall back to the setup flow. Approve the new scope on the
  consent screen.
- **Test the package without Google APIs** — `uv run pytest -ra`. The unit suite
  uses an in-memory keyring fixture and never touches your real vault.

## Roadmap

Future subpackages, each per the same auth pattern:

- `mgdio.gmail` (return on top of `mgdio.auth.google`)
- `mgdio.calendar`
- `mgdio.sheets`
- `mgdio.auth.ynab` + `mgdio.ynab`
- `mgdio.auth.twilio` + `mgdio.twilio`
