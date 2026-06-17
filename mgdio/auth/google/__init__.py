"""Google OAuth: shared identity for Gmail, Calendar, Sheets, and Drive.

A single OAuth client requests the union of all Google scopes mgdio uses
(see :data:`mgdio.settings.GOOGLE_SCOPES`) and the ``client_secret.json``
is shared. Each Google *account* is a named "profile": its refresh-token
bundle is stored in the OS keyring under ``mgdio:google:<slug>`` and
reused by every Google service subpackage. Which profile a given call
uses is resolved by :func:`resolve_profile` (explicit ``profile=`` ->
``MGDIO_GOOGLE_PROFILE`` env var -> the sole profile).
"""

from __future__ import annotations

from mgdio.auth.google._profiles import (
    detect_legacy_token,
    live_profiles,
    profile_has_token,
    read_index,
    resolve_profile,
    validate_slug,
)
from mgdio.auth.google.auth import (
    authorize_profile,
    clear_stored_token,
    get_credentials,
    reset_credentials_cache,
)

__all__ = [
    "authorize_profile",
    "clear_stored_token",
    "detect_legacy_token",
    "get_credentials",
    "live_profiles",
    "profile_has_token",
    "read_index",
    "reset_credentials_cache",
    "resolve_profile",
    "validate_slug",
]
