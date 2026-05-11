"""Shared pytest fixtures for the mgdio test suite."""

from __future__ import annotations

import pytest

from mgdio import settings as mgdio_settings
from mgdio.auth.google import auth as google_auth


@pytest.fixture(autouse=True)
def reset_caches() -> None:
    """Reset module-level credential caches between tests."""
    google_auth.reset_credentials_cache()
    yield
    google_auth.reset_credentials_cache()


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
    return store
