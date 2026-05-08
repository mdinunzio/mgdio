# mgdio

Personal connectivity tools (Gmail, Sheets, Calendar, YNAB, Twilio, ...) packaged
so they can be `pip` / `uv add`-ed into any other project with a uniform API.

**Current status:** Gmail (read + send) only. Other services to come.

## Why another wrapper

- **Stable auth** — OAuth refresh tokens that don't expire (consent-screen
  *Published* in Google Cloud Console; see step 2 below).
- **Native APIs** — Google's official `google-api-python-client`, not SMTP/IMAP.
- **No paid Workspace required** — works against a personal `@gmail.com`.
- **Credentials live in the OS credential vault** — Windows Credential Manager,
  macOS Keychain, or Linux Secret Service. No plaintext token files.

## One-time Google Cloud Console setup

You only do this once per Google account.

1. **Create or pick a project** at <https://console.cloud.google.com>.
2. **Enable the Gmail API**: *APIs & Services → Library → Gmail API → Enable*.
3. **Configure the OAuth consent screen** (*APIs & Services → OAuth consent screen*):
   - User type: **External**.
   - Fill in app name + your email.
   - Add scope `https://www.googleapis.com/auth/gmail.modify`.
   - Add yourself as a test user.
   - **Click "Publish app"**. *Critical:* apps left in *Testing* mode have their
     refresh tokens revoked every 7 days.
4. **Create an OAuth client ID** (*APIs & Services → Credentials → Create
   Credentials → OAuth client ID*):
   - Application type: **Desktop app**.
   - Click *Download JSON*.
5. **Drop the file** at the path `mgdio` will print on first run, e.g.:
   - Windows: `%LOCALAPPDATA%\mgdio\client_secret.json`
   - macOS: `~/Library/Application Support/mgdio/client_secret.json`
   - Linux: `~/.local/share/mgdio/client_secret.json`

## Install

In any project that needs it:

```powershell
uv add mgdio
```

For development on this repo:

```powershell
uv sync --extra dev
uv pip install -e .
```

## First-run auth

```powershell
uv run mgdio auth
```

If `client_secret.json` is missing, a browser tab opens with the setup
instructions and the exact path to drop the JSON. Once the file is in place,
re-run the command — a Google consent screen opens, you approve, and the
resulting OAuth token is written to your OS credential vault. Future calls
read from the vault and refresh transparently.

## Quickstart

```python
from pathlib import Path

from mgdio.gmail import fetch_messages, send_email

# Read the 5 most recent messages.
for message in fetch_messages(max_results=5):
    print(message.date, message.sender, message.subject)

# Search using Gmail's query syntax.
results = fetch_messages(query="from:noreply@github.com after:2026/01/01")

# Send plain text.
send_email(
    to="someone@example.com",
    subject="hello",
    body="from mgdio",
)

# Send HTML + attachment.
send_email(
    to=["a@example.com", "b@example.com"],
    subject="report",
    body="see attached",
    html="<p>see <b>attached</b></p>",
    attachments=[Path("report.pdf")],
)
```

## CLI

```powershell
uv run mgdio auth                                             # force OAuth flow
uv run mgdio logout                                           # forget token
uv run mgdio gmail list --max 5                               # list inbox
uv run mgdio gmail list --query "from:foo@bar.com" --max 3
uv run mgdio gmail send --to me@example.com --subject hi --body body
```

## Where credentials live

- **OAuth token**: stored in your OS credential vault under the name `mgdio:gmail`
  (username `oauth_token`). On Windows you can inspect it via *Credential Manager
  → Windows Credentials*.
- **`client_secret.json`**: plain file in the platform-appropriate
  application-data directory (see paths in step 5 of setup above). This is
  application configuration, not a per-session secret.

## Troubleshooting

- **`MissingClientSecretError`** — drop `client_secret.json` at the path the
  error names, then re-run.
- **Refresh token expired / revoked** — verify your OAuth consent screen is
  *Published*, then `mgdio logout && mgdio auth`.
- **Wrong scopes** — `mgdio logout && mgdio auth` to re-consent.
- **Test the package without Google APIs** — run the unit suite:
  `uv run pytest -m "not integration"`. To exercise the real API end-to-end
  set `MGDIO_RUN_INTEGRATION=1` and run `uv run pytest -m integration`.

## Roadmap

Future subpackages, each with the same pattern (per-service auth + service
singleton + functional public API re-exported from `__init__`):

- `mgdio.sheets`
- `mgdio.calendar`
- `mgdio.ynab`
- `mgdio.twilio`
