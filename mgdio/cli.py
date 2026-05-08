"""``mgdio`` console-script entry point."""

from __future__ import annotations

import click

from mgdio.gmail import (
    clear_stored_token,
    fetch_messages,
    get_credentials,
    send_email,
)


@click.group()
def cli() -> None:
    """mgdio: personal connectivity tools."""


@cli.group()
def auth() -> None:
    """Authentication commands."""


@auth.command("gmail")
def auth_gmail() -> None:
    """Run (or re-run) the Gmail OAuth onboarding flow.

    Opens a localhost setup page in your browser with instructions, a
    drag-and-drop slot for ``client_secret.json``, and an Authorize
    button that triggers Google's consent screen. The resulting token
    is saved to your OS keyring.
    """
    get_credentials()
    click.echo("Authenticated.")


@cli.command()
def logout() -> None:
    """Delete the cached OAuth token from the OS keyring."""
    clear_stored_token()
    click.echo("Token cleared.")


@cli.group()
def gmail() -> None:
    """Gmail commands."""


@gmail.command("list")
@click.option("--query", "-q", default="", help="Gmail search query.")
@click.option("--max", "max_results", default=5, type=int, show_default=True)
def gmail_list(query: str, max_results: int) -> None:
    """List recent emails (subject line + sender + date)."""
    for message in fetch_messages(query, max_results):
        click.echo(
            f"{message.date:%Y-%m-%d %H:%M}  "
            f"{message.sender:40.40}  "
            f"{message.subject}"
        )


@gmail.command("send")
@click.option("--to", required=True)
@click.option("--subject", required=True)
@click.option("--body", required=True)
def gmail_send(to: str, subject: str, body: str) -> None:
    """Send a plain-text email."""
    message_id = send_email(to=to, subject=subject, body=body)
    click.echo(f"Sent: {message_id}")


if __name__ == "__main__":
    cli()
