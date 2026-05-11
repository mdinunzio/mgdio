"""``mgdio`` console-script entry point."""

from __future__ import annotations

from pathlib import Path

import click

from mgdio.auth.google import clear_stored_token, get_credentials
from mgdio.gmail import fetch_message, fetch_messages, send_email
from mgdio.sheets import (
    append_values,
    clear_values,
    create_spreadsheet,
    fetch_spreadsheet,
    fetch_values,
    write_values,
)


@click.group()
def cli() -> None:
    """mgdio: personal connectivity tools."""


@cli.group()
def auth() -> None:
    """Authentication commands.

    Future providers will land as siblings:

      mgdio auth ynab     # planned

      mgdio auth twilio   # planned
    """


@auth.command("google")
@click.option(
    "--reset",
    is_flag=True,
    help="Delete the stored token before running, forcing a fresh consent flow.",
)
def auth_google(reset: bool) -> None:
    """Run (or re-run) the Google OAuth onboarding flow.

    Requests Gmail + Calendar + Sheets scopes in a single consent screen.
    Token is stored in your OS keyring under ``mgdio:google``.
    """
    if reset:
        clear_stored_token()
    get_credentials()
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


if __name__ == "__main__":
    cli()
