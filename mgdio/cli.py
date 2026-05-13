"""``mgdio`` console-script entry point."""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

import click

from mgdio.auth.google import clear_stored_token as clear_google_token
from mgdio.auth.google import (
    get_credentials,
)
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
from mgdio.gmail import fetch_message, fetch_messages, send_email
from mgdio.sheets import (
    append_values,
    clear_values,
    create_spreadsheet,
    fetch_spreadsheet,
    fetch_values,
    write_values,
)
from mgdio.skills import iter_skill_dirs
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


@auth.command("google")
@click.option(
    "--reset",
    is_flag=True,
    help="Delete the stored token before running, forcing a fresh consent flow.",
)
@click.option(
    "--headless",
    is_flag=True,
    help=(
        "Use the copy-paste flow instead of the localhost setup page. "
        "For machines without a browser (e.g. a Linux VPS)."
    ),
)
def auth_google(reset: bool, headless: bool) -> None:
    """Run (or re-run) the Google OAuth onboarding flow.

    Requests Gmail + Calendar + Sheets scopes in a single consent screen.
    Token is stored in your OS keyring under ``mgdio:google``.

    Pass ``--headless`` on machines without a browser (e.g. a Linux VPS):
    mgdio will print the auth URL and prompt for the resulting redirect
    URL to be pasted back, instead of opening a localhost setup page.
    """
    if reset:
        clear_google_token()
    get_credentials(headless=headless)
    click.echo("Authenticated.")


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
def gmail_list(query: str, max_results: int) -> None:
    """List recent inbox messages (subject + sender + date)."""
    for message in fetch_messages(query, max_results):
        click.echo(
            f"{message.date:%Y-%m-%d %H:%M}  "
            f"{message.sender[:40]:40}  "
            f"{message.subject}  "
            f"[{message.id}]"
        )


@gmail.command("get")
@click.argument("message_id")
def gmail_get(message_id: str) -> None:
    """Print one message's headers, snippet, and plain-text body."""
    message = fetch_message(message_id)
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
def gmail_send(
    to: str,
    subject: str,
    body: str,
    cc: str | None,
    bcc: str | None,
    html: str | None,
    attachments: tuple[Path, ...],
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
    )
    click.echo(f"Sent: {message_id}")


@cli.group()
def sheets() -> None:
    """Google Sheets commands."""


@sheets.command("info")
@click.argument("spreadsheet_id")
def sheets_info(spreadsheet_id: str) -> None:
    """Print metadata about a spreadsheet (title, tabs, url)."""
    sheet = fetch_spreadsheet(spreadsheet_id)
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
def sheets_read(spreadsheet_id: str, range_: str) -> None:
    """Print a tab-separated dump of a range."""
    for row in fetch_values(spreadsheet_id, range_):
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
def sheets_write(
    spreadsheet_id: str,
    range_: str,
    rows: tuple[str, ...],
    raw: bool,
) -> None:
    """Overwrite a range with --row values (comma-separated cells)."""
    values = [row.split(",") for row in rows]
    updated = write_values(spreadsheet_id, range_, values, raw=raw)
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
def sheets_append(
    spreadsheet_id: str,
    range_: str,
    rows: tuple[str, ...],
    raw: bool,
) -> None:
    """Append --row values to the end of the table at range_."""
    values = [row.split(",") for row in rows]
    updated = append_values(spreadsheet_id, range_, values, raw=raw)
    click.echo(f"Appended cells: {updated}")


@sheets.command("clear")
@click.argument("spreadsheet_id")
@click.argument("range_")
def sheets_clear(spreadsheet_id: str, range_: str) -> None:
    """Clear all values in range_ (formatting preserved)."""
    clear_values(spreadsheet_id, range_)
    click.echo("Cleared.")


@sheets.command("create")
@click.option("--title", required=True, help="New spreadsheet title.")
@click.option(
    "--tab",
    "tabs",
    multiple=True,
    help="Initial tab name. Repeatable.",
)
def sheets_create(title: str, tabs: tuple[str, ...]) -> None:
    """Create a new spreadsheet."""
    spreadsheet = create_spreadsheet(title, sheet_names=list(tabs) or None)
    click.echo(f"Created: {spreadsheet.id}")
    click.echo(f"Url:     {spreadsheet.url}")


@cli.group("calendar")
def calendar_cmd() -> None:
    """Google Calendar commands."""


@calendar_cmd.command("list-cals")
def calendar_list_cals() -> None:
    """List every calendar the authenticated user has access to."""
    for cal in fetch_calendars():
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
def calendar_list_events(
    calendar_id: str,
    max_results: int,
    query: str,
    time_min: str | None,
    time_max: str | None,
) -> None:
    """List upcoming events on a calendar."""
    events = fetch_events(
        calendar_id=calendar_id,
        max_results=max_results,
        query=query,
        time_min=_parse_iso_aware(time_min, "--time-min"),
        time_max=_parse_iso_aware(time_max, "--time-max"),
    )
    for ev in events:
        when = f"{ev.start:%Y-%m-%d}" if ev.all_day else f"{ev.start:%Y-%m-%d %H:%M}"
        click.echo(f"{when}  {ev.summary[:50]:50}  [{ev.id}]")


@calendar_cmd.command("get")
@click.argument("event_id")
@click.option("--calendar", "calendar_id", default="primary", show_default=True)
def calendar_get(event_id: str, calendar_id: str) -> None:
    """Print a single event's details."""
    ev = fetch_event(event_id, calendar_id=calendar_id)
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
def calendar_create(
    summary: str,
    start_str: str,
    end_str: str,
    description: str | None,
    location: str | None,
    attendees: tuple[str, ...],
    all_day: bool,
    calendar_id: str,
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
def calendar_update(
    event_id: str,
    calendar_id: str,
    summary: str | None,
    start_str: str | None,
    end_str: str | None,
    description: str | None,
    location: str | None,
    all_day: bool,
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
    )
    click.echo(f"Updated: {ev.id}")
    click.echo(f"Url:     {ev.html_link}")


@calendar_cmd.command("delete")
@click.argument("event_id")
@click.option("--calendar", "calendar_id", default="primary", show_default=True)
def calendar_delete(event_id: str, calendar_id: str) -> None:
    """Delete an event."""
    delete_event(event_id, calendar_id=calendar_id)
    click.echo("Deleted.")


@calendar_cmd.command("quick-add")
@click.argument("text")
@click.option("--calendar", "calendar_id", default="primary", show_default=True)
def calendar_quick_add(text: str, calendar_id: str) -> None:
    """Create an event from a natural-language string (Google parses it)."""
    ev = quick_add(text, calendar_id=calendar_id)
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
