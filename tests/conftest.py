"""Shared pytest fixtures for the mgdio test suite."""

from __future__ import annotations

import base64
from unittest.mock import MagicMock

import pytest

from mgdio import settings as mgdio_settings
from mgdio.auth.google import auth as google_auth
from mgdio.auth.ynab import auth as ynab_auth
from mgdio.calendar import client as calendar_client
from mgdio.gmail import client as gmail_client
from mgdio.sheets import client as sheets_client
from mgdio.ynab import client as ynab_client


@pytest.fixture(autouse=True)
def reset_caches() -> None:
    """Reset module-level credential and service caches between tests."""
    google_auth.reset_credentials_cache()
    ynab_auth.reset_token_cache()
    gmail_client.reset_service_cache()
    sheets_client.reset_service_cache()
    calendar_client.reset_service_cache()
    ynab_client.reset_session_cache()
    yield
    google_auth.reset_credentials_cache()
    ynab_auth.reset_token_cache()
    gmail_client.reset_service_cache()
    sheets_client.reset_service_cache()
    calendar_client.reset_service_cache()
    ynab_client.reset_session_cache()


@pytest.fixture
def tmp_appdata(tmp_path, monkeypatch):
    """Point all mgdio paths at a temp directory."""
    google_dir = tmp_path / "google"
    google_dir.mkdir(parents=True, exist_ok=True)
    client_secret = google_dir / "client_secret.json"

    monkeypatch.setattr(mgdio_settings, "APP_DATA_DIR", tmp_path)
    monkeypatch.setattr(mgdio_settings, "GOOGLE_DATA_DIR", google_dir)
    monkeypatch.setattr(mgdio_settings, "GOOGLE_CLIENT_SECRET_PATH", client_secret)
    monkeypatch.setattr(google_auth, "GOOGLE_CLIENT_SECRET_PATH", client_secret)
    return tmp_path


@pytest.fixture
def fake_keyring(monkeypatch):
    """Replace ``keyring`` calls in ``mgdio.auth.google.auth`` with a memory store."""
    import keyring as real_keyring

    store: dict[tuple[str, str], str] = {}

    class _FakeKeyring:
        errors = real_keyring.errors

        @staticmethod
        def get_password(service: str, username: str) -> str | None:
            return store.get((service, username))

        @staticmethod
        def set_password(service: str, username: str, password: str) -> None:
            store[(service, username)] = password

        @staticmethod
        def delete_password(service: str, username: str) -> None:
            try:
                del store[(service, username)]
            except KeyError as exc:
                raise real_keyring.errors.PasswordDeleteError(str(exc)) from exc

    monkeypatch.setattr(google_auth, "keyring", _FakeKeyring)
    monkeypatch.setattr(ynab_auth, "keyring", _FakeKeyring)
    return store


@pytest.fixture
def mock_gmail_service(monkeypatch) -> MagicMock:
    """Patch :func:`mgdio.gmail.client.get_service` to return a MagicMock."""
    service = MagicMock(name="GmailService")
    monkeypatch.setattr(gmail_client, "_service", service)
    monkeypatch.setattr("mgdio.gmail.messages.get_service", lambda: service)
    monkeypatch.setattr("mgdio.gmail.sender.get_service", lambda: service)
    return service


@pytest.fixture
def mock_sheets_service(monkeypatch) -> MagicMock:
    """Patch :func:`mgdio.sheets.client.get_service` to return a MagicMock."""
    service = MagicMock(name="SheetsService")
    monkeypatch.setattr(sheets_client, "_service", service)
    monkeypatch.setattr("mgdio.sheets.values.get_service", lambda: service)
    monkeypatch.setattr("mgdio.sheets.spreadsheets.get_service", lambda: service)
    return service


@pytest.fixture
def mock_calendar_service(monkeypatch) -> MagicMock:
    """Patch :func:`mgdio.calendar.client.get_service` to return a MagicMock."""
    service = MagicMock(name="CalendarService")
    monkeypatch.setattr(calendar_client, "_service", service)
    monkeypatch.setattr("mgdio.calendar.events.get_service", lambda: service)
    monkeypatch.setattr("mgdio.calendar.calendars.get_service", lambda: service)
    return service


@pytest.fixture
def mock_ynab_request(monkeypatch) -> MagicMock:
    """Patch ``mgdio.ynab.client.request`` everywhere it's imported.

    Returns the ``MagicMock`` so the test sets ``return_value`` (a ``data``
    envelope) or ``side_effect``. Inspect ``call_args`` to assert path /
    params.
    """
    mock = MagicMock(name="ynab_client.request")
    monkeypatch.setattr("mgdio.ynab.budgets.request", mock)
    monkeypatch.setattr("mgdio.ynab.accounts.request", mock)
    monkeypatch.setattr("mgdio.ynab.categories.request", mock)
    monkeypatch.setattr("mgdio.ynab.transactions.request", mock)
    return mock


@pytest.fixture
def mock_ynab_raw_request(monkeypatch) -> MagicMock:
    """Patch ``mgdio.ynab.client.raw_request`` (used by update_transaction)."""
    mock = MagicMock(name="ynab_client.raw_request")
    monkeypatch.setattr("mgdio.ynab.transactions.raw_request", mock)
    return mock


@pytest.fixture
def sample_message_payload() -> dict:
    """Realistic Gmail API ``users.messages.get?format=full`` response."""
    text_b64 = (
        base64.urlsafe_b64encode(b"hello plain world").decode("ascii").rstrip("=")
    )
    html_b64 = (
        base64.urlsafe_b64encode(b"<p>hello <b>html</b> world</p>")
        .decode("ascii")
        .rstrip("=")
    )
    return {
        "id": "msg-1",
        "threadId": "thread-1",
        "labelIds": ["INBOX", "UNREAD"],
        "snippet": "hello plain world",
        "internalDate": "1700000000000",
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": "Alice <alice@example.com>"},
                {"name": "To", "value": "Bob <bob@example.com>, c@example.com"},
                {"name": "Cc", "value": "d@example.com"},
                {"name": "Subject", "value": "Greetings"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": text_b64, "size": len("hello plain world")},
                },
                {
                    "mimeType": "text/html",
                    "body": {"data": html_b64, "size": 28},
                },
            ],
        },
    }
