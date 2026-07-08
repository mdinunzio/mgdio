"""Unit tests for ``mgdio.auth.status``."""

from __future__ import annotations

from mgdio.auth import status as auth_status
from mgdio.auth.google import _profiles as google_profiles
from mgdio.settings import (
    GOOGLE_KEYRING_USERNAME,
    LEGACY_GOOGLE_KEYRING_SERVICE,
    MAPS_KEYRING_SERVICE,
    MAPS_KEYRING_USERNAME,
    WHOOP_KEYRING_SERVICE,
    WHOOP_KEYRING_USERNAME_TOKEN,
    YNAB_KEYRING_SERVICE,
    YNAB_KEYRING_USERNAME,
    google_keyring_service,
)


def _by_name(rows):
    return {r.name: r for r in rows}


class TestGetAuthStatus:
    def test_all_unauthenticated(self, tmp_appdata, fake_keyring):
        rows = _by_name(auth_status.get_auth_status())
        assert set(rows) == {"google", "ynab", "whoop", "maps"}
        assert all(not r.authenticated for r in rows.values())
        assert rows["google"].detail == "no profiles"
        assert rows["maps"].detail == "not authenticated"

    def test_reports_each_authenticated_provider(self, tmp_appdata, fake_keyring):
        # Google: one live profile.
        fake_keyring[(google_keyring_service("svc"), GOOGLE_KEYRING_USERNAME)] = "{}"
        google_profiles.add_to_index("svc")
        # Single-secret providers.
        fake_keyring[(YNAB_KEYRING_SERVICE, YNAB_KEYRING_USERNAME)] = "t"
        fake_keyring[(WHOOP_KEYRING_SERVICE, WHOOP_KEYRING_USERNAME_TOKEN)] = "t"
        fake_keyring[(MAPS_KEYRING_SERVICE, MAPS_KEYRING_USERNAME)] = "k"

        rows = _by_name(auth_status.get_auth_status())

        assert rows["google"].authenticated is True
        assert "svc" in rows["google"].detail
        assert rows["ynab"].authenticated is True
        assert rows["whoop"].authenticated is True
        assert rows["maps"].authenticated is True

    def test_google_legacy_token_noted(self, tmp_appdata, fake_keyring):
        fake_keyring[(LEGACY_GOOGLE_KEYRING_SERVICE, GOOGLE_KEYRING_USERNAME)] = "old"

        google = _by_name(auth_status.get_auth_status())["google"]

        # Legacy token alone doesn't count as an authenticated profile...
        assert google.authenticated is False
        # ...but it is surfaced with the cleanup hint.
        assert "legacy" in google.detail.lower()
        assert "remove --legacy" in google.detail

    def test_whoop_app_creds_without_token_is_unauthenticated(
        self, tmp_appdata, fake_keyring
    ):
        # App credentials pasted but authorization not completed -> no token.
        fake_keyring[(WHOOP_KEYRING_SERVICE, "app_credentials")] = "id/secret"

        whoop = _by_name(auth_status.get_auth_status())["whoop"]
        assert whoop.authenticated is False

    def test_auth_command_present_for_missing(self, tmp_appdata, fake_keyring):
        rows = _by_name(auth_status.get_auth_status())
        assert rows["maps"].auth_command == "mgdio auth maps"
        assert "mgdio auth google --profile" in rows["google"].auth_command
