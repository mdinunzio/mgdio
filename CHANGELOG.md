# Changelog

Notable changes to mgdio. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/). Releases before 0.3.5 predate
this file — see the git history.

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
