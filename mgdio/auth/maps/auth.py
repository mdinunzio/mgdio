"""Google Maps API-key cache + setup-server flow on first use.

Google Maps Platform (Geocoding, Directions) authenticates with an API
key, not the shared Google OAuth token. Users create a key in the Cloud
Console and paste it into a localhost setup page; we store it in the
credential vault under ``mgdio/maps/api_key`` and surface a
:func:`get_api_key` that runs the setup page on first call.
"""

from __future__ import annotations

import logging

import mgdvault

from mgdio.auth._interactive import require_interactive
from mgdio.auth.maps._setup_server import run_headless_flow, run_setup_flow
from mgdio.settings import MAPS_VAULT_KEY

logger = logging.getLogger(__name__)

_api_key: str | None = None


def authorize(headless: bool = False) -> str:
    """Ensure a usable API key for ``mgdio auth maps`` -- guard bypassed.

    Identical to :func:`get_api_key`, except the non-interactive guard
    (``MGDIO_NONINTERACTIVE=1`` / no tty) does not apply: an explicit
    auth command *is* the user's request for an interactive flow.

    Args:
        headless: If True, prompt for the key on the terminal.

    Returns:
        The Google Maps Platform API key string.
    """
    return get_api_key(headless=headless, _explicit=True)


def get_api_key(headless: bool = False, *, _explicit: bool = False) -> str:
    """Return the cached Google Maps API key.

    On first call (or after :func:`clear_stored_token`) the setup flow
    runs: the browser localhost page by default, or a terminal
    copy-paste prompt when ``headless=True``. Either way the pasted key
    is validated with a test geocode before being saved to the vault.

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

    stored = mgdvault.get(MAPS_VAULT_KEY, default=None)
    if stored:
        _api_key = stored
        return _api_key

    if not _explicit:
        require_interactive("Google Maps", "mgdio auth maps", "no stored API key")
    flow = run_headless_flow if headless else run_setup_flow
    _api_key = flow()
    mgdvault.set(MAPS_VAULT_KEY, _api_key)
    return _api_key


def clear_stored_token() -> None:
    """Delete the Maps API key from the vault and the in-process cache."""
    mgdvault.delete(MAPS_VAULT_KEY)
    reset_key_cache()


def reset_key_cache() -> None:
    """Clear the in-process API-key cache (does not touch the vault)."""
    global _api_key
    _api_key = None
