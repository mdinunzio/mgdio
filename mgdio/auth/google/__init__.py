"""Google OAuth: shared identity for Gmail, Calendar, and Sheets.

A single OAuth client requests the union of all Google scopes mgdio uses
(see :data:`mgdio.settings.GOOGLE_SCOPES`); the resulting refresh-token
bundle is stored in the OS keyring under ``mgdio:google`` and reused by
every Google service subpackage.
"""

from __future__ import annotations

from mgdio.auth.google.auth import (
    clear_stored_token,
    get_credentials,
    reset_credentials_cache,
)

__all__ = ["clear_stored_token", "get_credentials", "reset_credentials_cache"]
