"""One-shot migration of pre-mgdvault secrets from the OS keyring.

mgdio <= 0.5 stored every secret in the OS credential manager via the
``keyring`` library. 0.6 moved to the shared mgdvault vault. This module
copies whatever is still in the keyring into the vault so existing
installs do not have to redo every consent flow. It only *reads* the
keyring; nothing is deleted, so it is safe to re-run.

``keyring`` is no longer a direct dependency of mgdio (mgdvault pulls it
in for its optional backend), so it is imported lazily and a missing
module is reported, not fatal.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import mgdvault

from mgdio import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MigrationResult:
    """Outcome of one keyring entry.

    Attributes:
        key: The vault key the secret maps to.
        action: ``"migrated"``, ``"skipped"`` (already in the vault), or
            ``"absent"`` (nothing in the keyring).
    """

    key: str
    action: str


def _legacy_google_slugs() -> list[str]:
    """Return slugs from the pre-mgdvault on-disk profile index."""
    try:
        raw = settings.LEGACY_GOOGLE_PROFILE_INDEX_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return []
    slugs = data.get("profiles", []) if isinstance(data, dict) else data
    if not isinstance(slugs, list):
        return []
    return sorted(
        s
        for s in slugs
        if isinstance(s, str) and settings.GOOGLE_PROFILE_SLUG_RE.match(s)
    )


def legacy_entries() -> list[tuple[str, str, str]]:
    """Return ``(service, username, vault_key)`` for every pre-mgdvault secret."""
    entries = [
        (
            settings.legacy_google_keyring_service(slug),
            settings.LEGACY_KEYRING_GOOGLE_USERNAME,
            settings.google_vault_key(slug),
        )
        for slug in _legacy_google_slugs()
    ]
    entries += [
        (*settings.LEGACY_KEYRING_YNAB, settings.YNAB_VAULT_KEY),
        (*settings.LEGACY_KEYRING_MAPS, settings.MAPS_VAULT_KEY),
        (*settings.LEGACY_KEYRING_WHOOP_APP, settings.WHOOP_VAULT_KEY_APP),
        (*settings.LEGACY_KEYRING_WHOOP_TOKEN, settings.WHOOP_VAULT_KEY_TOKEN),
    ]
    return entries


def migrate_from_keyring(
    *, overwrite: bool = False, keyring_module=None
) -> list[MigrationResult]:
    """Copy every known pre-mgdvault keyring secret into the vault.

    Args:
        overwrite: Replace vault entries that already exist. By default an
            existing vault entry wins (it is presumably newer).
        keyring_module: The ``keyring``-compatible module to read from;
            defaults to the real one. Exposed for tests.

    Returns:
        One :class:`MigrationResult` per known entry, in a stable order.

    Raises:
        ModuleNotFoundError: If ``keyring`` is not importable.
    """
    if keyring_module is None:
        import keyring as keyring_module  # noqa: F811 - lazy, optional

    results: list[MigrationResult] = []
    for service, username, key in legacy_entries():
        try:
            value = keyring_module.get_password(service, username)
        except Exception as exc:  # keyring backends raise all sorts
            logger.warning(
                "Could not read %s/%s from the keyring: %s", service, username, exc
            )
            value = None
        if not value:
            results.append(MigrationResult(key, "absent"))
            continue
        if mgdvault.exists(key) and not overwrite:
            results.append(MigrationResult(key, "skipped"))
            continue
        mgdvault.set(key, value)
        results.append(MigrationResult(key, "migrated"))
    return results
