"""YNAB token cache + setup-server flow on first use.

YNAB doesn't use OAuth -- users mint a long-lived personal access token
manually at https://app.ynab.com/settings/developer and paste it. We
store the token in the OS keyring under ``mgdio:ynab`` and surface a
provider-uniform :func:`get_token` that runs the localhost setup page
on first call.
"""

from __future__ import annotations

import logging

import keyring

from mgdio.auth.ynab._setup_server import run_setup_flow
from mgdio.settings import YNAB_KEYRING_SERVICE, YNAB_KEYRING_USERNAME

logger = logging.getLogger(__name__)

_token: str | None = None


def get_token() -> str:
    """Return the cached YNAB personal access token.

    On first call (or after :func:`clear_stored_token`) the localhost
    setup page opens in the browser; the pasted token is validated
    against ``/v1/user`` before being saved to the OS keyring.

    Returns:
        The personal access token string.
    """
    global _token
    if _token is not None:
        return _token

    stored = keyring.get_password(YNAB_KEYRING_SERVICE, YNAB_KEYRING_USERNAME)
    if stored:
        _token = stored
        return _token

    _token = run_setup_flow()
    keyring.set_password(YNAB_KEYRING_SERVICE, YNAB_KEYRING_USERNAME, _token)
    return _token


def clear_stored_token() -> None:
    """Delete the cached YNAB token from the OS keyring and in-process cache."""
    try:
        keyring.delete_password(YNAB_KEYRING_SERVICE, YNAB_KEYRING_USERNAME)
    except keyring.errors.PasswordDeleteError:
        pass
    reset_token_cache()


def reset_token_cache() -> None:
    """Clear the in-process token cache (does not touch the keyring)."""
    global _token
    _token = None
