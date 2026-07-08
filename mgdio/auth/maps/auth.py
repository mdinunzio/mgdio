"""Google Maps API-key cache + setup-server flow on first use.

Google Maps Platform (Geocoding, Directions) authenticates with an API
key, not the shared Google OAuth token. Users create a key in the Cloud
Console and paste it into a localhost setup page; we store it in the OS
keyring under ``mgdio:maps`` and surface a :func:`get_api_key` that runs
the setup page on first call.
"""

from __future__ import annotations

import logging

import keyring

from mgdio.auth.maps._setup_server import run_headless_flow, run_setup_flow
from mgdio.settings import MAPS_KEYRING_SERVICE, MAPS_KEYRING_USERNAME

logger = logging.getLogger(__name__)

_api_key: str | None = None


def get_api_key(headless: bool = False) -> str:
    """Return the cached Google Maps API key.

    On first call (or after :func:`clear_stored_token`) the setup flow
    runs: the browser localhost page by default, or a terminal
    copy-paste prompt when ``headless=True``. Either way the pasted key
    is validated with a test geocode before being saved to the keyring.

    Args:
        headless: If True, prompt for the key on the terminal instead of
            opening a browser page. For machines without a browser (e.g.
            a Linux VPS). Only used if a fresh flow is needed.

    Returns:
        The Google Maps Platform API key string.
    """
    global _api_key
    if _api_key is not None:
        return _api_key

    stored = keyring.get_password(MAPS_KEYRING_SERVICE, MAPS_KEYRING_USERNAME)
    if stored:
        _api_key = stored
        return _api_key

    flow = run_headless_flow if headless else run_setup_flow
    _api_key = flow()
    keyring.set_password(MAPS_KEYRING_SERVICE, MAPS_KEYRING_USERNAME, _api_key)
    return _api_key


def clear_stored_token() -> None:
    """Delete the cached Maps API key from the OS keyring and cache."""
    try:
        keyring.delete_password(MAPS_KEYRING_SERVICE, MAPS_KEYRING_USERNAME)
    except keyring.errors.PasswordDeleteError:
        pass
    reset_key_cache()


def reset_key_cache() -> None:
    """Clear the in-process API-key cache (does not touch the keyring)."""
    global _api_key
    _api_key = None
