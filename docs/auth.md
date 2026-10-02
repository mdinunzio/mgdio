# Authentication

mgdio's auth subsystem exists so that every other module can be a plain
function call. The design goals, in priority order:

- **Stable.** OAuth refresh tokens that do not expire (Google consent screen
  *Published*), long-lived personal tokens where the provider offers them.
- **Native.** Official provider APIs, not SMTP or IMAP.
- **Free.** Works against a personal `@gmail.com`; no Workspace account.
- **Vault-backed.** Tokens live in Windows Credential Manager, macOS Keychain,
  or Linux Secret Service. No plaintext token files.
- **Unattended-safe.** A missing or dead token on a cron host raises a clear
  error instead of blocking forever on a browser.

Each provider exposes the same triple: `get_credentials()` (or the provider's
equivalent such as `get_token()` / `get_api_key()`), `clear_stored_token()`,
and `reset_credentials_cache()`.

| Provider | Flow | Keyring service | Command |
| --- | --- | --- | --- |
| Google (Gmail, Sheets, Calendar, Drive) | OAuth, one consent for all four | `mgdio:google:<profile>` | `mgdio auth google --profile <slug>` |
| Google Maps | API key pasted into a setup page | `mgdio:maps` | `mgdio auth maps` |
| YNAB | Personal access token pasted into a setup page | `mgdio:ynab` | `mgdio auth ynab` |
| Whoop | OAuth 2.0 code flow, auto-refresh | `mgdio:whoop` | `mgdio auth whoop` |

Maps, YNAB, and Whoop setup is described on their service pages. The rest of
this page is about Google, which has the most moving parts.

## Google Cloud Console setup

You do this once per Google account.

1. **Create or pick a project** at <https://console.cloud.google.com>.
2. **Enable the APIs** under *APIs & Services → Library*: Gmail API, Google
   Calendar API, Google Sheets API, Google Drive API.
3. **Configure the app** under *Google Auth Platform* in the left nav. (The
   *Branding / Audience / Data Access* sidebar only appears once the project
   has an OAuth client. If you do not see it, do step 4 first, then open the
   client under *APIs & Services → Credentials*.)
    - **Branding**: app name and support email.
    - **Audience**: User type **External**, add yourself under *Test users*,
      then click **Publish app**. *Critical:* apps left in *Testing* mode have
      their refresh tokens revoked every 7 days.
    - **Data Access**: *Add or remove scopes* and add all four:
        - `https://www.googleapis.com/auth/gmail.modify`
        - `https://www.googleapis.com/auth/calendar`
        - `https://www.googleapis.com/auth/spreadsheets`
        - `https://www.googleapis.com/auth/drive`
4. **Create an OAuth client ID** under *Google Auth Platform → Clients →
   Create client*. Application type **Desktop app**. Click *Download JSON*.

??? note "Already have a client but lost the JSON?"
    Google will not re-download the original secret, but you can mint a fresh
    one. Open the client under *APIs & Services → Credentials → OAuth 2.0
    Client IDs*, then under *Client secrets* click **Add secret**. The new row
    has a download button that yields a ready-made `client_secret.json`.

## First-run auth

```bash
uv run mgdio auth google --profile mdinunziosvc
```

`--profile <slug>` names the Google account (lowercase letters, digits, `-`,
`_`). A localhost setup page opens. Drag in the `client_secret.json` you
downloaded, click **Authorize**, and approve the single consent screen covering
all four scopes. The token is written to your OS vault under
`mgdio:google:<slug>`; later calls read it from there and refresh silently.

Force a fresh consent flow (after rotating credentials or when scopes change):

```bash
uv run mgdio auth google --profile mdinunziosvc --reset
```

### Checking what's authenticated

```bash
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

This only reads the keyring. It makes no network calls and triggers no setup
flows.

## Multiple Google accounts (profiles)

mgdio holds one token per Google account, each named by a profile slug. There
is no stored "default"; which profile an environment uses comes from the
`MGDIO_GOOGLE_PROFILE` env var (for example in a project's `.env`).

```bash
# Authorize two accounts
uv run mgdio auth google --profile personal
uv run mgdio auth google --profile mdinunziosvc

# List configured profiles
uv run mgdio auth google profiles

# Remove credentials (confirms unless --yes)
uv run mgdio auth google remove --profile personal
uv run mgdio auth google remove --legacy    # the pre-profiles mgdio:google token
uv run mgdio auth google remove --all

# Use a specific profile for one command
uv run mgdio drive list --profile mdinunziosvc --max 5

# Or set a default for the whole environment
export MGDIO_GOOGLE_PROFILE=mdinunziosvc
```

**Resolution waterfall**, applied to every Google call, most specific first:

1. An explicit `--profile <slug>` (CLI) or `profile="<slug>"` (Python).
2. The `MGDIO_GOOGLE_PROFILE` env var.
3. The sole profile, if exactly one is configured. Single-account use is
   zero-config.
4. Otherwise an error telling you to pick one.

A misspelled profile raises rather than silently using the wrong account. In
Python every Google function takes an optional trailing `profile=` keyword:

```python
from mgdio.drive import list_files
from mgdio.gmail import send_email

list_files(max_results=5, profile="mdinunziosvc")
send_email(to="a@b.com", subject="hi", body="...", profile="personal")
```

## Headless auth

On a machine without a browser (Linux VPS, container, SSH-only host):

```bash
mgdio auth google --profile mdinunziosvc --headless
```

mgdio prints the Google authorization URL. Open it on any device with a
browser, grant consent, and Google redirects to
`http://localhost/?state=...&code=...`. That page **fails to load** on the
browser device because nothing is listening there. That is expected. Copy the
entire failed-redirect URL from the address bar, paste it into the VPS
terminal, press Enter. mgdio exchanges the code and stores the token as usual.

If `client_secret.json` is not on the VPS yet, mgdio prompts you to paste the
JSON on stdin (end with a blank line). Or `scp` it ahead of time to the path
listed under [Where credentials live](#where-credentials-live).

The same `--headless` flag exists for `mgdio auth ynab`, `mgdio auth maps`,
and `mgdio auth whoop`.

### Unattended jobs never hang

If a token goes stale on a host where nobody can complete an auth flow, mgdio
raises `MgdioInteractionRequiredError` naming the exact `mgdio auth ...`
command to run, instead of waiting on a browser forever.

- Interactive flows are allowed only when stdin is a TTY by default.
- `MGDIO_NONINTERACTIVE=1` forbids them (library calls never go interactive).
- `MGDIO_NONINTERACTIVE=0` always allows them (a GUI-launched process with a
  working browser but no TTY).
- Explicit `mgdio auth <provider>` commands are exempt, so exporting
  `MGDIO_NONINTERACTIVE=1` host-wide on a server is safe.

### Linux keyring fallback

A minimal VPS image often has no Secret Service daemon, so the OS `keyring`
cannot store a token. mgdio detects this at startup and falls back to a
file-based store on its own. No manual backend configuration.

The default fallback is **unencrypted**: a `chmod 600` file at
`~/.local/share/mgdio/keyring/mgdio_plaintext.cfg` inside a `chmod 700`
directory. This is deliberate so cron jobs never hang on a password prompt.
mgdio logs a one-time warning only when it *writes* a credential; read-only
commands stay silent.

- `MGDIO_KEYRING_PLAINTEXT=0` switches to an encrypted file backend, which
  prompts for a password on every process (unsuitable for cron).
- `PYTHON_KEYRING_BACKEND` or `MGDIO_KEYRING_BACKEND` forces a backend of your
  choosing and mgdio will not override it.

A cron entry is then just the absolute path to the binary, for example
`*/15 * * * * /path/to/venv/bin/mgdio drive list --max 5`.

## Where credentials live

- **OAuth token**: OS vault under service `mgdio:google:<profile>`, username
  `oauth_token`. Windows: *Credential Manager → Windows Credentials*. macOS:
  *Keychain*. Linux: *Secret Service*, or the file fallback above.
- **Profile index**: the list of known slugs lives next to
  `client_secret.json` as `google/profiles.json`. The keyring remains the
  source of truth for the token bytes.
- **`client_secret.json`**: one shared file (app identity, not per-account):

| OS | Path |
| --- | --- |
| Windows | `%LOCALAPPDATA%\mgdio\mgdio\google\client_secret.json` (yes, `mgdio` twice) |
| macOS | `~/Library/Application Support/mgdio/google/client_secret.json` |
| Linux | `~/.local/share/mgdio/google/client_secret.json` |

Print the real path on your machine rather than guessing:

```bash
uv run python -c "from mgdio.settings import GOOGLE_CLIENT_SECRET_PATH as p; print(p, p.exists())"
```

`--reset` deletes only the token and reuses this file, so re-auth never
requires re-downloading anything.

??? note "macOS Keychain: stale items are handled automatically"
    The Keychain binds each item's ACL to the binary that created it. After a
    `.venv` rebuild the new python cannot overwrite the old item (error
    `-25244`). mgdio deletes the stale item with Apple's `security` CLI and
    retries. If that ever fails, the error includes the manual fix:

    ```bash
    security delete-generic-password -s "mgdio:google:<profile>" -a "oauth_token"
    ```

    You may also see a one-time *"python wants to access your keychain"*
    dialog after a rebuild. Click **Always Allow**.

## Building your own Google API client

Need a Google API that has no subpackage yet? The shared auth is one call away:

```python
from googleapiclient.discovery import build

from mgdio.auth.google import get_credentials

service = build("docs", "v1", credentials=get_credentials(), cache_discovery=False)
```

No scopes argument, no per-service auth dance. See
[`mgdio.auth`](reference/auth.md) for the full API.
