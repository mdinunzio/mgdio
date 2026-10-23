"""Unit tests for ``mgdio.auth._migrate`` (keyring -> vault, one-shot)."""

from __future__ import annotations

import json

from mgdio import settings
from mgdio.auth import _migrate


class _FakeKeyring:
    """Minimal ``keyring``-module stand-in backed by a dict."""

    def __init__(self, store: dict[tuple[str, str], str] | None = None):
        self.store = store or {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))


def _write_legacy_index(slugs: list[str]) -> None:
    settings.LEGACY_GOOGLE_PROFILE_INDEX_PATH.write_text(
        json.dumps({"version": 1, "profiles": slugs}), encoding="utf-8"
    )


class TestLegacyEntries:
    def test_google_profiles_come_from_old_index(self, tmp_appdata):
        _write_legacy_index(["work", "home", "Bad Slug"])

        entries = _migrate.legacy_entries()

        google = [e for e in entries if e[2].startswith("mgdio/google/")]
        assert google == [
            ("mgdio:google:home", "oauth_token", "mgdio/google/home"),
            ("mgdio:google:work", "oauth_token", "mgdio/google/work"),
        ]

    def test_single_secret_providers_always_listed(self, tmp_appdata):
        keys = {e[2] for e in _migrate.legacy_entries()}
        assert keys == {
            settings.YNAB_VAULT_KEY,
            settings.MAPS_VAULT_KEY,
            settings.WHOOP_VAULT_KEY_APP,
            settings.WHOOP_VAULT_KEY_TOKEN,
        }

    def test_missing_or_corrupt_index_is_empty(self, tmp_appdata):
        assert not any(
            e[2].startswith("mgdio/google/") for e in _migrate.legacy_entries()
        )
        settings.LEGACY_GOOGLE_PROFILE_INDEX_PATH.write_text("{nope", encoding="utf-8")
        assert not any(
            e[2].startswith("mgdio/google/") for e in _migrate.legacy_entries()
        )


class TestMigrateFromKeyring:
    def test_copies_present_entries_and_reports_absent(self, tmp_appdata, fake_vault):
        _write_legacy_index(["svc"])
        kr = _FakeKeyring(
            {
                ("mgdio:google:svc", "oauth_token"): '{"token": "g"}',
                ("mgdio:ynab", "personal_access_token"): "ynab-tok",
                ("mgdio:whoop", "app_credentials"): '{"client_id": "c"}',
            }
        )

        results = _migrate.migrate_from_keyring(keyring_module=kr)

        by_key = {r.key: r.action for r in results}
        assert by_key == {
            "mgdio/google/svc": "migrated",
            settings.YNAB_VAULT_KEY: "migrated",
            settings.MAPS_VAULT_KEY: "absent",
            settings.WHOOP_VAULT_KEY_APP: "migrated",
            settings.WHOOP_VAULT_KEY_TOKEN: "absent",
        }
        assert fake_vault.get("mgdio/google/svc") == '{"token": "g"}'
        assert fake_vault.get(settings.YNAB_VAULT_KEY) == "ynab-tok"
        assert fake_vault.get_json(settings.WHOOP_VAULT_KEY_APP) == {"client_id": "c"}

    def test_existing_vault_entry_wins_unless_overwrite(self, tmp_appdata, fake_vault):
        fake_vault.set(settings.YNAB_VAULT_KEY, "newer-in-vault")
        kr = _FakeKeyring({("mgdio:ynab", "personal_access_token"): "old-in-keyring"})

        results = _migrate.migrate_from_keyring(keyring_module=kr)
        assert {r.key: r.action for r in results}[settings.YNAB_VAULT_KEY] == "skipped"
        assert fake_vault.get(settings.YNAB_VAULT_KEY) == "newer-in-vault"

        _migrate.migrate_from_keyring(keyring_module=kr, overwrite=True)
        assert fake_vault.get(settings.YNAB_VAULT_KEY) == "old-in-keyring"

    def test_keyring_read_errors_are_treated_as_absent(self, tmp_appdata, fake_vault):
        class _Broken:
            def get_password(self, service, username):
                raise RuntimeError("no backend")

        results = _migrate.migrate_from_keyring(keyring_module=_Broken())

        assert all(r.action == "absent" for r in results)
        assert fake_vault.list_keys() == []

    def test_keyring_is_never_written(self, tmp_appdata, fake_vault):
        kr = _FakeKeyring({("mgdio:maps", "api_key"): "k"})
        _migrate.migrate_from_keyring(keyring_module=kr)
        # The fake exposes no set/delete at all; reaching here proves the
        # migration only called get_password.
        assert not hasattr(kr, "set_password")
