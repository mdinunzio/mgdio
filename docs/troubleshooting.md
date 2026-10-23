# Troubleshooting

**Refresh token expired or revoked.**
Verify the Google Auth Platform consent screen is *Published* (apps in
*Testing* lose refresh tokens every 7 days), then run
`mgdio auth google --profile <slug> --reset`.

**`no Google profiles` or `multiple Google profiles` error.**
Pick an account: pass `--profile <slug>` (or set `MGDIO_GOOGLE_PROFILE`), or
authorize one with `mgdio auth google --profile <slug>`. List existing ones
with `mgdio auth google profiles`.

**Scope mismatch after an upgrade.**
When a release adds a Google scope, the first call falls back to the setup
flow. Approve the new scope on the consent screen (or run `--reset`).

**`MgdioInteractionRequiredError` in a cron job or service.**
A token needs an interactive auth flow and the process has no TTY. Run the
`mgdio auth ...` command named in the error from a terminal. See
[Unattended jobs never hang](auth.md#unattended-jobs-never-hang).

**Testing without touching real APIs.**
`uv run pytest -ra`. The unit suite routes every secret read and write to an
in-memory vault and never touches your real one, even with `MGDVAULT_PASSWORD`
exported.

**YNAB token rejected.**
`mgdio auth ynab --reset` and paste a new one. The setup page calls
`GET /v1/user` before saving, so typos surface immediately.

**Maps `REQUEST_DENIED`.**
The API key is invalid, or the Geocoding / Directions API is not enabled for
its project, or billing is not enabled. Fix it in the Cloud Console, then
`mgdio auth maps --reset`.

**Maps `reverse` says "No such option".**
Pass the coordinate as one quoted `"lat,lng"` token so the negative longitude
is not parsed as a CLI option.

**`mismatching_state` in `--headless` mode.**
You pasted a redirect URL from a *different* mgdio session. State rotates every
run, so finish the paste in the same terminal session that printed the auth
URL. Re-run the command and try again.

**`MGDVAULT_PASSWORD is not set`.**
Every mgdio command needs the vault passphrase. Export it in your shell
profile, or put it in a `.env` in the directory you run from. `mgdio auth
status` shows which vault is in use without touching any provider. See
[Credential vault](auth.md#credential-vault).

**`Could not unlock the KeePass database`.**
Wrong passphrase for the file at `MGDVAULT_PATH` (or the default path). If you
copied a `vault.kdbx` from another machine, use that machine's passphrase.

**Tokens vanished after upgrading to 0.6.**
They are still in the OS keychain. Run `mgdio auth migrate-keyring` on that
machine; see [Migrating from mgdio ≤ 0.5](auth.md#migrating-from-mgdio-05).

**`Timed out ... waiting for the vault write lock`.**
Another process is mid-write, or died holding `vault.kdbx.lock`. Wait, or
delete the stale `.lock` file if nothing is running.

**Whoop callback URL never appears in the browser.**
Usually VS Code Remote-SSH port forwarding. See the
[Whoop headless notes](services/whoop.md#headless-whoop-auth).

**Which mgdio am I running?**
`mgdio --version` prints the version **and the install path**, which exposes a
stale `uv tool` shim shadowing a project venv.
