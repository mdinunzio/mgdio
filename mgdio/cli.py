"""``mgdio`` console-script entry point.

Currently exposes the authentication subsystem only. Service commands
(gmail / calendar / sheets) will land in follow-up PRs on top of
:mod:`mgdio.auth.google`.
"""

from __future__ import annotations

import click

from mgdio.auth.google import clear_stored_token, get_credentials


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


if __name__ == "__main__":
    cli()
