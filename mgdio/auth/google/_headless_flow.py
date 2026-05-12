"""Copy-paste OAuth flow for machines without a browser (Linux VPS, etc).

The browser-based flow in :mod:`mgdio.auth.google._setup_server` assumes
a GUI is available on the host. When that's not true (a Linux VPS, a
Docker container, an SSH session into a server), we use the lower-level
``google_auth_oauthlib.flow.Flow`` with ``redirect_uri="http://localhost:
<port>"``, print the authorization URL on the terminal, and read the
resulting failed-redirect URL back from stdin.

Why this works (and why the obvious alternatives don't):

* ``InstalledAppFlow.run_console()`` -- removed from
  ``google-auth-oauthlib`` in Feb 2022.
* The ``urn:ietf:wg:oauth:2.0:oob`` redirect -- blocked by Google in
  Jan 2023.
* OAuth Device Authorization Grant -- only available for TV / limited-
  input OAuth client types, not for the "Desktop app" client we use.
* ``gcloud --no-launch-browser`` -- proxy pattern that needs gcloud
  installed on both machines.

What the user sees:

1. We print the authorization URL.
2. They open it on a device that *does* have a browser (laptop, phone).
3. After granting consent, Google redirects to
   ``http://localhost:<port>/?state=...&code=...`` -- which fails to
   load on the user's laptop (nothing's listening there). That's
   expected.
4. They copy the *whole failed-redirect URL* from the address bar and
   paste it back into the terminal.
5. ``flow.fetch_token(authorization_response=...)`` parses the ``code``
   out and exchanges it for credentials. State is validated to catch
   typos and CSRF.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from mgdio.auth.google._setup_server import _looks_like_client_secret
from mgdio.exceptions import MissingClientSecretError

logger = logging.getLogger(__name__)

# Any port works -- the VPS does NOT listen on it. The browser on the
# user's laptop is the only thing that tries to load this URL, and
# "connection refused" is the expected outcome: by then we've already
# read the URL from the address bar.
HEADLESS_REDIRECT_PORT: int = 8765
HEADLESS_REDIRECT_URI: str = f"http://localhost:{HEADLESS_REDIRECT_PORT}/"


def run_headless_flow(
    client_secret_path: Path,
    scopes: list[str],
) -> Credentials:
    """Run the copy-paste OAuth flow and return credentials.

    Args:
        client_secret_path: Where ``client_secret.json`` lives (or
            should be saved if absent). If absent, the user is prompted
            to paste the JSON contents.
        scopes: OAuth scopes to request.

    Returns:
        Valid ``google.oauth2.credentials.Credentials``. The caller is
        responsible for persisting them.

    Raises:
        MissingClientSecretError: If ``client_secret_path`` is missing
            and the user doesn't paste a valid JSON body.
        RuntimeError: If ``fetch_token`` rejects the pasted URL (most
            commonly: state mismatch, expired auth code, wrong URL).
    """
    if not client_secret_path.exists():
        _prompt_and_save_client_secret(client_secret_path)

    flow = Flow.from_client_secrets_file(
        str(client_secret_path),
        scopes=scopes,
        redirect_uri=HEADLESS_REDIRECT_URI,
    )
    auth_url, _state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )

    _print_instructions(auth_url)
    pasted = _read_pasted_response()

    try:
        flow.fetch_token(authorization_response=pasted)
    except Exception as exc:  # google-auth raises various subclasses
        raise RuntimeError(
            f"Failed to exchange the pasted URL for a token: {exc}. "
            "If you see 'mismatching_state', the URL came from a "
            "different terminal session -- run `mgdio auth google "
            "--headless` again and use the SAME session for both the "
            "auth URL and the paste."
        ) from exc

    return flow.credentials


def _print_instructions(auth_url: str) -> None:
    """Print the auth URL + step-by-step copy-paste instructions to stderr."""
    msg = (
        "\n=== mgdio headless Google auth ===\n\n"
        "1. On a machine WITH a browser, open this URL:\n\n"
        f"   {auth_url}\n\n"
        "2. Sign in with the Google account you want to authorize.\n"
        "3. Click 'Continue' / 'Allow' through the consent screen.\n"
        "4. Your browser will be redirected to a 'localhost' URL that\n"
        "   FAILS to load -- that's EXPECTED. Copy the FULL URL from\n"
        "   the address bar (it starts with\n"
        f"   '{HEADLESS_REDIRECT_URI}?state=...').\n"
        "5. Paste it below and press Enter.\n"
    )
    # stderr so stdout stays clean for callers that might pipe output.
    print(msg, file=sys.stderr, flush=True)


def _read_pasted_response() -> str:
    """Read the redirect URL from stdin. Raises if empty."""
    pasted = input("paste redirect URL > ").strip()
    if not pasted:
        raise RuntimeError("No URL pasted; aborting.")
    return pasted


def _prompt_and_save_client_secret(client_secret_path: Path) -> None:
    """Prompt the user to paste ``client_secret.json`` and save it.

    Args:
        client_secret_path: Target on-disk location.

    Raises:
        MissingClientSecretError: If the paste is empty, not valid JSON,
            or doesn't look like a Google OAuth client secret file.
    """
    print(
        f"\nNo client_secret.json found at {client_secret_path}.\n"
        "Paste the JSON contents below. End with a blank line:\n",
        file=sys.stderr,
        flush=True,
    )
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "" and lines:
            break
        lines.append(line)
    raw = "\n".join(lines).strip()
    if not raw:
        raise MissingClientSecretError(
            "No client_secret JSON pasted; aborting headless setup."
        )
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MissingClientSecretError(
            f"Pasted content is not valid JSON: {exc}"
        ) from exc
    if not _looks_like_client_secret(parsed):
        raise MissingClientSecretError(
            "Pasted JSON doesn't look like a Google OAuth client_secret "
            "file (expected an 'installed' or 'web' top-level key with "
            "client_id and client_secret)."
        )
    client_secret_path.parent.mkdir(parents=True, exist_ok=True)
    client_secret_path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
    logger.info("Saved client_secret.json to %s", client_secret_path)
