"""Whoop OAuth: vault-backed token bundle + automatic refresh.

Whoop uses a standard OAuth 2.0 authorization-code flow (confidential
client -- the app's ``client_secret`` is used in the token exchange).
First-time setup opens a localhost page where the user pastes their
Client ID + Secret (saved to the vault) and authorizes; the callback
exchanges the code for an access+refresh token bundle.

Two vault entries:

* ``mgdio/whoop/app_credentials`` -- ``{"client_id", "client_secret"}``
  JSON. Needed to refresh the access token, so it persists across
  ``--reset``.
* ``mgdio/whoop/oauth_token`` -- the token bundle JSON (access token,
  refresh token, ``expires_at`` epoch seconds, scope, token type).

Access tokens last one hour. :func:`get_access_token` transparently
refreshes an expired token using the stored refresh token + app creds,
falling back to the full setup flow only if refresh fails or there's no
token at all.

Whoop *rotates* refresh tokens: the old one is dead server-side the
moment a refresh succeeds. Refresh therefore runs inside
:func:`mgdvault.update`, which holds the vault's inter-process write
lock across the exchange and re-reads first -- so two processes (say,
two cron jobs) that both find the token expired can't each spend the
same refresh token and strand one another.
"""

from __future__ import annotations

import json
import logging
import time

import mgdvault
import requests

from mgdio.auth._interactive import require_interactive
from mgdio.auth.whoop._setup_server import run_headless_flow, run_setup_flow
from mgdio.exceptions import (
    MgdioAPIError,
    MgdioTokenRejectedError,
    MissingWhoopCredentialsError,
)
from mgdio.settings import WHOOP_TOKEN_URL, WHOOP_VAULT_KEY_APP, WHOOP_VAULT_KEY_TOKEN

logger = logging.getLogger(__name__)

# Refresh slightly early so a token that's about to expire mid-request
# doesn't slip through as "still valid".
_EXPIRY_SAFETY_MARGIN_SECONDS = 60

_token: dict | None = None


def authorize(headless: bool = False) -> str:
    """Ensure a usable token for ``mgdio auth whoop`` -- guard bypassed.

    Identical to :func:`get_access_token`, except it never raises
    :class:`MgdioInteractionRequiredError`: an explicit auth command *is*
    the user's request for an interactive flow, so the non-interactive
    guard (``MGDIO_NONINTERACTIVE=1`` / no tty) does not apply. In a
    context with no usable stdin the flow fails with a clean
    ``MgdioAuthError`` instead.

    Args:
        headless: If True, use the copy-paste OAuth flow.

    Returns:
        A currently-valid Whoop access token string.
    """
    return get_access_token(headless=headless, _explicit=True)


def get_access_token(headless: bool = False, *, _explicit: bool = False) -> str:
    """Return a valid Whoop access token, refreshing or onboarding as needed.

    Resolution order: in-process cache -> vault (refresh if expired) ->
    interactive setup flow. The result is cached in-process and persisted
    to the vault.

    Transient refresh failures (network errors, Whoop 5xx) propagate as
    :class:`MgdioAPIError` without touching the stored token -- retry
    later. Only a definitive rejection of the refresh token (HTTP
    400/401) or missing app credentials fall through to the setup flow.

    Args:
        headless: If True, use the copy-paste OAuth flow instead of the
            browser-based localhost setup page (for hosts without a
            browser). Only used if a fresh flow is needed.

    Returns:
        A currently-valid Whoop access token string.

    Raises:
        MgdioAPIError: On a transient refresh failure; the stored
            refresh token is likely still valid.
        MgdioInteractionRequiredError: If re-authorization is needed but
            this session can't run an interactive flow (no tty, or
            ``MGDIO_NONINTERACTIVE=1``).
    """
    global _token
    if _token is not None and not _is_expired(_token):
        return _token["access_token"]

    stored = _load_token()
    if stored is not None and _is_expired(stored) and stored.get("refresh_token"):
        logger.debug("Refreshing expired Whoop access token")
        try:
            stored = _refresh_and_store()
        except (MgdioTokenRejectedError, MissingWhoopCredentialsError) as exc:
            logger.warning(
                "Whoop re-authorization required (%s); falling back to the "
                "setup flow",
                exc,
            )
            stored = None

    if stored is None:
        if not _explicit:
            require_interactive("Whoop", "mgdio auth whoop", "no usable stored token")
        flow = run_headless_flow if headless else run_setup_flow
        stored = flow()
        _save_token(stored)

    _token = stored
    return _token["access_token"]


def clear_stored_token() -> None:
    """Delete the OAuth token (not the app creds) and reset the cache.

    Leaves ``mgdio/whoop/app_credentials`` in place so the next
    ``mgdio auth whoop`` can re-authorize without re-pasting the Client
    ID / Secret.
    """
    mgdvault.delete(WHOOP_VAULT_KEY_TOKEN)
    reset_token_cache()


def reset_token_cache() -> None:
    """Clear the in-process token cache (does not touch the vault)."""
    global _token
    _token = None


def _is_expired(token: dict) -> bool:
    return time.time() >= token.get("expires_at", 0)


def _refresh(token: dict) -> dict:
    """Exchange the stored refresh token for a fresh access token.

    Raises:
        MissingWhoopCredentialsError: If app credentials are absent
            (permanent: the setup flow re-collects them).
        MgdioTokenRejectedError: If Whoop definitively rejects the
            refresh token (HTTP 400/401 -- re-authorization needed).
        MgdioAPIError: On transient failures (transport errors, 5xx,
            malformed body) -- the stored token is likely still valid.
    """
    app = _load_app_credentials()
    if not app:
        raise MissingWhoopCredentialsError(
            "Whoop app credentials missing; re-run `mgdio auth whoop`."
        )
    try:
        resp = requests.post(
            WHOOP_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": token["refresh_token"],
                "client_id": app["client_id"],
                "client_secret": app["client_secret"],
                "scope": "offline",
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        raise MgdioAPIError(f"Whoop token refresh transport error: {exc}") from exc

    if resp.status_code in (400, 401):
        raise MgdioTokenRejectedError(
            f"Whoop rejected the refresh token (HTTP {resp.status_code}): "
            f"{resp.text[:200]}"
        )
    if resp.status_code != 200:
        raise MgdioAPIError(
            f"Whoop token refresh failed (HTTP {resp.status_code}): "
            f"{resp.text[:200]}"
        )
    try:
        payload = resp.json()
    except ValueError as exc:
        raise MgdioAPIError("Whoop refresh returned non-JSON body") from exc

    return _bundle_from_token_response(
        payload,
        # Whoop may omit a rotated refresh token; keep the existing one.
        fallback_refresh_token=token.get("refresh_token"),
    )


def _refresh_and_store() -> dict | None:
    """Refresh the stored bundle under the vault's write lock and persist it.

    The callback re-reads the bundle inside the lock: if another process
    already refreshed it, that fresh bundle is adopted without spending
    our (now-rotated, dead) refresh token. Returns None if the token was
    removed from the vault in the meantime.

    Raises:
        MgdioTokenRejectedError, MissingWhoopCredentialsError,
        MgdioAPIError: Propagated from :func:`_refresh`; the stored
            value is left untouched.
    """
    result: dict[str, dict] = {}

    def _do_refresh(current: str | None) -> str | None:
        if current is None:
            return None
        bundle = json.loads(current)
        if _is_expired(bundle) and bundle.get("refresh_token"):
            bundle = _refresh(bundle)
            result["bundle"] = bundle
            return json.dumps(bundle)
        result["bundle"] = bundle  # already refreshed by another process
        return current

    mgdvault.update(WHOOP_VAULT_KEY_TOKEN, _do_refresh)
    return result.get("bundle")


def _bundle_from_token_response(
    payload: dict,
    *,
    fallback_refresh_token: str | None = None,
) -> dict:
    """Normalize a Whoop token response into our stored bundle shape."""
    expires_in = int(payload.get("expires_in", 3600))
    return {
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token") or fallback_refresh_token,
        "expires_at": time.time() + expires_in - _EXPIRY_SAFETY_MARGIN_SECONDS,
        "scope": payload.get("scope", ""),
        "token_type": payload.get("token_type", "bearer"),
    }


def _load_token() -> dict | None:
    return mgdvault.get_json(WHOOP_VAULT_KEY_TOKEN, default=None)


def _save_token(token: dict) -> None:
    mgdvault.set_json(WHOOP_VAULT_KEY_TOKEN, token)


def _load_app_credentials() -> dict | None:
    return mgdvault.get_json(WHOOP_VAULT_KEY_APP, default=None)
