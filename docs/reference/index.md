# API reference

Generated from the source docstrings by
[mkdocstrings](https://mkdocstrings.github.io/). Each service subpackage
re-exports its public API from its `__init__`, so `from mgdio.gmail import ...`
is always the right import path; the private `client` / `messages` /
`values` modules behind it are implementation detail.

## Conventions

- **Functions, not clients.** Each subpackage is a set of module-level
  functions. Service connections are cached per process behind `get_service()`
  (Google) or `get_session()` / `request()` (REST providers).
- **Naming.** `fetch_*` performs a network read. `get_*` returns something
  cheap or cached. `list_*` (Drive) is a paginated search. Everything else is
  a verb: `send_email`, `create_event`, `share_file`, `update_transaction`.
- **Return types.** Frozen `dataclass(slots=True)` instances with plain
  Python types: tz-aware `datetime`, `Path`, tuples instead of lists where the
  data is immutable. Money (YNAB) is kept in integer milliunits with
  `..._dollars` convenience properties.
- **Tri-state updates.** `update_event` (Calendar) and `update_transaction`
  (YNAB) take `None` to leave a field alone, the `CLEAR` sentinel to null it
  on the server, or a value to set it.
- **Profiles.** Every Google function accepts a trailing `profile=` keyword
  naming the Google account. See
  [Multiple Google accounts](../auth.md#multiple-google-accounts-profiles).
- **Errors.** Everything raised on purpose derives from
  [`MgdioError`][mgdio.exceptions.MgdioError]. API failures are
  [`MgdioAPIError`][mgdio.exceptions.MgdioAPIError]; auth problems are
  [`MgdioAuthError`][mgdio.exceptions.MgdioAuthError] subclasses. Invalid
  inputs (a naive datetime, an unknown profile slug) raise `ValueError` at the
  function boundary.

## Modules

| Module | What it covers |
| --- | --- |
| [Command line](cli.md) | The `mgdio` console script, every group and option |
| [mgdio.auth](auth.md) | Google OAuth profiles, YNAB / Whoop / Maps credentials, `mgdio auth status` |
| [mgdio.gmail](gmail.md) | `fetch_messages`, `fetch_message`, `send_email` |
| [mgdio.sheets](sheets.md) | Values read / write / append / clear, spreadsheets, tabs |
| [mgdio.calendar](calendar.md) | Calendars, event CRUD, quick-add |
| [mgdio.drive](drive.md) | Files, folders, upload / download / export, sharing |
| [mgdio.maps](maps.md) | Geocoding and routes on an API key |
| [mgdio.ynab](ynab.md) | Budgets, accounts, categories, transactions |
| [mgdio.whoop](whoop.md) | Recovery, sleep, workouts, cycles, profile, body |
| [mgdio.settings](settings.md) | Paths, scopes, keyring identifiers, env vars |
| [mgdio.exceptions](exceptions.md) | The error hierarchy |
