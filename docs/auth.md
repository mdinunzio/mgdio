# Authentication

mgdio's auth subsystem exists so that every other module can be a plain
function call. The design goals, in priority order:

- **Stable.** OAuth refresh tokens that do not expire (Google consent screen
  *Published*), long-lived personal tokens where the provider offers them.
- **Native.** Official provider APIs, not SMTP or IMAP.
- **Free.** Works against a personal `@gmail.com`; no Workspace account.
- **Vault-backed.** Tokens live in an encrypted
  [mgdvault](https://github.com/mdinunzio/mgdvault) KeePass file shared by
  every project on the machine, unlocked by one env var. Same behaviour on a
  laptop, a headless VPS, or in cron. See [Credential vault](#credential-vault).
- **Unattended-safe.** A missing or dead token on a cron host raises a clear
  error instead of blocking forever on a browser.

Each provider exposes the same triple: `get_credentials()` (or the provider's
equivalent such as `get_token()` / `get_api_key()`), `clear_stored_token()`,
and `reset_credentials_cache()`.

| Provider | Flow | Vault key | Command |
| --- | --- | --- | --- |
| Google (Gmail, Sheets, Calendar, Drive) | OAuth, one consent for all four | `mgdio/google/<profile>` | `mgdio auth google --profile <slug>` |
| Google Maps | API key pasted into a setup page | `mgdio/maps/api_key` | `mgdio auth maps` |
| YNAB | Personal access token pasted into a setup page | `mgdio/ynab/token` | `mgdio auth ynab` |
| Whoop | OAuth 2.0 code flow, auto-refresh | `mgdio/whoop/oauth_token` (+ `app_credentials`) | `mgdio auth whoop` |

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
all four scopes. The token is written to your credential vault under
`mgdio/google/<slug>`; later calls read it from there and refresh silently.

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

The first line names the vault in use. This only reads the vault; it makes no
network calls and triggers no setup flows. If the vault is not configured,
every provider is reported as unauthenticated with the reason.

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

### Headless hosts

The vault is a file, so a VPS or container works exactly like a laptop:
export `MGDVAULT_PASSWORD` (shell profile, a systemd unit's `Environment=`,
or a `.env` next to the job) and run the auth commands. Simpler still, copy
an already-populated `vault.kdbx` from your laptop to the host; every token
comes with it and no consent flows need redoing. The file is encrypted, so
`scp` is fine as long as the passphrase travels separately.

Cron does not source your shell profile, so put `MGDVAULT_PASSWORD=...` at
the top of the crontab (or in a `chmod 600` env file the entry sources) and
use the absolute path to the binary, for example
`*/15 * * * * /path/to/venv/bin/mgdio drive list --max 5`. Concurrent jobs
are safe: token refreshes take the vault's write lock.

## Credential vault

Every secret mgdio holds lives in [mgdvault](https://github.com/mdinunzio/mgdvault),
a small library that stores secrets in an encrypted KeePass (`.kdbx`) file in
your user data directory and shares it across all your Python projects. One
env var unlocks it:

```bash
export MGDVAULT_PASSWORD='a long passphrase'
```

Put it in your shell profile (one copy for every project) or in a gitignored
`.env`; mgdio loads `.env` on import. The database is created automatically
the first time something is stored.

| Variable | Purpose | Default |
| --- | --- | --- |
| `MGDVAULT_PASSWORD` | Master passphrase | required |
| `MGDVAULT_PATH` | Location of the `.kdbx` file | `~/Library/Application Support/mgdvault/vault.kdbx` (macOS), `%LOCALAPPDATA%\mgdvault\vault.kdbx` (Windows), `~/.local/share/mgdvault/vault.kdbx` (Linux) |
| `MGDVAULT_BACKEND` | `keepass` (default) or `keyring` for the OS credential manager | `keepass` |

### Keys mgdio uses

| Key | Contents |
| --- | --- |
| `mgdio/google/<profile>` | Google OAuth token bundle (one per account) |
| `mgdio/ynab/token` | YNAB personal access token |
| `mgdio/maps/api_key` | Google Maps Platform API key |
| `mgdio/whoop/app_credentials` | Whoop developer app Client ID + Secret |
| `mgdio/whoop/oauth_token` | Whoop OAuth token bundle |

The set of Google profiles is simply the keys under `mgdio/google/`; there is
no separate index. Inspect or manage entries with the `mgdvault` CLI, which
never prints values unless asked:

```bash
uv run mgdvault info                 # backend, path, secret count
uv run mgdvault list mgdio           # keys only
uv run mgdvault exists mgdio/ynab/token
uv run mgdvault delete mgdio/maps/api_key
```

The `.kdbx` file is a standard KeePass database; open it in
[KeePassXC](https://keepassxc.org/) to audit what is stored.

??? note "Why a file instead of the OS keychain"
    mgdio ≤ 0.5 used the OS credential manager via `keyring`. Headless Linux
    has no Secret Service daemon (so mgdio carried a plaintext-file
    fallback), macOS ties each Keychain item to the binary that created it
    (so every rebuilt `.venv` triggered permission dialogs or write refusals),
    and none of it was portable between machines. The encrypted file has none
    of those problems, and token refreshes go through a locked
    read-modify-write so concurrent cron jobs cannot clobber each other,
    which matters for Whoop, whose refresh tokens rotate on every use.
    `MGDVAULT_BACKEND=keyring` still stores the same keys in the OS keychain
    if you prefer it.

### Migrating from mgdio ≤ 0.5

Existing installs have their tokens in the OS keychain. On the machine that
holds them, copy everything into the vault in one go. The keychain is only
read, never modified, so re-running is safe:

```bash
export MGDVAULT_PASSWORD='...'
uv run mgdio auth migrate-keyring
uv run mgdio auth status
```

Then copy `vault.kdbx` to your other machines rather than migrating each one.
A headless host that used the old plaintext-file fallback has no keychain to
read; copy the vault file there or re-run the auth commands. Once satisfied,
remove the old items from the keychain by hand (macOS: Keychain Access, search
`mgdio:`).

## Where non-secret files live

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

## Building your own Google API client

Need a Google API that has no subpackage yet? The shared auth is one call away:

```python
from googleapiclient.discovery import build

from mgdio.auth.google import get_credentials

service = build("docs", "v1", credentials=get_credentials(), cache_discovery=False)
```

No scopes argument, no per-service auth dance. See
[`mgdio.auth`](reference/auth.md) for the full API.
