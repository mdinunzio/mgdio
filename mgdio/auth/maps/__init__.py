"""Google Maps authentication: API key in the credential vault.

Google Maps Platform uses an API key, not OAuth. The key is pasted by
the user into a localhost setup page; this subpackage saves it to the
vault under ``mgdio/maps/api_key`` and exposes the standard provider triple
(:func:`get_api_key`, :func:`clear_stored_token`, :func:`reset_key_cache`).
"""

from __future__ import annotations

from mgdio.auth.maps.auth import (
    authorize,
    clear_stored_token,
    get_api_key,
    reset_key_cache,
)

__all__ = ["authorize", "clear_stored_token", "get_api_key", "reset_key_cache"]
