# Changelog

Notable changes to mgdio. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/). Releases before 0.3.5 predate
this file — see the git history.

## [0.4.0] - 2026-07-23

### Added

- **Non-interactive mode.** Every provider's implicit auth fallback
  (`get_access_token`, `get_credentials`, `get_token`, `get_api_key`) is
  now guarded: on a host that can't run an interactive flow, mgdio raises
  the new `MgdioInteractionRequiredError` — naming the exact
  `mgdio auth ...` command to run — instead of starting a setup flow that
  blocks forever waiting for a browser/human. Controlled by
  `MGDIO_NONINTERACTIVE` (`1` = never interactive, `0` = always allow);
  when unset, interactive flows are allowed only if stdin is a tty, so
  cron/systemd/CI jobs fail fast by default.
- **`mgdio auth whoop --headless`.** Copy-paste OAuth flow for machines
  without a browser (the #25 pattern, now for Whoop): mgdio prints the
  auth URL, you open it elsewhere, approve, and paste the failed-redirect
  URL back. Prompts for the app's Client ID/Secret first if not stored.
  `get_access_token()` gains a matching `headless=` parameter.

### Changed

- **Whoop refresh failures are now classified.** Only a definitive
  rejection of the refresh token (HTTP 400/401 → new
  `MgdioTokenRejectedError`) or missing app credentials fall through to
  re-authorization. Transient failures (network errors, Whoop 5xx,
  malformed responses) raise `MgdioAPIError` and leave the stored token
  untouched, so a network blip during a scheduled job no longer discards
  a valid refresh token (or, on a headless box, hangs forever).
- **Google refresh failures are now handled** (previously an unhandled
  `google.auth.exceptions.RefreshError` traceback): `invalid_grant`
  (expired/revoked) falls through to the guarded consent flow; anything
  else raises `MgdioAPIError` as transient.
- The "re-running setup flow" warning now includes *why* the refresh
  failed (HTTP status + body snippet), distinguishing a revoked token
  from a network outage at a glance.

## [0.3.5] - 2026-07-21

### Fixed

- **macOS: auth no longer crashes on a stale Keychain item.** The Keychain
  binds each item's ACL to the binary that created it, so after a `.venv`
  rebuild every token save failed with
  `keyring.errors.PasswordSetError: ... (-25244, 'Unknown Error')` — after
  the consent screen had already completed. mgdio now deletes the stale
  item via Apple's `security` CLI (which is not subject to the item's app
  ACL) and retries the save automatically.
- Interactive auth flows verify the keyring entry is writable **before**
  opening the browser/consent page, so a broken vault entry fails fast
  instead of after the user has authorized.
- `mgdio auth <provider> --reset` no longer silently ignores a refused
  keyring delete; unrecoverable failures surface as an error with the
  exact manual-fix command.
- CLI errors raised by mgdio itself (auth/keyring/API failures) print a
  one-line `error: ...` message instead of a raw traceback.

### Added

- Shared robust keyring helpers (`mgdio.auth._keyring`) used by the
  Google, YNAB, Whoop, and Maps providers, with a new
  `MgdioKeyringError` exception for vault write/delete refusals.
