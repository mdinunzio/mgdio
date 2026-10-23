"""Aggregate authentication status across every mgdio provider.

Reports which providers are set up on this machine by reading the
credential vault **without** triggering any setup flow or network call
-- every check is a plain vault lookup.
"""

from __future__ import annotations

from dataclasses import dataclass

import mgdvault
from mgdvault import VaultConfigurationError

from mgdio.auth.google import live_profiles
from mgdio.settings import MAPS_VAULT_KEY, WHOOP_VAULT_KEY_TOKEN, YNAB_VAULT_KEY


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    """Authentication status for one provider.

    Attributes:
        name: Provider name, e.g. ``"google"``.
        authenticated: True if usable credentials are stored.
        detail: Human-readable specifics (profile names, "not
            authenticated", ...).
        auth_command: The command to run to authenticate (or add another
            account, for Google).
    """

    name: str
    authenticated: bool
    detail: str
    auth_command: str


_AUTH_COMMANDS: dict[str, str] = {
    "google": "mgdio auth google --profile <slug>",
    "ynab": "mgdio auth ynab",
    "whoop": "mgdio auth whoop",
    "maps": "mgdio auth maps",
}


def describe_vault() -> str:
    """Return a secret-free description of the vault in use, never raising.

    For example ``"KeePass database at /path/vault.kdbx"``, or a
    ``"not configured: ..."`` message when the environment does not
    describe a usable vault (typically ``MGDVAULT_PASSWORD`` unset).
    """
    try:
        return mgdvault.default_vault().describe_location()
    except VaultConfigurationError as exc:
        return f"not configured: {exc}"


def _has_secret(key: str) -> bool:
    """Return True if a non-empty vault secret exists (never raises)."""
    try:
        return bool(mgdvault.get(key, default=None))
    except Exception:  # pragma: no cover - defensive against backend hiccups
        return False


def get_auth_status() -> list[ProviderStatus]:
    """Return the auth status for every provider, in display order.

    If the vault itself is unavailable (not configured, wrong password,
    ...), every provider is reported as unauthenticated with the vault
    error as its detail rather than raising.
    """
    try:
        mgdvault.default_vault()
    except VaultConfigurationError as exc:
        return [
            ProviderStatus(name, False, f"vault not configured: {exc}", cmd)
            for name, cmd in _AUTH_COMMANDS.items()
        ]

    statuses: list[ProviderStatus] = []

    # Google (multi-account: authenticated == at least one live profile).
    profiles = live_profiles()
    if profiles:
        detail = f"{len(profiles)} profile(s): {', '.join(profiles)}"
    else:
        detail = "no profiles"
    statuses.append(
        ProviderStatus(
            name="google",
            authenticated=bool(profiles),
            detail=detail,
            auth_command=_AUTH_COMMANDS["google"],
        )
    )

    # Single-secret providers.
    ynab_ok = _has_secret(YNAB_VAULT_KEY)
    statuses.append(
        ProviderStatus(
            name="ynab",
            authenticated=ynab_ok,
            detail="token stored" if ynab_ok else "not authenticated",
            auth_command=_AUTH_COMMANDS["ynab"],
        )
    )

    whoop_ok = _has_secret(WHOOP_VAULT_KEY_TOKEN)
    statuses.append(
        ProviderStatus(
            name="whoop",
            authenticated=whoop_ok,
            detail="token stored" if whoop_ok else "not authenticated",
            auth_command=_AUTH_COMMANDS["whoop"],
        )
    )

    maps_ok = _has_secret(MAPS_VAULT_KEY)
    statuses.append(
        ProviderStatus(
            name="maps",
            authenticated=maps_ok,
            detail="API key stored" if maps_ok else "not authenticated",
            auth_command=_AUTH_COMMANDS["maps"],
        )
    )

    return statuses
