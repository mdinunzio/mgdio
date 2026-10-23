---
name: mgdvault
description: Store, check and retrieve project secrets (API keys, passwords, OAuth tokens) with the `mgdvault` CLI and Python API. Use whenever a task needs a credential, when code calls `mgdvault.get(...)`, when a secret is missing or an auth error appears, or when the user wants to add, rotate or list secrets. Covers configuration (MGDVAULT_PASSWORD, MGDVAULT_PATH, MGDVAULT_BACKEND), how to add secrets without leaking them into the conversation, and troubleshooting.
---

# mgdvault

mgdvault is a small secret store. One environment variable, `MGDVAULT_PASSWORD`,
unlocks an encrypted KeePass database shared by every application on the machine.
Secrets are addressed by slash-separated keys such as `mgdio/google/personal` or
`myapp/openai/api_key`.

## Security rules (read first)

1. **Never print a secret value into this conversation.** Do not run
   `mgdvault get KEY`, `print(mgdvault.get(...))`, `echo $MGDVAULT_PASSWORD`, or
   `env | grep` in a way that returns a value. Transcripts can leave the machine;
   a leaked value means the credential must be rotated.
2. **Check presence, not value.** Use `mgdvault exists KEY` (exit code 0/1) and
   `mgdvault list [PREFIX]`. Both are safe; they never show values.
3. **Never put a secret on a command line.** `mgdvault set` deliberately has no
   value argument. Do not construct `echo 'sk-...' | mgdvault set ...` with a
   literal value, and do not write secrets into files you create.
4. **To add a secret, hand the user a command to run themselves** in their own
   terminal, where the hidden prompt keeps the value out of history:

   ```
   mgdvault set myapp/openai/api_key
   ```

   If the user already has the value in a file (for example a downloaded
   `client_secret.json`), they can run `mgdvault set KEY --from-file PATH`.
   Once they confirm, verify with `mgdvault exists KEY` and continue.
5. Code you write should read secrets at runtime with `mgdvault.get(...)`, never
   hard-code them and never copy them into `.env` files.

## Configuration

| Variable | Meaning | Default |
| --- | --- | --- |
| `MGDVAULT_PASSWORD` | Master password that unlocks the KeePass database | required for the keepass backend |
| `MGDVAULT_KEYFILE` | Optional KeePass key file, alone or with the password | unset |
| `MGDVAULT_PATH` | Location of the `.kdbx` file | `~/Library/Application Support/mgdvault/vault.kdbx` (macOS), `%LOCALAPPDATA%\mgdvault\vault.kdbx` (Windows), `~/.local/share/mgdvault/vault.kdbx` (Linux) |
| `MGDVAULT_BACKEND` | `keepass` (default), `keyring` (OS credential manager), `env`, `memory` | `keepass` |
| `MGDVAULT_KEYRING_SERVICE` | Service name for the keyring backend | `mgdvault` |
| `MGDVAULT_LOCK_TIMEOUT` | Seconds to wait for another process's write lock | `30` |

mgdvault does **not** load `.env` files. The application does (for example with
`python-dotenv`), or the variables are exported in the shell, CI, or container.
If a project keeps `MGDVAULT_PASSWORD` in `.env`, make sure `.env` is gitignored.

The database is created automatically on first use, so a fresh machine needs
only the password. `mgdvault info` shows the active backend, file location, and
how many secrets exist, without values.

## CLI reference

```
mgdvault info                      # backend, path, secret count
mgdvault list [PREFIX]             # keys only, e.g. `mgdvault list mgdio`
mgdvault exists KEY                # prints yes/no, exit code 0/1
mgdvault set KEY                   # hidden prompt (user runs this)
mgdvault set KEY --from-file PATH  # value from a file
cmd | mgdvault set KEY             # value from stdin (non-interactive)
mgdvault set KEY --json            # also validate the value is JSON
mgdvault delete KEY [-y]
mgdvault init [--path FILE]        # create the database explicitly
mgdvault get KEY                   # prints the value: avoid in agent sessions
mgdvault install-skill [--global] [--force]
```

Run it as `uv run mgdvault ...` inside a project, or plain `mgdvault ...` when
installed with `uv tool install mgdvault`.

## Python API

```python
import mgdvault

api_key = mgdvault.get("myapp/openai/api_key")            # raises SecretNotFoundError if missing
token = mgdvault.get("myapp/token", default=None)         # None if missing
mgdvault.set("myapp/openai/api_key", value)               # strings only
mgdvault.set_json("myapp/google/oauth", creds_dict)       # JSON helpers for token bundles
creds = mgdvault.get_json("myapp/google/oauth")
mgdvault.exists("myapp/token")
mgdvault.list_keys("myapp")                               # keys under a namespace
mgdvault.delete("myapp/token")
mgdvault.update("myapp/token", lambda cur: refresh(cur))  # atomic read-modify-write
```

`update(key, fn)` holds the vault's write lock while `fn` runs, so several
processes refreshing the same OAuth token cannot clobber each other. A `get`
followed by `set` is a race; use `update` for anything that rewrites a value
based on its current contents.

Explicit vaults when one process needs several stores:

```python
from mgdvault import KeePassVault, KeyringVault, MemoryVault

project_vault = KeePassVault("./secrets.kdbx", password=pw)
os_vault = KeyringVault()
mgdvault.set_default_vault(MemoryVault({"myapp/token": "x"}))  # e.g. in tests
```

Reads are cached in-process after the first unlock (a few hundred ms), so
calling `mgdvault.get` in a loop is fine. Writes take a file lock and are safe
across processes.

## Key naming convention

`<application>/<service>/<name>`, lower-case, segments of letters, digits,
`_`, `-`, `.`. Examples: `mgdio/ynab/token`, `mgdio/google/personal`,
`etl/postgres/password`. Namespacing by application lets many packages share
one vault, and `mgdvault list <application>` shows everything an app owns.

## Typical workflow when a task needs a credential

1. `mgdvault info` to confirm a vault is configured. If it says not configured,
   ask the user to set `MGDVAULT_PASSWORD` (export, or add to a gitignored
   `.env` that the app loads).
2. `mgdvault list <app>` and `mgdvault exists <key>` to see what is present.
3. For anything missing, give the user the exact `mgdvault set <key>` command
   to run, and say what the value is (for example "your YNAB personal access
   token from app.ynab.com/settings/developer").
4. After they confirm, re-check with `mgdvault exists <key>` and proceed.
5. Write code that calls `mgdvault.get(<key>)` at runtime.

## Troubleshooting

- `MGDVAULT_PASSWORD is not set`: the app did not load its `.env`, or the
  variable is missing. Check with `mgdvault info` from the same shell.
- `Could not unlock the KeePass database ... wrong password`: the password does
  not match the existing file. Confirm `MGDVAULT_PATH` points at the intended
  database; a different path with a new password would create a separate vault.
- `No OS keyring backend is available`: `MGDVAULT_BACKEND=keyring` on a headless
  machine. Unset it to use KeePass.
- macOS keyring errors mentioning a stale Keychain item: the error message
  includes the `security delete-generic-password` command to clear it. This is
  one reason the KeePass backend is the default.
- `Timed out ... waiting for the vault write lock`: another process is writing
  or crashed while holding `vault.kdbx.lock`. If nothing is running, delete the
  lock file.
- Secret missing in a cloud or CI environment: the `.kdbx` file lives on the
  machine where it was created. The user needs to provide the file (via
  `MGDVAULT_PATH`) and the password to that environment.
