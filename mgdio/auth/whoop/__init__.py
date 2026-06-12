"""Whoop OAuth: keyring-backed token bundle with automatic refresh.

Whoop uses a standard OAuth 2.0 authorization-code flow. The user pastes
their app's Client ID + Secret into a localhost setup page and authorizes;
mgdio exchanges the resulting code for an access+refresh token bundle and
stores it in the OS keyring. Access tokens auto-refresh on expiry.
"""

from __future__ import annotations

from mgdio.auth.whoop.auth import (
    clear_stored_token,
    get_access_token,
    reset_token_cache,
)

__all__ = ["clear_stored_token", "get_access_token", "reset_token_cache"]
