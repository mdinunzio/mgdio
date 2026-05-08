"""Gmail end-to-end demo for the mgdio package.

Run this after installing mgdio (``uv add mgdio`` or ``uv pip install -e .``)
and completing the one-time OAuth setup (``uv run mgdio auth gmail``).

Walks through the four common operations:

1. Authenticate (no-op if you already did ``mgdio auth gmail``).
2. List recent inbox messages.
3. Search with Gmail's query syntax.
4. Send a plain-text email and a richer HTML+attachment email to yourself.

Usage:
    uv run python examples/gmail.py             # send to the authed user
    uv run python examples/gmail.py you@x.com   # send to a custom address
"""

from __future__ import annotations

import sys
import tempfile
import uuid
from pathlib import Path

from mgdio.gmail import fetch_messages, get_credentials, send_email


def main(recipient: str | None = None) -> None:
    """Run the Gmail demo: auth, list, search, send plain, send HTML+attach."""
    print("== 1. Authenticate ==")
    creds = get_credentials()
    print(f"   token valid: {creds.valid}")

    print("\n== 2. List the 5 most recent inbox messages ==")
    for message in fetch_messages(max_results=5):
        print(
            f"   {message.date:%Y-%m-%d %H:%M}  "
            f"{message.sender[:40]:40}  {message.subject}"
        )

    print("\n== 3. Search: messages from yourself in the last 30 days ==")
    me = recipient or _resolve_self_address()
    query = f"from:{me} newer_than:30d"
    hits = fetch_messages(query=query, max_results=3)
    print(f"   query: {query!r}  -> {len(hits)} match(es)")
    for message in hits:
        print(f"   - {message.subject}  ({message.snippet[:60]}...)")

    print("\n== 4a. Send a plain-text email to yourself ==")
    token = uuid.uuid4().hex[:8]
    plain_id = send_email(
        to=me,
        subject=f"mgdio demo (plain) {token}",
        body="Hello from the mgdio Gmail demo. This is a plain-text message.",
    )
    print(f"   sent message id: {plain_id}")

    print("\n== 4b. Send an HTML email with an attachment ==")
    attachment_path = _write_demo_attachment(token)
    rich_id = send_email(
        to=me,
        subject=f"mgdio demo (html+attach) {token}",
        body="Plain-text fallback for clients without HTML support.",
        html=(
            "<h2>Hello from <code>mgdio</code></h2>"
            "<p>This message was sent via the Gmail API with both an HTML "
            "body and an attachment.</p>"
        ),
        attachments=[attachment_path],
    )
    print(f"   sent message id: {rich_id}")
    print(f"   attachment: {attachment_path}")

    print("\nDone. Check your inbox for two messages tagged " f"'{token}'.")


def _resolve_self_address() -> str:
    """Return the authenticated user's email via Gmail's getProfile endpoint."""
    from mgdio.gmail import get_service

    profile = get_service().users().getProfile(userId="me").execute()
    return profile["emailAddress"]


def _write_demo_attachment(token: str) -> Path:
    path = Path(tempfile.gettempdir()) / f"mgdio_demo_{token}.txt"
    path.write_text(f"mgdio demo attachment\ntoken: {token}\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    main(recipient=arg)
