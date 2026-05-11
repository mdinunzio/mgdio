"""YNAB authentication: personal-access-token in the OS keyring.

YNAB uses long-lived personal access tokens, not OAuth. The token is
pasted by the user into a localhost setup page; this subpackage saves
it to the OS keyring under ``mgdio:ynab`` and exposes the standard
provider triple (:func:`get_token`, :func:`clear_stored_token`,
:func:`reset_token_cache`).
"""

from __future__ import annotations

from mgdio.auth.ynab.auth import (
    clear_stored_token,
    get_token,
    reset_token_cache,
)

__all__ = ["clear_stored_token", "get_token", "reset_token_cache"]
