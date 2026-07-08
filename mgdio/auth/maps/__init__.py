"""Google Maps authentication: API key in the OS keyring.

Google Maps Platform uses an API key, not OAuth. The key is pasted by
the user into a localhost setup page; this subpackage saves it to the OS
keyring under ``mgdio:maps`` and exposes the standard provider triple
(:func:`get_api_key`, :func:`clear_stored_token`, :func:`reset_key_cache`).
"""

from __future__ import annotations

from mgdio.auth.maps.auth import (
    clear_stored_token,
    get_api_key,
    reset_key_cache,
)

__all__ = ["clear_stored_token", "get_api_key", "reset_key_cache"]
