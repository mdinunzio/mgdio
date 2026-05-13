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
  Calendar, YNAB) plus a `mgdio skills deploy [--global]` CLI to copy them into
  `./.claude/skills/` or `~/.claude/skills/`. Skills auto-trigger on natural
  intent; writes require explicit user confirmation.
- `python -m mgdio` entry point as an alternative to the `mgdio` console script.

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
