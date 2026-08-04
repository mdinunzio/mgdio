# Changelog

Notable changes to mgdio. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/). Releases before 0.3.5 predate
this file — see the git history.

## [0.5.0] - 2026-08-03

### Added

- **`mgdio auth whoop --catch`** — the callback catcher, run on the
  machine *with* the browser while `--headless` waits on the other
  machine. It binds the redirect URI locally, so the post-consent
  redirect lands on a real page that displays the full callback URL
  (with a copy button; also printed in the catcher's terminal) instead
  of a dead page whose address bar must be scavenged. This flips the
  headless flow's fragile contract — "the redirect must fail fast" —
  to "the redirect is served," making local listeners, port-forward
  hangs, and browser localhost policies irrelevant. The catcher never
  sees app credentials and stores nothing; it only relays the URL,
  which still gets pasted into the waiting prompt. Runs until Ctrl-C
  so a re-consent after an expired code is caught too. The headless
  instructions now mention it, and `run_catch_server` is exported from
  `mgdio.auth.whoop`.

## [0.4.3] - 2026-08-03

### Changed

- **Whoop headless troubleshooting rewritten from live field debugging.**
  Removed the blank-page ("harmless, use the address bar") and
  try-incognito bullets — both proved unhelpful or counterproductive: a
  local listener that *hangs* the redirect (VS Code Remote-SSH
  auto-forwarding, which re-arms itself because it forwards any
  `localhost:<port>` URL printed in an integrated terminal — including
  the callback URI these very instructions print) keeps the callback URL
  out of the address bar until the one-time auth code has expired.
  Replaced with the capture method that works regardless: DevTools →
  Network → Preserve log → GRANT again → copy the `Location` response
  header off the 302 — with a note to paste quickly. README and the
  whoop skill carry the same guidance, plus the
  `"remote.autoForwardPorts": false` fix for the VS Code loop.

## [0.4.2] - 2026-08-03

### Fixed

- **Explicit `mgdio auth <provider>` commands bypass the non-interactive
  guard.** The 0.4.0 guard also fired on the explicit auth CLI (which
  routes through the same getters), so under `MGDIO_NONINTERACTIVE=1` or
  without a tty, `mgdio auth whoop --headless` refused with advice to
  run the very command being run. Whoop/YNAB/Maps gain an
  `authorize(headless=False)` entry point (mirroring Google's
  `authorize_profile`) that skips the guard — an explicit auth command
  *is* the user's request for an interactive flow — and the CLI now uses
  it. Library calls via the getters keep the guard unchanged.
- Headless prompts (`input()`) in all four providers now turn a closed
  stdin (`EOFError`) into a clean, actionable error instead of a
  traceback.

### Added

- **Install provenance diagnostics** (stale-shim antidote): `mgdio
  --version` prints the version *and* install path, and the
  non-interactive guard error appends `[mgdio <version> @ <path>]` — one
  line that exposes an old parallel install (e.g. a forgotten `uv tool`
  shim shadowing a project venv) masquerading as a missing feature.

## [0.4.1] - 2026-08-03

UX/robustness pass on `mgdio auth whoop --headless`, from field feedback
of a real re-auth session (VPS + Mac browser).

### Changed

- **Instructions warn about the dead page *before* the auth URL.** Users
  open the URL the moment they see it and never read further, then
  mistake the failed post-consent page for breakage. The warning now
  leads, covers the page rendering **blank** (not just failing), names
  the expected address-bar prefix (the registered redirect URI, default
  `http://localhost:8765/callback` unless `MGDIO_WHOOP_REDIRECT_URI` is
  set), and the input prompt itself repeats the instruction.
- **Troubleshooting is printed with the instructions**: a blank page
  means something local is listening on the callback port (VS Code
  port-forwarding, an orphaned `ssh -L`, another dev server) — harmless,
  `lsof -nP -i :<port>` names it; a browser stuck on the consent screen
  suggests retrying in a private window without extensions.
- **Tolerant paste parsing.** Whitespace/line-wraps from terminal
  copying are collapsed; a bare `code=...&state=...` (or `code=...`)
  fragment is accepted alongside a full URL. A missing `state` is
  allowed with a warning; a wrong one is still rejected.
- **Bad pastes re-prompt instead of aborting** (up to 3 attempts, with a
  specific hint). The `state` is minted once per run, so the printed
  auth URL — and any consent already completed from it — stays valid
  across retries; previously an abort minted a new state on re-run,
  invalidating the URL the user had already used.
- **Successful auth names the account**: `Authorized as First Last
  (email).` — from the `/v2/user/profile/basic` validation call that
  already runs — so a wrong-account consent is caught immediately (also
  shown on the browser flow's result page).

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
