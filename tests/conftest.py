"""Shared pytest fixtures for the mgdio test suite."""

from __future__ import annotations

import base64
import os
from unittest.mock import MagicMock

import mgdvault
import pytest
from mgdvault import MemoryVault

from mgdio import settings as mgdio_settings
from mgdio.auth.google import auth as google_auth
from mgdio.auth.maps import auth as maps_auth
from mgdio.auth.whoop import auth as whoop_auth
from mgdio.auth.ynab import auth as ynab_auth
from mgdio.calendar import client as calendar_client
from mgdio.drive import client as drive_client
from mgdio.gmail import client as gmail_client
from mgdio.maps import client as maps_client
from mgdio.sheets import client as sheets_client
from mgdio.whoop import client as whoop_client
from mgdio.ynab import client as ynab_client


@pytest.fixture(autouse=True)
def allow_interactive_auth(monkeypatch) -> None:
    """Pytest has no tty; don't let the non-interactive guard trip.

    Tests exercising the guard itself override MGDIO_NONINTERACTIVE
    with their own monkeypatch.setenv, which wins over this fixture.
    """
    monkeypatch.setenv("MGDIO_NONINTERACTIVE", "0")


@pytest.fixture(autouse=True)
def fake_vault(monkeypatch) -> MemoryVault:
    """Route every mgdvault call at an in-memory vault; never the real one.

    Autouse so no test can reach a developer's real KeePass file even if
    ``MGDVAULT_PASSWORD`` is exported in their shell: the ``MGDVAULT_*``
    variables are stripped, and mgdvault's own ``.env`` discovery is
    switched off (``MGDVAULT_DOTENV=0``) so the repo's ``.env`` cannot
    re-supply the password when a test resets the default vault.
    Request the fixture by name to seed or inspect secrets::

        fake_vault.set(YNAB_VAULT_KEY, "token")
        assert fake_vault.exists(MAPS_VAULT_KEY)
    """
    for name in list(os.environ):
        if name.startswith("MGDVAULT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MGDVAULT_DOTENV", "0")
    vault = MemoryVault()
    mgdvault.set_default_vault(vault)
    yield vault
    mgdvault.reset_default_vault()


@pytest.fixture(autouse=True)
def reset_caches() -> None:
    """Reset module-level credential and service caches between tests."""
    google_auth.reset_credentials_cache()
    ynab_auth.reset_token_cache()
    whoop_auth.reset_token_cache()
    maps_auth.reset_key_cache()
    gmail_client.reset_service_cache()
    sheets_client.reset_service_cache()
    calendar_client.reset_service_cache()
    drive_client.reset_service_cache()
    ynab_client.reset_session_cache()
    whoop_client.reset_session_cache()
    maps_client.reset_session_cache()
    yield
    google_auth.reset_credentials_cache()
    ynab_auth.reset_token_cache()
    whoop_auth.reset_token_cache()
    maps_auth.reset_key_cache()
    gmail_client.reset_service_cache()
    sheets_client.reset_service_cache()
    calendar_client.reset_service_cache()
    drive_client.reset_service_cache()
    ynab_client.reset_session_cache()
    whoop_client.reset_session_cache()
    maps_client.reset_session_cache()


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
    monkeypatch.setattr(
        mgdio_settings,
        "LEGACY_GOOGLE_PROFILE_INDEX_PATH",
        google_dir / "profiles.json",
    )
    return tmp_path


@pytest.fixture
def mock_gmail_service(monkeypatch) -> MagicMock:
    """Patch :func:`mgdio.gmail.client.get_service` to return a MagicMock."""
    service = MagicMock(name="GmailService")
    monkeypatch.setattr(gmail_client, "_services", {})
    monkeypatch.setattr(
        "mgdio.gmail.messages.get_service", lambda profile=None: service
    )
    monkeypatch.setattr("mgdio.gmail.sender.get_service", lambda profile=None: service)
    return service


@pytest.fixture
def mock_sheets_service(monkeypatch) -> MagicMock:
    """Patch :func:`mgdio.sheets.client.get_service` to return a MagicMock."""
    service = MagicMock(name="SheetsService")
    monkeypatch.setattr(sheets_client, "_services", {})
    monkeypatch.setattr("mgdio.sheets.values.get_service", lambda profile=None: service)
    monkeypatch.setattr(
        "mgdio.sheets.spreadsheets.get_service", lambda profile=None: service
    )
    return service


@pytest.fixture
def mock_calendar_service(monkeypatch) -> MagicMock:
    """Patch :func:`mgdio.calendar.client.get_service` to return a MagicMock."""
    service = MagicMock(name="CalendarService")
    monkeypatch.setattr(calendar_client, "_services", {})
    monkeypatch.setattr(
        "mgdio.calendar.events.get_service", lambda profile=None: service
    )
    monkeypatch.setattr(
        "mgdio.calendar.calendars.get_service", lambda profile=None: service
    )
    return service


@pytest.fixture
def mock_drive_service(monkeypatch) -> MagicMock:
    """Patch :func:`mgdio.drive.client.get_service` to return a MagicMock."""
    service = MagicMock(name="DriveService")
    monkeypatch.setattr(drive_client, "_services", {})
    monkeypatch.setattr("mgdio.drive.files.get_service", lambda profile=None: service)
    monkeypatch.setattr(
        "mgdio.drive.permissions.get_service", lambda profile=None: service
    )
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
def mock_whoop_paginate(monkeypatch) -> MagicMock:
    """Patch ``mgdio.whoop.client._paginate`` in every paginated resource module.

    Returns the ``MagicMock`` -- set ``return_value`` to a list of raw
    record dicts. Inspect ``call_args`` to assert path / params /
    max_records.
    """
    mock = MagicMock(name="whoop_client._paginate")
    monkeypatch.setattr("mgdio.whoop.recovery._paginate", mock)
    monkeypatch.setattr("mgdio.whoop.sleep._paginate", mock)
    monkeypatch.setattr("mgdio.whoop.workouts._paginate", mock)
    monkeypatch.setattr("mgdio.whoop.cycles._paginate", mock)
    return mock


@pytest.fixture
def mock_whoop_request(monkeypatch) -> MagicMock:
    """Patch ``mgdio.whoop.client.request`` for the single-object endpoints."""
    mock = MagicMock(name="whoop_client.request")
    monkeypatch.setattr("mgdio.whoop.user.request", mock)
    return mock


@pytest.fixture
def mock_maps_request(monkeypatch) -> MagicMock:
    """Patch ``mgdio.maps.client.request`` in the geocoding + directions modules.

    Returns the ``MagicMock`` -- set ``return_value`` to a parsed Maps
    response body (already status-OK; the real client would have raised
    otherwise). Inspect ``call_args`` to assert endpoint + params.
    """
    mock = MagicMock(name="maps_client.request")
    monkeypatch.setattr("mgdio.maps.geocoding.request", mock)
    monkeypatch.setattr("mgdio.maps.directions.request", mock)
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
