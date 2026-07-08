"""Aggregate authentication status across every mgdio provider.

Reports which providers are set up on this machine by reading the OS
keyring (and the Google profile index) **without** triggering any setup
flow or network call -- every check is a plain keyring lookup.
"""

from __future__ import annotations

from dataclasses import dataclass

import keyring

from mgdio.auth.google import detect_legacy_token, live_profiles
from mgdio.settings import (
    MAPS_KEYRING_SERVICE,
    MAPS_KEYRING_USERNAME,
    WHOOP_KEYRING_SERVICE,
    WHOOP_KEYRING_USERNAME_TOKEN,
    YNAB_KEYRING_SERVICE,
    YNAB_KEYRING_USERNAME,
)


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    """Authentication status for one provider.

    Attributes:
        name: Provider name, e.g. ``"google"``.
        authenticated: True if usable credentials are stored.
        detail: Human-readable specifics (profile names, "not
            authenticated", legacy-token notice, ...).
        auth_command: The command to run to authenticate (or add another
            account, for Google).
    """

    name: str
    authenticated: bool
    detail: str
    auth_command: str


def _has_secret(service: str, username: str) -> bool:
    """Return True if a non-empty keyring secret exists (never raises)."""
    try:
        return bool(keyring.get_password(service, username))
    except Exception:  # pragma: no cover - defensive against backend hiccups
        return False


def get_auth_status() -> list[ProviderStatus]:
    """Return the auth status for every provider, in display order."""
    statuses: list[ProviderStatus] = []

    # Google (multi-account: authenticated == at least one live profile).
    profiles = live_profiles()
    if profiles:
        detail = f"{len(profiles)} profile(s): {', '.join(profiles)}"
    else:
        detail = "no profiles"
    if detect_legacy_token():
        detail += (
            "; legacy 'mgdio:google' token present "
            "(remove with `mgdio auth google remove --legacy`)"
        )
    statuses.append(
        ProviderStatus(
            name="google",
            authenticated=bool(profiles),
            detail=detail,
            auth_command="mgdio auth google --profile <slug>",
        )
    )

    # Single-secret providers.
    ynab_ok = _has_secret(YNAB_KEYRING_SERVICE, YNAB_KEYRING_USERNAME)
    statuses.append(
        ProviderStatus(
            name="ynab",
            authenticated=ynab_ok,
            detail="token stored" if ynab_ok else "not authenticated",
            auth_command="mgdio auth ynab",
        )
    )

    whoop_ok = _has_secret(WHOOP_KEYRING_SERVICE, WHOOP_KEYRING_USERNAME_TOKEN)
    statuses.append(
        ProviderStatus(
            name="whoop",
            authenticated=whoop_ok,
            detail="token stored" if whoop_ok else "not authenticated",
            auth_command="mgdio auth whoop",
        )
    )

    maps_ok = _has_secret(MAPS_KEYRING_SERVICE, MAPS_KEYRING_USERNAME)
    statuses.append(
        ProviderStatus(
            name="maps",
            authenticated=maps_ok,
            detail="API key stored" if maps_ok else "not authenticated",
            auth_command="mgdio auth maps",
        )
    )

    return statuses
