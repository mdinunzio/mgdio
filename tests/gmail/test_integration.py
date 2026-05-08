"""Opt-in integration tests that hit the real Gmail API.

Skipped unless ``MGDIO_RUN_INTEGRATION=1`` is set. These exercise the
full read+send round-trip against the authenticated user's mailbox, so a
``client_secret.json`` and a previously-completed OAuth flow are required.
"""

from __future__ import annotations

import os
import time
import uuid

import pytest

pytestmark = pytest.mark.integration

if os.getenv("MGDIO_RUN_INTEGRATION") != "1":
    pytest.skip(
        "MGDIO_RUN_INTEGRATION!=1; skipping real-API tests",
        allow_module_level=True,
    )


def test_fetch_messages_returns_list():
    from mgdio.gmail import fetch_messages

    result = fetch_messages(max_results=1)
    assert isinstance(result, list)


def test_send_then_search_round_trip():
    from mgdio.gmail import fetch_messages, get_credentials, send_email

    creds = get_credentials()
    me = getattr(creds, "id_token", None) or os.environ.get(
        "MGDIO_INTEGRATION_TO", "mdinunzio@gmail.com"
    )
    token = uuid.uuid4().hex[:12]
    subject = f"mgdio integration test {token}"

    sent_id = send_email(to=me, subject=subject, body="round-trip body")
    assert sent_id

    found = []
    for _ in range(10):
        found = fetch_messages(query=f"subject:{token}", max_results=5)
        if found:
            break
        time.sleep(2)

    assert any(token in m.subject for m in found)
