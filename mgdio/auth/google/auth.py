"""Google OAuth: keyring-backed token cache + setup-server flow on first use.

Token storage uses the OS-native credential vault via :mod:`keyring`:

* Windows: Credential Manager (DPAPI-protected, current-user scoped).
* macOS: Keychain.
* Linux: Secret Service (gnome-keyring, kwallet, ...).

A single OAuth client requests the union of every Google scope mgdio uses
(see :data:`mgdio.settings.GOOGLE_SCOPES`). One consent flow, one token,
shared by every Google service subpackage.
"""

from __future__ import annotations

import json
import logging

import keyring
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from mgdio.auth.google._headless_flow import run_headless_flow
from mgdio.auth.google._setup_server import run_setup_flow
from mgdio.settings import (
    GOOGLE_CLIENT_SECRET_PATH,
    GOOGLE_KEYRING_SERVICE,
    GOOGLE_KEYRING_USERNAME,
    GOOGLE_SCOPES,
)

logger = logging.getLogger(__name__)

_credentials: Credentials | None = None


def get_credentials(headless: bool = False) -> Credentials:
    """Return valid Google OAuth credentials, running setup flow on first use.

    The returned credentials are valid for every API listed in
    :data:`mgdio.settings.GOOGLE_SCOPES` (Gmail, Calendar, Sheets).
    Cached in-process for the lifetime of the program; persisted across
    runs in the OS keyring.

    Args:
        headless: If True, use the copy-paste OAuth flow
            (:func:`mgdio.auth.google._headless_flow.run_headless_flow`)
            instead of the browser-based localhost setup page. For
            machines without a GUI/browser, e.g. a Linux VPS.

    Returns:
        A valid ``google.oauth2.credentials.Credentials`` instance.
    """
    global _credentials
    if _credentials is not None and _credentials.valid:
        return _credentials

    creds = _load_token_from_keyring()
    if creds is not None and creds.expired and creds.refresh_token:
        logger.debug("Refreshing expired Google OAuth token")
        creds.refresh(Request())
        _save_token_to_keyring(creds)
    if creds is None or not creds.valid:
        flow_fn = run_headless_flow if headless else run_setup_flow
        creds = flow_fn(GOOGLE_CLIENT_SECRET_PATH, list(GOOGLE_SCOPES))
        _save_token_to_keyring(creds)

    _credentials = creds
    return creds


def clear_stored_token() -> None:
    """Delete the cached OAuth token from the OS keyring and in-process cache."""
    try:
        keyring.delete_password(GOOGLE_KEYRING_SERVICE, GOOGLE_KEYRING_USERNAME)
    except keyring.errors.PasswordDeleteError:
        pass
    reset_credentials_cache()


def reset_credentials_cache() -> None:
    """Clear the in-process credentials cache (does not touch the keyring)."""
    global _credentials
    _credentials = None


def _load_token_from_keyring() -> Credentials | None:
    raw = keyring.get_password(GOOGLE_KEYRING_SERVICE, GOOGLE_KEYRING_USERNAME)
    if not raw:
        return None
    # Note: if the stored token's recorded scopes are a strict subset of
    # GOOGLE_SCOPES (e.g. after a release that adds a new service),
    # google-auth still returns Credentials here; the next refresh will
    # surface the mismatch and we fall back to the setup flow.
    return Credentials.from_authorized_user_info(json.loads(raw), list(GOOGLE_SCOPES))


def _save_token_to_keyring(creds: Credentials) -> None:
    keyring.set_password(
        GOOGLE_KEYRING_SERVICE, GOOGLE_KEYRING_USERNAME, creds.to_json()
    )
