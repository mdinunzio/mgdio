"""Unit tests for ``mgdio.auth.status``."""

from __future__ import annotations

import mgdvault

from mgdio.auth import status as auth_status
from mgdio.settings import (
    MAPS_VAULT_KEY,
    WHOOP_VAULT_KEY_APP,
    WHOOP_VAULT_KEY_TOKEN,
    YNAB_VAULT_KEY,
    google_vault_key,
)


def _by_name(rows):
    return {r.name: r for r in rows}


class TestGetAuthStatus:
    def test_all_unauthenticated(self, fake_vault):
        rows = _by_name(auth_status.get_auth_status())
        assert set(rows) == {"google", "ynab", "whoop", "maps"}
        assert all(not r.authenticated for r in rows.values())
        assert rows["google"].detail == "no profiles"
        assert rows["maps"].detail == "not authenticated"

    def test_reports_each_authenticated_provider(self, fake_vault):
        fake_vault.set(google_vault_key("svc"), "{}")
        fake_vault.set(YNAB_VAULT_KEY, "t")
        fake_vault.set(WHOOP_VAULT_KEY_TOKEN, "t")
        fake_vault.set(MAPS_VAULT_KEY, "k")

        rows = _by_name(auth_status.get_auth_status())

        assert rows["google"].authenticated is True
        assert "svc" in rows["google"].detail
        assert rows["ynab"].authenticated is True
        assert rows["whoop"].authenticated is True
        assert rows["maps"].authenticated is True

    def test_whoop_app_creds_without_token_is_unauthenticated(self, fake_vault):
        # App credentials pasted but authorization not completed -> no token.
        fake_vault.set(WHOOP_VAULT_KEY_APP, "id/secret")

        whoop = _by_name(auth_status.get_auth_status())["whoop"]
        assert whoop.authenticated is False

    def test_auth_command_present_for_missing(self, fake_vault):
        rows = _by_name(auth_status.get_auth_status())
        assert rows["maps"].auth_command == "mgdio auth maps"
        assert "mgdio auth google --profile" in rows["google"].auth_command

    def test_unconfigured_vault_reports_instead_of_raising(self):
        mgdvault.reset_default_vault()  # env is stripped -> no password

        rows = auth_status.get_auth_status()

        assert {r.name for r in rows} == {"google", "ynab", "whoop", "maps"}
        assert all(not r.authenticated for r in rows)
        assert all("vault not configured" in r.detail for r in rows)
        assert all("MGDVAULT_PASSWORD" in r.detail for r in rows)


class TestDescribeVault:
    def test_describes_active_vault(self, fake_vault):
        assert auth_status.describe_vault() == fake_vault.describe_location()

    def test_unconfigured_vault_is_described_not_raised(self):
        mgdvault.reset_default_vault()
        text = auth_status.describe_vault()
        assert text.startswith("not configured:")
        assert "MGDVAULT_PASSWORD" in text
