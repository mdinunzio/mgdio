"""``mgdio`` console-script entry point."""

from __future__ import annotations

import os
import re
import shutil
from datetime import datetime
from pathlib import Path

import click

from mgdio.auth.google import authorize_profile as authorize_google_profile
from mgdio.auth.google import clear_legacy_token as clear_google_legacy_token
from mgdio.auth.google import clear_stored_token as clear_google_token
from mgdio.auth.google import (
    detect_legacy_token,
    live_profiles,
)
from mgdio.auth.maps import clear_stored_token as clear_maps_key
from mgdio.auth.maps import get_api_key as get_maps_key
from mgdio.auth.whoop import clear_stored_token as clear_whoop_token
from mgdio.auth.whoop import get_access_token as get_whoop_token
from mgdio.auth.ynab import clear_stored_token as clear_ynab_token
from mgdio.auth.ynab import get_token as get_ynab_token
from mgdio.calendar import (
    create_event,
    delete_event,
    fetch_calendars,
    fetch_event,
    fetch_events,
    quick_add,
    update_event,
)
from mgdio.drive import (
    copy_file,
    create_folder,
    delete_file,
    download_file,
    export_file,
    fetch_file,
    list_files,
    list_permissions,
    move_file,
    share_file,
    trash_file,
    unshare_file,
    upload_file,
)
from mgdio.gmail import fetch_message, fetch_messages, send_email
from mgdio.maps import fetch_route, geocode, reverse_geocode
from mgdio.settings import GOOGLE_PROFILE_ENV_VAR
from mgdio.sheets import (
    append_values,
    clear_values,
    create_spreadsheet,
    fetch_spreadsheet,
    fetch_values,
    write_values,
)
from mgdio.skills import iter_skill_dirs
from mgdio.whoop import (
    fetch_body_measurement,
    fetch_cycles,
    fetch_profile,
    fetch_recoveries,
    fetch_sleeps,
    fetch_workouts,
)
from mgdio.ynab import CLEAR as YNAB_CLEAR
from mgdio.ynab import (
    fetch_accounts,
    fetch_budgets,
    fetch_categories,
    fetch_transactions,
    update_transaction,
)


@click.group()
def cli() -> None:
    """mgdio: personal connectivity tools."""


@cli.group()
def auth() -> None:
    """Authentication commands.

    Future providers will land as siblings:

      mgdio auth twilio   # planned
    """


@auth.command("status")
def auth_status() -> None:
    """Show which providers are authenticated on this machine."""
    from mgdio.auth.status import get_auth_status

    rows = get_auth_status()
    width = max(len(r.name) for r in rows)
    for r in rows:
        mark = "[x]" if r.authenticated else "[ ]"
        click.echo(f"{mark} {r.name:<{width}}  {r.detail}")

    missing = [r for r in rows if not r.authenticated]
    if missing:
        click.echo("")
        click.echo("To authenticate the remaining provider(s):")
        for r in missing:
            click.echo(f"  {r.auth_command}")


def _profile_option(func):
    """Attach the shared ``--profile`` option to a Google service command."""
    return click.option(
        "--profile",
        default=None,
        help=(
            "Google account profile slug. Omit to use $"
            f"{GOOGLE_PROFILE_ENV_VAR} or the sole configured profile."
        ),
    )(func)


@auth.group("google", invoke_without_command=True)
@click.option(
    "--profile",
    default=None,
    help="Account profile slug to authorize, e.g. mdinunziosvc.",
)
@click.option(
    "--reset",
    is_flag=True,
    help="Delete this profile's stored token before running.",
)
@click.option(
    "--headless",
    is_flag=True,
    help=(
        "Use the copy-paste flow instead of the localhost setup page. "
        "For machines without a browser (e.g. a Linux VPS)."
    ),
)
@click.pass_context
def auth_google(
    ctx: click.Context, profile: str | None, reset: bool, headless: bool
) -> None:
    """Run (or re-run) the Google OAuth onboarding flow for a profile.

    Requests Gmail + Calendar + Sheets + Drive scopes in a single consent
    screen. The token is stored in your OS keyring under
    ``mgdio:google:<profile>``. ``--profile`` is required.

    Pass ``--headless`` on machines without a browser (e.g. a Linux VPS):
    mgdio will print the auth URL and prompt for the resulting redirect
    URL to be pasted back, instead of opening a localhost setup page.

    Run ``mgdio auth google profiles`` to list configured profiles.
    """
    if ctx.invoked_subcommand is not None:
        return
    if not profile:
        raise click.UsageError(
            "pass --profile <slug>, e.g. " "mgdio auth google --profile mdinunziosvc"
        )
    if reset:
        clear_google_token(profile)
    authorize_google_profile(profile, headless=headless)
    click.echo(f"Authenticated profile '{profile}'.")
    if detect_legacy_token():
        click.echo(
            "note: a legacy token at 'mgdio:google' (pre-profiles) is still "
            "in your keyring and now unused; remove it with "
            "`mgdio auth google remove --legacy`."
        )


@auth_google.command("profiles")
def auth_google_profiles() -> None:
    """List configured Google account profiles."""
    slugs = live_profiles()
    if not slugs:
        click.echo("(no Google profiles; run `mgdio auth google --profile <slug>`)")
        return
    env = os.environ.get(GOOGLE_PROFILE_ENV_VAR)
    auto = slugs[0] if len(slugs) == 1 else None
    for slug in slugs:
        marks = []
        if slug == env:
            marks.append("env-default")
        if slug == auto:
            marks.append("auto")
        suffix = f"  [{', '.join(marks)}]" if marks else ""
        click.echo(f"{slug}{suffix}")


@auth_google.command("remove")
@click.option("--profile", default=None, help="Profile slug to remove.")
@click.option(
    "--legacy",
    is_flag=True,
    help="Remove the pre-profiles token at the bare 'mgdio:google' service.",
)
@click.option("--all", "all_", is_flag=True, help="Remove every profile (+ legacy).")
@click.option(
    "--yes", "-y", is_flag=True, help="Skip the confirmation prompt (for scripts)."
)
def auth_google_remove(
    profile: str | None, legacy: bool, all_: bool, yes: bool
) -> None:
    """Delete stored Google credentials (a profile, the legacy token, or all).

    Examples: ``mgdio auth google remove --profile personal``,
    ``--legacy`` (the old token), or ``--all``.
    """
    selected = sum(bool(x) for x in (profile, legacy, all_))
    if selected == 0:
        raise click.UsageError("pass one of --profile <slug>, --legacy, or --all.")
    if selected > 1:
        raise click.UsageError("--profile, --legacy, and --all are mutually exclusive.")

    # Build the work list + a human description for the confirmation.
    profiles_to_remove: list[str] = []
    remove_legacy = False
    if all_:
        profiles_to_remove = live_profiles()
        remove_legacy = detect_legacy_token()
    elif legacy:
        remove_legacy = True
    else:
        profiles_to_remove = [profile]  # type: ignore[list-item]

    targets = [f"profile '{slug}'" for slug in profiles_to_remove]
    if remove_legacy:
        targets.append("legacy 'mgdio:google' token")
    if not targets:
        click.echo("Nothing to remove.")
        return

    if not yes:
        click.echo("About to delete: " + ", ".join(targets) + ".")
        click.confirm("This cannot be undone. Continue?", abort=True)

    for slug in profiles_to_remove:
        clear_google_token(slug)
        click.echo(f"Removed profile '{slug}'.")
    if remove_legacy:
        clear_google_legacy_token()
        click.echo("Removed legacy 'mgdio:google' token.")


@auth.command("ynab")
@click.option(
    "--reset",
    is_flag=True,
    help="Delete the stored token before running, forcing a fresh paste flow.",
)
def auth_ynab(reset: bool) -> None:
    """Run (or re-run) the YNAB personal-access-token onboarding flow.

    Opens a localhost setup page in your browser with instructions to
    mint a token at app.ynab.com/settings/developer; paste the token
    there and it's validated and saved to your OS keyring under
    ``mgdio:ynab``.
    """
    if reset:
        clear_ynab_token()
    get_ynab_token()
    click.echo("Authenticated.")


@auth.command("whoop")
@click.option(
    "--reset",
    is_flag=True,
    help="Delete the stored token before running, forcing re-authorization.",
)
def auth_whoop(reset: bool) -> None:
    """Run (or re-run) the Whoop OAuth onboarding flow.

    Opens a localhost setup page in your browser: paste your Whoop app's
    Client ID + Secret, click "Authorize with Whoop", and approve. The
    resulting token bundle is saved to your OS keyring under
    ``mgdio:whoop`` and refreshed automatically on expiry.

    The redirect URI defaults to ``http://localhost:8765/callback`` and
    can be overridden with the ``MGDIO_WHOOP_REDIRECT_URI`` env var (must
    match what's registered in your Whoop app).
    """
    if reset:
        clear_whoop_token()
    get_whoop_token()
    click.echo("Authenticated.")


@auth.command("maps")
@click.option(
    "--reset",
    is_flag=True,
    help="Delete the stored API key before running, forcing a fresh paste flow.",
)
def auth_maps(reset: bool) -> None:
    """Run (or re-run) the Google Maps API-key onboarding flow.

    Maps uses an API key, not the shared Google login. Opens a localhost
    setup page with Cloud Console instructions (enable the Geocoding +
    Directions APIs, create a key); paste the key there and it's verified
    with a test geocode and saved to your OS keyring under ``mgdio:maps``.
    """
    if reset:
        clear_maps_key()
    get_maps_key()
    click.echo("Authenticated.")


@cli.group()
def gmail() -> None:
    """Gmail commands (read, list, send)."""


@gmail.command("list")
@click.option("--query", "-q", default="", help="Gmail search query.")
@click.option(
    "--max",
    "max_results",
    default=5,
    type=int,
    show_default=True,
    help="Max messages to fetch.",
)
@_profile_option
def gmail_list(query: str, max_results: int, profile: str | None) -> None:
    """List recent inbox messages (subject + sender + date)."""
    for message in fetch_messages(query, max_results, profile=profile):
        click.echo(
            f"{message.date:%Y-%m-%d %H:%M}  "
            f"{message.sender[:40]:40}  "
            f"{message.subject}  "
            f"[{message.id}]"
        )


@gmail.command("get")
@click.argument("message_id")
@_profile_option
def gmail_get(message_id: str, profile: str | None) -> None:
    """Print one message's headers, snippet, and plain-text body."""
    message = fetch_message(message_id, profile=profile)
    click.echo(f"Id:      {message.id}")
    click.echo(f"Date:    {message.date:%Y-%m-%d %H:%M %Z}")
    click.echo(f"From:    {message.sender}")
    click.echo(f"To:      {', '.join(message.to)}")
    if message.cc:
        click.echo(f"Cc:      {', '.join(message.cc)}")
    click.echo(f"Subject: {message.subject}")
    click.echo(f"Labels:  {', '.join(message.label_ids)}")
    click.echo(f"Snippet: {message.snippet}")
    click.echo("---")
    click.echo(message.body_text or "(no plain-text body)")


@gmail.command("send")
@click.option("--to", required=True, help="Recipient email address.")
@click.option("--subject", required=True)
@click.option("--body", required=True, help="Plain-text body.")
@click.option("--cc", default=None, help="Optional cc address.")
@click.option("--bcc", default=None, help="Optional bcc address.")
@click.option(
    "--html",
    default=None,
    help="Optional HTML body (sent as multipart/alternative).",
)
@click.option(
    "--attach",
    "attachments",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Attach a file. Repeatable.",
)
@_profile_option
def gmail_send(
    to: str,
    subject: str,
    body: str,
    cc: str | None,
    bcc: str | None,
    html: str | None,
    attachments: tuple[Path, ...],
    profile: str | None,
) -> None:
    """Send an email."""
    message_id = send_email(
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        bcc=bcc,
        html=html,
        attachments=list(attachments) or None,
        profile=profile,
    )
    click.echo(f"Sent: {message_id}")


@cli.group()
def sheets() -> None:
    """Google Sheets commands."""


@sheets.command("info")
@click.argument("spreadsheet_id")
@_profile_option
def sheets_info(spreadsheet_id: str, profile: str | None) -> None:
    """Print metadata about a spreadsheet (title, tabs, url)."""
    sheet = fetch_spreadsheet(spreadsheet_id, profile=profile)
    click.echo(f"Title:  {sheet.title}")
    click.echo(f"Url:    {sheet.url}")
    click.echo(f"Locale: {sheet.locale}  ({sheet.time_zone})")
    click.echo("Tabs:")
    for tab in sheet.tabs:
        click.echo(
            f"  [{tab.index}] {tab.title}  "
            f"({tab.row_count}x{tab.column_count})  "
            f"sheetId={tab.id}"
        )


@sheets.command("read")
@click.argument("spreadsheet_id")
@click.argument("range_")
@_profile_option
def sheets_read(spreadsheet_id: str, range_: str, profile: str | None) -> None:
    """Print a tab-separated dump of a range."""
    for row in fetch_values(spreadsheet_id, range_, profile=profile):
        click.echo("\t".join("" if cell is None else str(cell) for cell in row))


@sheets.command("write")
@click.argument("spreadsheet_id")
@click.argument("range_")
@click.option(
    "--row",
    "rows",
    multiple=True,
    help="One row of comma-separated cells. Repeatable.",
)
@click.option(
    "--raw",
    is_flag=True,
    help="Use valueInputOption=RAW (no formula/date/number parsing).",
)
@_profile_option
def sheets_write(
    spreadsheet_id: str,
    range_: str,
    rows: tuple[str, ...],
    raw: bool,
    profile: str | None,
) -> None:
    """Overwrite a range with --row values (comma-separated cells)."""
    values = [row.split(",") for row in rows]
    updated = write_values(spreadsheet_id, range_, values, raw=raw, profile=profile)
    click.echo(f"Updated cells: {updated}")


@sheets.command("append")
@click.argument("spreadsheet_id")
@click.argument("range_")
@click.option(
    "--row",
    "rows",
    multiple=True,
    help="One row of comma-separated cells. Repeatable.",
)
@click.option("--raw", is_flag=True)
@_profile_option
def sheets_append(
    spreadsheet_id: str,
    range_: str,
    rows: tuple[str, ...],
    raw: bool,
    profile: str | None,
) -> None:
    """Append --row values to the end of the table at range_."""
    values = [row.split(",") for row in rows]
    updated = append_values(spreadsheet_id, range_, values, raw=raw, profile=profile)
    click.echo(f"Appended cells: {updated}")


@sheets.command("clear")
@click.argument("spreadsheet_id")
@click.argument("range_")
@_profile_option
def sheets_clear(spreadsheet_id: str, range_: str, profile: str | None) -> None:
    """Clear all values in range_ (formatting preserved)."""
    clear_values(spreadsheet_id, range_, profile=profile)
    click.echo("Cleared.")


@sheets.command("create")
@click.option("--title", required=True, help="New spreadsheet title.")
@click.option(
    "--tab",
    "tabs",
    multiple=True,
    help="Initial tab name. Repeatable.",
)
@_profile_option
def sheets_create(title: str, tabs: tuple[str, ...], profile: str | None) -> None:
    """Create a new spreadsheet."""
    spreadsheet = create_spreadsheet(
        title, sheet_names=list(tabs) or None, profile=profile
    )
    click.echo(f"Created: {spreadsheet.id}")
    click.echo(f"Url:     {spreadsheet.url}")


@cli.group("calendar")
def calendar_cmd() -> None:
    """Google Calendar commands."""


@calendar_cmd.command("list-cals")
@_profile_option
def calendar_list_cals(profile: str | None) -> None:
    """List every calendar the authenticated user has access to."""
    for cal in fetch_calendars(profile=profile):
        marker = "*" if cal.primary else " "
        click.echo(f"{marker} {cal.access_role:18} " f"{cal.summary[:40]:40} {cal.id}")


@calendar_cmd.command("list-events")
@click.option(
    "--calendar",
    "calendar_id",
    default="primary",
    show_default=True,
    help="Calendar id (use list-cals to find non-primary ids).",
)
@click.option(
    "--max",
    "max_results",
    default=10,
    type=int,
    show_default=True,
)
@click.option("--query", "-q", default="", help="Free-text search.")
@click.option(
    "--time-min",
    "time_min",
    default=None,
    help="ISO datetime lower bound, e.g. 2026-05-09T00:00:00-04:00.",
)
@click.option(
    "--time-max",
    "time_max",
    default=None,
    help="ISO datetime upper bound, e.g. 2026-05-16T00:00:00-04:00.",
)
@_profile_option
def calendar_list_events(
    calendar_id: str,
    max_results: int,
    query: str,
    time_min: str | None,
    time_max: str | None,
    profile: str | None,
) -> None:
    """List upcoming events on a calendar."""
    events = fetch_events(
        calendar_id=calendar_id,
        max_results=max_results,
        query=query,
        time_min=_parse_iso_aware(time_min, "--time-min"),
        time_max=_parse_iso_aware(time_max, "--time-max"),
        profile=profile,
    )
    for ev in events:
        when = f"{ev.start:%Y-%m-%d}" if ev.all_day else f"{ev.start:%Y-%m-%d %H:%M}"
        click.echo(f"{when}  {ev.summary[:50]:50}  [{ev.id}]")


@calendar_cmd.command("get")
@click.argument("event_id")
@click.option("--calendar", "calendar_id", default="primary", show_default=True)
@_profile_option
def calendar_get(event_id: str, calendar_id: str, profile: str | None) -> None:
    """Print a single event's details."""
    ev = fetch_event(event_id, calendar_id=calendar_id, profile=profile)
    click.echo(f"Id:       {ev.id}")
    click.echo(f"Calendar: {ev.calendar_id}")
    click.echo(f"Summary:  {ev.summary}")
    click.echo(f"Status:   {ev.status}")
    click.echo(f"All-day:  {ev.all_day}")
    click.echo(f"Start:    {ev.start.isoformat()}")
    click.echo(f"End:      {ev.end.isoformat()}")
    if ev.location:
        click.echo(f"Location: {ev.location}")
    if ev.attendees:
        click.echo(f"Attendees: {', '.join(ev.attendees)}")
    click.echo(f"Url:      {ev.html_link}")
    if ev.description:
        click.echo("---")
        click.echo(ev.description)


@calendar_cmd.command("create")
@click.option("--summary", required=True)
@click.option(
    "--start",
    "start_str",
    required=True,
    help="ISO datetime, e.g. 2026-05-12T14:00:00-04:00.",
)
@click.option(
    "--end",
    "end_str",
    required=True,
    help="ISO datetime, e.g. 2026-05-12T15:00:00-04:00.",
)
@click.option("--description", default=None)
@click.option("--location", default=None)
@click.option(
    "--attendee",
    "attendees",
    multiple=True,
    help="Attendee email. Repeatable.",
)
@click.option(
    "--all-day",
    is_flag=True,
    help="Treat start/end as date-only (time-of-day ignored).",
)
@click.option("--calendar", "calendar_id", default="primary", show_default=True)
@_profile_option
def calendar_create(
    summary: str,
    start_str: str,
    end_str: str,
    description: str | None,
    location: str | None,
    attendees: tuple[str, ...],
    all_day: bool,
    calendar_id: str,
    profile: str | None,
) -> None:
    """Create a new event."""
    start = _parse_iso_aware(start_str, "--start")
    end = _parse_iso_aware(end_str, "--end")
    assert start is not None and end is not None  # required options
    ev = create_event(
        summary=summary,
        start=start,
        end=end,
        description=description,
        location=location,
        attendees=list(attendees) or None,
        calendar_id=calendar_id,
        all_day=all_day,
        profile=profile,
    )
    click.echo(f"Created: {ev.id}")
    click.echo(f"Url:     {ev.html_link}")


@calendar_cmd.command("update")
@click.argument("event_id")
@click.option("--calendar", "calendar_id", default="primary", show_default=True)
@click.option("--summary", default=None)
@click.option("--start", "start_str", default=None)
@click.option("--end", "end_str", default=None)
@click.option("--description", default=None)
@click.option("--location", default=None)
@click.option(
    "--all-day",
    is_flag=True,
    help=(
        "Mark new start/end as all-day. Required when updating times of an "
        "existing all-day event."
    ),
)
@_profile_option
def calendar_update(
    event_id: str,
    calendar_id: str,
    summary: str | None,
    start_str: str | None,
    end_str: str | None,
    description: str | None,
    location: str | None,
    all_day: bool,
    profile: str | None,
) -> None:
    """PATCH an event. Only options you pass are changed."""
    ev = update_event(
        event_id,
        calendar_id=calendar_id,
        summary=summary,
        start=_parse_iso_aware(start_str, "--start"),
        end=_parse_iso_aware(end_str, "--end"),
        description=description,
        location=location,
        all_day=all_day or None,
        profile=profile,
    )
    click.echo(f"Updated: {ev.id}")
    click.echo(f"Url:     {ev.html_link}")


@calendar_cmd.command("delete")
@click.argument("event_id")
@click.option("--calendar", "calendar_id", default="primary", show_default=True)
@_profile_option
def calendar_delete(event_id: str, calendar_id: str, profile: str | None) -> None:
    """Delete an event."""
    delete_event(event_id, calendar_id=calendar_id, profile=profile)
    click.echo("Deleted.")


@calendar_cmd.command("quick-add")
@click.argument("text")
@click.option("--calendar", "calendar_id", default="primary", show_default=True)
@_profile_option
def calendar_quick_add(text: str, calendar_id: str, profile: str | None) -> None:
    """Create an event from a natural-language string (Google parses it)."""
    ev = quick_add(text, calendar_id=calendar_id, profile=profile)
    click.echo(f"Created: {ev.id}")
    click.echo(f"Summary: {ev.summary}")
    click.echo(f"Url:     {ev.html_link}")


def _parse_iso_aware(value: str | None, option_name: str) -> datetime | None:
    """Parse an ISO datetime; raise click.BadParameter if naive."""
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise click.BadParameter(f"{option_name}: {exc}") from exc
    if parsed.tzinfo is None:
        raise click.BadParameter(
            f"{option_name} must include a timezone offset "
            f"(e.g. ...T14:00:00-04:00 or ...T14:00:00Z)."
        )
    return parsed


@cli.group("ynab")
def ynab_cmd() -> None:
    """YNAB commands (budgets, accounts, categories, transactions)."""


@ynab_cmd.command("budgets")
def ynab_budgets() -> None:
    """List every budget the token can see."""
    for budget in fetch_budgets():
        click.echo(
            f"{budget.id}  {budget.name[:40]:40}  "
            f"{budget.currency_iso_code}  "
            f"(last modified {budget.last_modified_on:%Y-%m-%d})"
        )


@ynab_cmd.command("accounts")
@click.option("--budget", "budget_id", default="last-used", show_default=True)
def ynab_accounts(budget_id: str) -> None:
    """List accounts on a budget with balances."""
    for account in fetch_accounts(budget_id=budget_id):
        marker = " " if account.on_budget else "T"  # T = tracking
        closed = " [closed]" if account.closed else ""
        click.echo(
            f"{marker} {account.type:12} "
            f"{account.name[:30]:30} "
            f"{account.balance_dollars:>12.2f}{closed}  "
            f"[{account.id}]"
        )


@ynab_cmd.command("categories")
@click.option("--budget", "budget_id", default="last-used", show_default=True)
def ynab_categories(budget_id: str) -> None:
    """List category groups with this month's budget/activity/balance."""
    for group in fetch_categories(budget_id=budget_id):
        if group.hidden or group.deleted:
            continue
        click.echo(f"\n# {group.name}")
        for cat in group.categories:
            if cat.hidden or cat.deleted:
                continue
            click.echo(
                f"  {cat.name[:30]:30} "
                f"budgeted {cat.budgeted_dollars:>10.2f}  "
                f"activity {cat.activity_dollars:>10.2f}  "
                f"balance {cat.balance_dollars:>10.2f}"
            )


@ynab_cmd.command("transactions")
@click.option("--budget", "budget_id", default="last-used", show_default=True)
@click.option(
    "--since",
    "since_date",
    default=None,
    help="ISO date lower bound, e.g. 2026-04-01.",
)
@click.option("--account", "account_id", default=None)
@click.option("--category", "category_id", default=None)
@click.option(
    "--max",
    "max_results",
    default=20,
    type=int,
    show_default=True,
    help="Limit how many to print (client-side trim).",
)
def ynab_transactions(
    budget_id: str,
    since_date: str | None,
    account_id: str | None,
    category_id: str | None,
    max_results: int,
) -> None:
    """List transactions, optionally filtered by account/category/date."""
    txns = fetch_transactions(
        budget_id=budget_id,
        since_date=since_date,
        account_id=account_id,
        category_id=category_id,
    )
    for tx in txns[:max_results]:
        click.echo(
            f"{tx.date}  "
            f"{tx.amount_dollars:>10.2f}  "
            f"{tx.payee_name[:24]:24} "
            f"{tx.category_name[:18]:18} "
            f"{(tx.memo or '')[:30]:30}  "
            f"[{tx.id}]"
        )


@ynab_cmd.command("update-tx")
@click.argument("transaction_id")
@click.option("--budget", "budget_id", default="last-used", show_default=True)
@click.option(
    "--memo",
    default=None,
    help="New memo / note (use --clear-memo to clear).",
)
@click.option(
    "--clear-memo",
    is_flag=True,
    help="Clear the memo (mutually exclusive with --memo).",
)
@click.option(
    "--cleared",
    type=click.Choice(["cleared", "uncleared", "reconciled"]),
    default=None,
)
@click.option(
    "--approved/--unapproved",
    "approved",
    default=None,
)
@click.option(
    "--flag",
    "flag_color",
    type=click.Choice(["red", "orange", "yellow", "green", "blue", "purple"]),
    default=None,
)
def ynab_update_tx(
    transaction_id: str,
    budget_id: str,
    memo: str | None,
    clear_memo: bool,
    cleared: str | None,
    approved: bool | None,
    flag_color: str | None,
) -> None:
    """PATCH a transaction. Most common: ``--memo "<new note>"``."""
    if clear_memo and memo is not None:
        raise click.BadParameter("Use either --memo or --clear-memo, not both.")
    memo_arg = YNAB_CLEAR if clear_memo else memo
    tx = update_transaction(
        transaction_id,
        budget_id=budget_id,
        memo=memo_arg,
        cleared=cleared,
        approved=approved,
        flag_color=flag_color,
    )
    click.echo(f"Updated: {tx.id}")
    click.echo(f"  date:   {tx.date}")
    click.echo(f"  amount: {tx.amount_dollars:.2f}")
    click.echo(f"  memo:   {tx.memo!r}")
    click.echo(f"  cleared: {tx.cleared}")


@cli.group()
def whoop() -> None:
    """Whoop commands (recovery, sleep, workouts, cycles, profile)."""


def _whoop_range_opts(func):
    """Shared --start / --end / --max options for paginated whoop commands."""
    func = click.option(
        "--end",
        "end_str",
        default=None,
        help="ISO upper bound, e.g. 2026-05-12T00:00:00-04:00.",
    )(func)
    func = click.option(
        "--start",
        "start_str",
        default=None,
        help="ISO lower bound, e.g. 2026-05-01T00:00:00-04:00.",
    )(func)
    func = click.option(
        "--max",
        "max_records",
        default=10,
        type=int,
        show_default=True,
        help="Max records to fetch.",
    )(func)
    return func


@whoop.command("recoveries")
@_whoop_range_opts
def whoop_recoveries(
    max_records: int, start_str: str | None, end_str: str | None
) -> None:
    """List recovery records (recovery score, HRV, resting HR)."""
    recoveries = fetch_recoveries(
        start=_parse_iso_aware(start_str, "--start"),
        end=_parse_iso_aware(end_str, "--end"),
        max_records=max_records,
    )
    for r in recoveries:
        when = f"{r.created_at:%Y-%m-%d}" if r.created_at else "?"
        score = "--" if r.recovery_score is None else f"{r.recovery_score:g}%"
        hrv = "--" if r.hrv_rmssd_milli is None else f"{r.hrv_rmssd_milli:.1f}ms"
        rhr = "--" if r.resting_heart_rate is None else f"{r.resting_heart_rate:g}bpm"
        click.echo(f"{when}  recovery {score:>5}  hrv {hrv:>8}  rhr {rhr:>7}")


@whoop.command("sleeps")
@_whoop_range_opts
def whoop_sleeps(max_records: int, start_str: str | None, end_str: str | None) -> None:
    """List sleep records (performance %, respiratory rate)."""
    sleeps = fetch_sleeps(
        start=_parse_iso_aware(start_str, "--start"),
        end=_parse_iso_aware(end_str, "--end"),
        max_records=max_records,
    )
    for s in sleeps:
        when = f"{s.start:%Y-%m-%d %H:%M}" if s.start else "?"
        perf = (
            "--"
            if s.sleep_performance_percentage is None
            else f"{s.sleep_performance_percentage:g}%"
        )
        nap = " (nap)" if s.nap else ""
        click.echo(f"{when}  performance {perf:>5}{nap}  [{s.id}]")


@whoop.command("workouts")
@_whoop_range_opts
def whoop_workouts(
    max_records: int, start_str: str | None, end_str: str | None
) -> None:
    """List workout records (strain, avg HR, calories)."""
    workouts = fetch_workouts(
        start=_parse_iso_aware(start_str, "--start"),
        end=_parse_iso_aware(end_str, "--end"),
        max_records=max_records,
    )
    for w in workouts:
        when = f"{w.start:%Y-%m-%d %H:%M}" if w.start else "?"
        strain = "--" if w.strain is None else f"{w.strain:.1f}"
        cals = "--" if w.calories is None else f"{w.calories:.0f}"
        sport = w.sport_name or "workout"
        click.echo(f"{when}  {sport[:20]:20}  strain {strain:>5}  {cals:>6} kcal")


@whoop.command("cycles")
@_whoop_range_opts
def whoop_cycles(max_records: int, start_str: str | None, end_str: str | None) -> None:
    """List physiological cycles (day strain)."""
    cycles = fetch_cycles(
        start=_parse_iso_aware(start_str, "--start"),
        end=_parse_iso_aware(end_str, "--end"),
        max_records=max_records,
    )
    for c in cycles:
        when = f"{c.start:%Y-%m-%d}" if c.start else "?"
        strain = "--" if c.strain is None else f"{c.strain:.1f}"
        click.echo(f"{when}  day strain {strain:>5}  [{c.id}]")


@whoop.command("profile")
def whoop_profile() -> None:
    """Print the authenticated user's basic profile."""
    p = fetch_profile()
    click.echo(f"User id: {p.user_id}")
    click.echo(f"Name:    {p.first_name} {p.last_name}")
    click.echo(f"Email:   {p.email}")


@whoop.command("body")
def whoop_body() -> None:
    """Print the authenticated user's body measurements."""
    b = fetch_body_measurement()
    click.echo(f"Height:         {b.height_meter} m")
    click.echo(f"Weight:         {b.weight_kilogram} kg")
    click.echo(f"Max heart rate: {b.max_heart_rate} bpm")


@cli.group()
def drive() -> None:
    """Google Drive commands (files, folders, sharing)."""


def _fmt_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "        -"
    units = ["B", "K", "M", "G", "T"]
    value = float(size_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:7.1f}{unit}"
        value /= 1024
    return f"{size_bytes}B"


@drive.command("list")
@click.option("--query", "-q", default="", help="Drive query (the `q` param).")
@click.option("--parent", "parent_id", default=None, help="Restrict to a folder id.")
@click.option(
    "--order", "order_by", default=None, help="Sort, e.g. 'modifiedTime desc'."
)
@click.option(
    "--trashed", is_flag=True, help="Include trashed files (default excludes them)."
)
@click.option("--max", "max_results", default=25, type=int, show_default=True)
@_profile_option
def drive_list(
    query: str,
    parent_id: str | None,
    order_by: str | None,
    trashed: bool,
    max_results: int,
    profile: str | None,
) -> None:
    """List / search files and folders."""
    files = list_files(
        query=query,
        parent_id=parent_id,
        include_trashed=trashed,
        order_by=order_by,
        max_results=max_results,
        profile=profile,
    )
    for f in files:
        kind = "DIR " if f.is_folder else "FILE"
        flag = "*" if f.starred else " "
        click.echo(
            f"{kind}{flag} {_fmt_size(f.size_bytes)}  {f.name[:50]:50}  [{f.id}]"
        )


@drive.command("get")
@click.argument("file_id")
@_profile_option
def drive_get(file_id: str, profile: str | None) -> None:
    """Print a file's metadata."""
    f = fetch_file(file_id, profile=profile)
    click.echo(f"Id:        {f.id}")
    click.echo(f"Name:      {f.name}")
    click.echo(f"MIME:      {f.mime_type}")
    click.echo(f"Folder:    {f.is_folder}")
    click.echo(f"Size:      {f.size_bytes if f.size_bytes is not None else '-'}")
    click.echo(f"Parents:   {', '.join(f.parents)}")
    click.echo(f"Modified:  {f.modified_time.isoformat() if f.modified_time else '-'}")
    click.echo(f"Owners:    {', '.join(f.owner_emails)}")
    click.echo(f"Shared:    {f.shared}")
    click.echo(f"Trashed:   {f.trashed}")
    click.echo(f"Url:       {f.web_view_link}")


@drive.command("mkdir")
@click.argument("name")
@click.option("--parent", "parent_id", default=None, help="Parent folder id.")
@_profile_option
def drive_mkdir(name: str, parent_id: str | None, profile: str | None) -> None:
    """Create a folder."""
    folder = create_folder(name, parent_id=parent_id, profile=profile)
    click.echo(f"Created folder: {folder.id}")
    click.echo(f"Url:            {folder.web_view_link}")


@drive.command("upload")
@click.argument(
    "local_path", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.option("--name", default=None, help="Name in Drive (default: local name).")
@click.option("--parent", "parent_id", default=None, help="Parent folder id.")
@_profile_option
def drive_upload(
    local_path: Path,
    name: str | None,
    parent_id: str | None,
    profile: str | None,
) -> None:
    """Upload a local file to Drive."""
    f = upload_file(local_path, name=name, parent_id=parent_id, profile=profile)
    click.echo(f"Uploaded: {f.id}")
    click.echo(f"Url:      {f.web_view_link}")


@drive.command("download")
@click.argument("file_id")
@click.argument("local_path", type=click.Path(dir_okay=False, path_type=Path))
@_profile_option
def drive_download(file_id: str, local_path: Path, profile: str | None) -> None:
    """Download a binary file's content to LOCAL_PATH."""
    dest = download_file(file_id, local_path, profile=profile)
    click.echo(f"Downloaded to: {dest}")


@drive.command("export")
@click.argument("file_id")
@click.argument("local_path", type=click.Path(dir_okay=False, path_type=Path))
@click.option(
    "--mime",
    "mime_type",
    required=True,
    help="Export MIME type, e.g. application/pdf or text/csv.",
)
@_profile_option
def drive_export(
    file_id: str, local_path: Path, mime_type: str, profile: str | None
) -> None:
    """Export a Google-native doc (Docs/Sheets/Slides) to LOCAL_PATH."""
    dest = export_file(file_id, local_path, mime_type=mime_type, profile=profile)
    click.echo(f"Exported to: {dest}")


@drive.command("rename")
@click.argument("file_id")
@click.argument("new_name")
@_profile_option
def drive_rename(file_id: str, new_name: str, profile: str | None) -> None:
    """Rename a file or folder."""
    from mgdio.drive import update_file

    f = update_file(file_id, name=new_name, profile=profile)
    click.echo(f"Renamed: {f.name}  [{f.id}]")


@drive.command("move")
@click.argument("file_id")
@click.argument("new_parent_id")
@_profile_option
def drive_move(file_id: str, new_parent_id: str, profile: str | None) -> None:
    """Move a file into a different folder."""
    f = move_file(file_id, new_parent_id, profile=profile)
    click.echo(f"Moved: {f.name}  -> parents {', '.join(f.parents)}")


@drive.command("copy")
@click.argument("file_id")
@click.option("--name", default=None, help="Name for the copy.")
@click.option("--parent", "parent_id", default=None, help="Destination folder id.")
@_profile_option
def drive_copy(
    file_id: str,
    name: str | None,
    parent_id: str | None,
    profile: str | None,
) -> None:
    """Copy a file."""
    f = copy_file(file_id, name=name, parent_id=parent_id, profile=profile)
    click.echo(f"Copied to: {f.id}")
    click.echo(f"Url:       {f.web_view_link}")


@drive.command("trash")
@click.argument("file_id")
@click.option("--restore", is_flag=True, help="Restore from trash instead.")
@_profile_option
def drive_trash(file_id: str, restore: bool, profile: str | None) -> None:
    """Move a file to the trash (or --restore it)."""
    f = trash_file(file_id, trashed=not restore, profile=profile)
    state = "restored" if restore else "trashed"
    click.echo(f"{state.capitalize()}: {f.name}  [{f.id}]")


@drive.command("delete")
@click.argument("file_id")
@_profile_option
def drive_delete(file_id: str, profile: str | None) -> None:
    """Permanently delete a file (skips the trash -- irreversible)."""
    delete_file(file_id, profile=profile)
    click.echo("Deleted.")


@drive.command("empty-trash")
@_profile_option
def drive_empty_trash(profile: str | None) -> None:
    """Permanently delete every trashed file (irreversible)."""
    from mgdio.drive import empty_trash

    empty_trash(profile=profile)
    click.echo("Trash emptied.")


@drive.command("perms")
@click.argument("file_id")
@_profile_option
def drive_perms(file_id: str, profile: str | None) -> None:
    """List a file's sharing permissions."""
    for p in list_permissions(file_id, profile=profile):
        who = p.email_address or p.domain or p.type
        click.echo(f"{p.role:12} {p.type:8} {who[:40]:40}  [{p.id}]")


@drive.command("share")
@click.argument("file_id")
@click.option("--role", default="reader", show_default=True)
@click.option("--email", default=None, help="Share with a person/group email.")
@click.option("--domain", default=None, help="Share with a Workspace domain.")
@click.option("--anyone", is_flag=True, help="Share with anyone who has the link.")
@click.option("--notify", is_flag=True, help="Email the grantee (user/group only).")
@_profile_option
def drive_share(
    file_id: str,
    role: str,
    email: str | None,
    domain: str | None,
    anyone: bool,
    notify: bool,
    profile: str | None,
) -> None:
    """Grant a sharing permission on a file."""
    p = share_file(
        file_id,
        role=role,
        email=email,
        domain=domain,
        anyone=anyone,
        send_notification=notify,
        profile=profile,
    )
    click.echo(f"Granted {p.role} to {p.email_address or p.domain or p.type}")
    click.echo(f"Permission id: {p.id}")


@drive.command("unshare")
@click.argument("file_id")
@click.argument("permission_id")
@_profile_option
def drive_unshare(file_id: str, permission_id: str, profile: str | None) -> None:
    """Revoke a sharing permission (id from `drive perms`)."""
    unshare_file(file_id, permission_id, profile=profile)
    click.echo("Revoked.")


@cli.group()
def maps() -> None:
    """Google Maps commands (geocoding, distance, directions)."""


def _route_opts(func):
    """Attach shared --mode / --units options to a route command."""
    func = click.option(
        "--units",
        type=click.Choice(["imperial", "metric"]),
        default="imperial",
        show_default=True,
        help="Units for the distance/duration text.",
    )(func)
    func = click.option(
        "--mode",
        type=click.Choice(["driving", "walking", "bicycling", "transit"]),
        default="driving",
        show_default=True,
        help="Travel mode.",
    )(func)
    return func


@maps.command("geocode")
@click.argument("address")
def maps_geocode(address: str) -> None:
    """Geocode an address / place to its formatted address + coordinates."""
    results = geocode(address)
    if not results:
        click.echo("No match found.")
        return
    for r in results:
        click.echo(f"{r.formatted_address}  ({r.latlng})  [{r.location_type}]")


@maps.command("reverse")
@click.argument("latlng")
def maps_reverse(latlng: str) -> None:
    """Reverse-geocode a coordinate to a postal address.

    LATLNG is a single "latitude,longitude" string, e.g.
    "40.714,-74.006" (a single token so the negative longitude isn't
    parsed as an option).
    """
    parts = latlng.replace(" ", "").split(",")
    if len(parts) != 2:
        raise click.UsageError('LATLNG must be "latitude,longitude".')
    try:
        latitude, longitude = float(parts[0]), float(parts[1])
    except ValueError as exc:
        raise click.UsageError(f"Invalid coordinate {latlng!r}: {exc}")
    results = reverse_geocode(latitude, longitude)
    if not results:
        click.echo("No match found.")
        return
    click.echo(results[0].formatted_address)


@maps.command("distance")
@click.argument("origin")
@click.argument("destination")
@_route_opts
def maps_distance(origin: str, destination: str, mode: str, units: str) -> None:
    """Print the travel distance between two locations."""
    route = fetch_route(origin, destination, mode=mode, units=units)
    click.echo(route.distance_text)


@maps.command("duration")
@click.argument("origin")
@click.argument("destination")
@_route_opts
def maps_duration(origin: str, destination: str, mode: str, units: str) -> None:
    """Print the travel time between two locations."""
    route = fetch_route(origin, destination, mode=mode, units=units)
    click.echo(route.duration_text)


@maps.command("directions")
@click.argument("origin")
@click.argument("destination")
@_route_opts
def maps_directions(origin: str, destination: str, mode: str, units: str) -> None:
    """Print turn-by-turn directions between two locations."""
    route = fetch_route(origin, destination, mode=mode, units=units)
    click.echo(f"{route.distance_text}, {route.duration_text}")
    for i, step in enumerate(route.instructions, start=1):
        click.echo(f"  {i}. {step}")


@cli.group()
def skills() -> None:
    """Manage bundled Claude Code skills."""


@skills.command("list")
def skills_list() -> None:
    """List the Claude Code skills bundled with this mgdio version."""
    with iter_skill_dirs() as skill_dirs:
        if not skill_dirs:
            click.echo("(no skills bundled in this build)")
            return
        for src in skill_dirs:
            description = _read_skill_description(src / "SKILL.md")
            click.echo(f"{src.name}")
            if description:
                # Indent the description; wrap to ~75 chars for readability.
                first = description.splitlines()[0]
                click.echo(f"  {first}")


@skills.command("deploy")
@click.option(
    "--global",
    "global_install",
    is_flag=True,
    help=(
        "Install to ~/.claude/skills/ (cross-project). "
        "Default: current project's .claude/skills/."
    ),
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing skill directories instead of skipping.",
)
def skills_deploy(global_install: bool, force: bool) -> None:
    """Copy bundled mgdio skills into a Claude Code skills directory.

    Default target: ``./.claude/skills/`` (the current project).
    With ``--global``: ``~/.claude/skills/`` (every project).

    Existing skill directories are skipped unless ``--force`` is passed.
    """
    if global_install:
        target_root = Path.home() / ".claude" / "skills"
    else:
        target_root = Path.cwd() / ".claude" / "skills"
    target_root.mkdir(parents=True, exist_ok=True)

    deployed = 0
    skipped = 0
    with iter_skill_dirs() as skill_dirs:
        for src in skill_dirs:
            dest = target_root / src.name
            if dest.exists() and not force:
                click.echo(f"skip   {dest}  (exists; pass --force to overwrite)")
                skipped += 1
                continue
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
            click.echo(f"deploy {dest}")
            deployed += 1

    click.echo(
        f"\n{deployed} deployed, {skipped} skipped to {target_root}.\n"
        "Restart Claude Code (or /clear) for the skills to load."
    )


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_DESCRIPTION_RE = re.compile(
    r"^description:\s*(.+?)(?=\n[a-zA-Z_-]+:|\Z)", re.DOTALL | re.MULTILINE
)


def _read_skill_description(skill_md_path: Path) -> str:
    """Return the ``description`` field from a SKILL.md's YAML frontmatter.

    Best-effort: returns an empty string if the file is malformed.
    """
    try:
        text = skill_md_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    front = _FRONTMATTER_RE.match(text)
    if not front:
        return ""
    body = front.group(1)
    match = _DESCRIPTION_RE.search(body)
    if not match:
        return ""
    # Collapse the multi-line description into a single line.
    return " ".join(match.group(1).split())


if __name__ == "__main__":
    cli()
