---
name: mgdvault-integration
description: Adopt mgdvault as the credential store inside a Python package, library or pipeline. Use when adding mgdvault to a project, migrating from keyring/python-keyring or .env secrets, designing key names for a package, writing auth/setup commands that store tokens, or making a test suite run without real secrets. Complements the `mgdvault` skill, which covers day-to-day CLI use.
---

# Integrating mgdvault into a package

Goal: an application reads every credential through `mgdvault.get(...)`, users
configure one environment variable, and the test suite never touches a real
vault.

## 1. Add the dependency

```toml
# pyproject.toml
dependencies = ["mgdvault>=0.1"]
```

`uv add mgdvault` or `pip install mgdvault`. The package depends on pykeepass,
keyring, platformdirs, click and filelock.

## 2. Choose a key namespace

Use `<package>/<service>/<name>` with the package name as the first segment,
all lower-case. Define keys in one settings module so they are discoverable:

```python
# mypkg/settings.py
KEY_YNAB_TOKEN = "mypkg/ynab/token"
KEY_GOOGLE_OAUTH = "mypkg/google/{profile}"   # format with the account slug


def google_oauth_key(profile: str) -> str:
    return KEY_GOOGLE_OAUTH.format(profile=profile)
```

Multi-account support is just more keys (`mypkg/google/personal`,
`mypkg/google/work`); `mgdvault.list_keys("mypkg/google")` enumerates them.

## 3. Read secrets at the point of use

```python
import mgdvault
from mgdvault import SecretNotFoundError


def ynab_token() -> str:
    try:
        return mgdvault.get(KEY_YNAB_TOKEN)
    except SecretNotFoundError as exc:
        raise MyPkgAuthError(
            "YNAB token not configured. Run `mypkg auth ynab` "
            f"(or `mgdvault set {KEY_YNAB_TOKEN}`)."
        ) from exc
```

Guidelines:

- Call `mgdvault.get` lazily inside functions, not at import time, so importing
  the package never requires a vault.
- Do not call `load_dotenv()` from library code. Only the top-level application
  (or the package's own CLI entry point) decides whether to load a `.env`.
- Reads are cached per process after the first unlock; no need to memoise.
- Use `mgdvault.get_json` / `set_json` for structured payloads such as Google
  OAuth `Credentials.to_json()` output. Store the JSON string, rebuild with
  `Credentials.from_authorized_user_info(mgdvault.get_json(key), scopes)`.
- Raise your own exception type with a message naming the command that fixes
  it, as above.

## 4. Provide a setup command that stores the secret

Library code should never prompt for a secret in the middle of a data call.
Give the package an explicit auth command:

```python
@cli.command()
def auth_ynab() -> None:
    """Store a YNAB personal access token."""
    token = click.prompt("YNAB personal access token", hide_input=True)
    mgdvault.set(KEY_YNAB_TOKEN, token.strip())
    click.echo("Stored. Verify with: mgdvault exists " + KEY_YNAB_TOKEN)
```

For OAuth flows, run the browser flow, then `mgdvault.set_json(key,
json.loads(creds.to_json()))`.

**Refresh write-back must use `update`, not `get` then `set`.** Pipelines run
several processes at once; two of them refreshing the same token would
otherwise overwrite each other, and providers that rotate refresh tokens
(Whoop does; Google does not) would leave one process holding a dead token.

```python
def _refreshed(current: str | None) -> str | None:
    creds = Credentials.from_authorized_user_info(json.loads(current), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds.to_json()


mgdvault.update(KEY_GOOGLE_OAUTH, _refreshed)
```

`update` holds the vault's inter-process write lock for the duration of the
callback and re-reads the file first, so the callback always sees the latest
value. Keep the callback short (no network calls other than the refresh).

## 5. Make tests independent of real secrets

```python
# conftest.py
import pytest
import mgdvault
from mgdvault import MemoryVault


@pytest.fixture(autouse=True)
def fake_vault():
    vault = MemoryVault({"mypkg/ynab/token": "test-token"})
    mgdvault.set_default_vault(vault)
    yield vault
    mgdvault.reset_default_vault()
```

For integration tests that need the real vault, let the repo's `.env` be
loaded by `conftest.py` (`dotenv.load_dotenv()` there is fine because tests are
an application, not the library). Mark such tests and skip them unless an
opt-in variable is set.

## 6. Document it for users

In the README:

- Say the package uses mgdvault and list the keys it reads (`mypkg/ynab/token`,
  `mypkg/google/<profile>`).
- Tell users to export `MGDVAULT_PASSWORD` (or add it to a gitignored `.env`
  that the app loads) and that the vault is created automatically.
- Mention `MGDVAULT_BACKEND=keyring` for people who prefer the OS credential
  manager, and `MGDVAULT_PATH` for a per-project database.
- Point to `uv run mgdvault install-skill` so Claude Code sessions in that
  project know how to handle its secrets.

## 7. Migrating from `keyring`

Old code: `keyring.get_password("mypkg:ynab", "token")`.
New code: `mgdvault.get("mypkg/ynab/token")`.

Do a clean cut: ship the new version, have users re-run the auth commands to
store secrets under the new keys, and delete old keyring entries. Reading the
old entries through mgdvault's keyring backend is possible
(`KeyringVault(service="mypkg:ynab").get("token")`) but mixing layouts is
confusing; prefer re-authentication. Remove any `keyrings.alt` fallbacks and
macOS stale-Keychain-item recovery code; the KeePass backend has neither
problem.

## 8. Multiple vaults in one process

Rarely needed, but supported:

```python
from mgdvault import KeePassVault

shared = mgdvault.default_vault()                       # from env vars
project = KeePassVault(".secrets/project.kdbx", password=pw)
value = project.get("deploy/token", default=None) or shared.get("deploy/token")
```

All vault classes share the same interface (`get`, `set`, `delete`, `exists`,
`list_keys`, `get_json`, `set_json`, `update`), so code can accept any
`mgdvault.Vault`.
