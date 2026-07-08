# Roadmap

## Done

- Unified Google OAuth (Gmail + Calendar + Sheets share one token).
- Gmail: read, send (plain + HTML + attachments).
- Google Sheets: values read/write/append/clear, spreadsheet + tab management,
  pandas / polars DataFrame return types.
- Google Calendar: list calendars, full event CRUD, quick-add (NL parsing).
- YNAB: budgets, accounts, categories, transactions, memo edits (and other
  fields) via PATCH.
- Personal-access-token auth flow for YNAB (paste into a localhost web page).
- Headless Google auth (`mgdio auth google --headless`) for Linux VPS / SSH-only
  hosts — copy-paste flow, no browser required on the host machine.
- Claude Code skills bundled with the package (one per service: Gmail, Sheets,
  Calendar, YNAB, Whoop) plus a `mgdio skills deploy [--global]` CLI to copy them
  into `./.claude/skills/` or `~/.claude/skills/`. Skills auto-trigger on natural
  intent; writes require explicit user confirmation.
- `python -m mgdio` entry point as an alternative to the `mgdio` console script.
- Whoop: OAuth 2.0 authorization-code flow (paste Client ID/Secret into a
  localhost setup page, browser consent, auto-refreshing token bundle in the
  keyring). Read-only v2 API: recovery, sleep, workouts, cycles, profile, body
  measurements, with auto-pagination. Redirect URI is env-overridable via
  `MGDIO_WHOOP_REDIRECT_URI`.
- Google Drive: full v3 surface on the shared Google token — list/search,
  metadata, create folders, upload, download (binary) / export (Google-native
  docs), rename/update, move, copy, trash/restore, permanent delete,
  empty-trash, and sharing (list/grant/update/revoke permissions). Typed
  `DriveFile` / `Permission` dataclasses, auto-paginated listing.
- Headless-Linux keyring auto-fallback: on a host with no Secret Service,
  mgdio selects a `keyrings.alt` file backend automatically (plaintext by
  default, `chmod 600`, no password prompt — cron-safe), opt into encryption
  via `MGDIO_KEYRING_PLAINTEXT=0`.
- Multi-account Google profiles: per-account tokens at `mgdio:google:<slug>`,
  a `profile=` kwarg on every Google function, `--profile` on every Google CLI
  command, `MGDIO_GOOGLE_PROFILE` env default, `mgdio auth google profiles` to
  list, and `mgdio auth google remove` (`--profile` / `--legacy` / `--all`) to
  clean up. Resolution waterfall: explicit → env var → sole profile.
- Google Maps: geocoding (address → coordinates, place → address, reverse) and
  routing (distance / duration / turn-by-turn directions) via an API key
  (`mgdio auth maps`, stored under `mgdio:maps`). Typed `GeocodeResult` /
  `Route` / `RouteStep` dataclasses, imperial-default units, `mgdio maps` CLI
  group — covers the common `GOOGLEMAPS_*` Google Sheets helpers.
- `mgdio auth status`: at-a-glance report of which providers (Google profiles,
  YNAB, Whoop, Maps) are authenticated on this machine, plus the commands to
  set up whatever's missing. Keyring-only, triggers no setup flows.

## Next

- **Twilio** — SMS + voice. Auth is account SID + auth token; will follow the
  YNAB paste-token UX. Subpackage at `mgdio/twilio/`.
- **`mgdio auth ynab --headless`** — YNAB's paste flow already works headlessly
  via stdin (no browser needed on the host), but the setup page is HTML. Add a
  pure-terminal variant for symmetry with `--headless` on Google.

## Possibly later

- Drafts + threads in Gmail (currently messages only).
- Free/busy lookup + meeting-invite responses in Calendar.
- Conditional formatting + chart APIs in Sheets.
- YNAB scheduled transactions + payee management.
