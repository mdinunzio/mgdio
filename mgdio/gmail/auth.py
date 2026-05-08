"""Gmail OAuth: keyring-backed token cache + browser login on first use.

Token storage uses the OS-native credential vault via :mod:`keyring`:

* Windows: Credential Manager (DPAPI-protected, current-user scoped).
* macOS: Keychain.
* Linux: Secret Service (gnome-keyring, kwallet, ...).

The OAuth ``client_secret.json`` lives as a plain file in
``mgdio.settings.APP_DATA_DIR`` because the user has to drop it there
manually after downloading from Google Cloud Console; it is *application*
config rather than a per-session secret.
"""

from __future__ import annotations

import json
import logging

import keyring
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from mgdio.exceptions import MissingClientSecretError
from mgdio.gmail._setup_page import render_to_temp_and_open
from mgdio.settings import (
    GMAIL_CLIENT_SECRET_PATH,
    GMAIL_SCOPES,
    KEYRING_SERVICE_GMAIL,
    KEYRING_USERNAME_GMAIL,
)

logger = logging.getLogger(__name__)

_credentials: Credentials | None = None


def get_credentials() -> Credentials:
    """Return valid Gmail OAuth credentials, running the flow on first use.

    On first call the user is taken through the browser-based consent
    flow; the resulting refresh-token bundle is stored in the OS keyring
    and reused on subsequent calls. Expired access tokens are refreshed
    automatically.

    Returns:
        A valid ``google.oauth2.credentials.Credentials`` instance.

    Raises:
        MissingClientSecretError: If ``client_secret.json`` is missing
            from :data:`mgdio.settings.APP_DATA_DIR`. The browser will
            open with setup instructions before the exception is raised.
    """
    global _credentials
    if _credentials is not None and _credentials.valid:
        return _credentials

    creds = _load_token_from_keyring()
    if creds is not None and creds.expired and creds.refresh_token:
        logger.debug("Refreshing expired Gmail OAuth token")
        creds.refresh(Request())
        _save_token_to_keyring(creds)
    if creds is None or not creds.valid:
        creds = _run_oauth_flow()
        _save_token_to_keyring(creds)

    _credentials = creds
    return creds


def clear_stored_token() -> None:
    """Delete the cached OAuth token from the OS keyring and in-process cache."""
    try:
        keyring.delete_password(KEYRING_SERVICE_GMAIL, KEYRING_USERNAME_GMAIL)
    except keyring.errors.PasswordDeleteError:
        pass
    reset_credentials_cache()


def reset_credentials_cache() -> None:
    """Clear the in-process credentials cache (does not touch the keyring)."""
    global _credentials
    _credentials = None


def _load_token_from_keyring() -> Credentials | None:
    raw = keyring.get_password(KEYRING_SERVICE_GMAIL, KEYRING_USERNAME_GMAIL)
    if not raw:
        return None
    return Credentials.from_authorized_user_info(json.loads(raw), list(GMAIL_SCOPES))


def _save_token_to_keyring(creds: Credentials) -> None:
    keyring.set_password(KEYRING_SERVICE_GMAIL, KEYRING_USERNAME_GMAIL, creds.to_json())


def _run_oauth_flow() -> Credentials:
    if not GMAIL_CLIENT_SECRET_PATH.exists():
        render_to_temp_and_open(GMAIL_CLIENT_SECRET_PATH)
        raise MissingClientSecretError(
            f"client_secret.json not found. Drop it at "
            f"{GMAIL_CLIENT_SECRET_PATH} and retry. "
            f"(A browser window has opened with setup instructions.)"
        )
    flow = InstalledAppFlow.from_client_secrets_file(
        str(GMAIL_CLIENT_SECRET_PATH), scopes=list(GMAIL_SCOPES)
    )
    return flow.run_local_server(port=0, open_browser=True)
