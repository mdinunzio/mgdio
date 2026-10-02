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
`uv run pytest -ra`. The unit suite uses an in-memory keyring fixture and never
touches your real vault.

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

**`keyring.errors.NoKeyringError` on a Linux VPS.**
mgdio normally falls back to a file-based store automatically (see
[Linux keyring fallback](auth.md#linux-keyring-fallback)). If you still hit
it, `keyrings.alt` may be missing (`pip install keyrings.alt`) or a stale
`PYTHON_KEYRING_BACKEND` env var is forcing an unusable backend. Unset it and
let mgdio choose.

**Headless auth hangs on a keyring password prompt.**
`MGDIO_KEYRING_PLAINTEXT=0` (or an `EncryptedKeyring` env var) is set, which
prompts for a password every run and blocks cron. Unset it to use the default
no-prompt fallback.

**macOS: `errSecInvalidOwnerEdit` / error `-25244`.**
A stale Keychain item from a rebuilt `.venv`. mgdio recovers automatically;
if it cannot, the error message prints the `security delete-generic-password`
command to run. See [Where credentials live](auth.md#where-credentials-live).

**Whoop callback URL never appears in the browser.**
Usually VS Code Remote-SSH port forwarding. See the
[Whoop headless notes](services/whoop.md#headless-whoop-auth).

**Which mgdio am I running?**
`mgdio --version` prints the version **and the install path**, which exposes a
stale `uv tool` shim shadowing a project venv.
