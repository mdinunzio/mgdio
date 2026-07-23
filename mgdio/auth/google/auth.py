"""Google OAuth: per-profile keyring-backed token cache + setup flow.

Token storage uses the OS-native credential vault via :mod:`keyring`:

* Windows: Credential Manager (DPAPI-protected, current-user scoped).
* macOS: Keychain.
* Linux: Secret Service (gnome-keyring, kwallet, ...) or, on a headless
  host, an auto-selected file backend (see :mod:`mgdio.keyring_backend`).

One OAuth client requests the union of every Google scope mgdio uses
(see :data:`mgdio.settings.GOOGLE_SCOPES`); the ``client_secret.json`` is
shared. Each Google *account* is a named "profile" with its own token at
keyring service ``mgdio:google:<slug>``. A single consent flow per
profile, shared by every Google service subpackage. Which profile a call
uses is resolved by :func:`mgdio.auth.google._profiles.resolve_profile`.
"""

from __future__ import annotations

import json
import logging

import keyring
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from mgdio.auth import _keyring
from mgdio.auth._interactive import require_interactive
from mgdio.auth.google._headless_flow import run_headless_flow
from mgdio.auth.google._profiles import (
    add_to_index,
    remove_from_index,
    resolve_profile,
    validate_slug,
)
from mgdio.auth.google._setup_server import run_setup_flow
from mgdio.exceptions import MgdioAPIError
from mgdio.settings import (
    GOOGLE_CLIENT_SECRET_PATH,
    GOOGLE_KEYRING_USERNAME,
    GOOGLE_SCOPES,
    LEGACY_GOOGLE_KEYRING_SERVICE,
    google_keyring_service,
)

logger = logging.getLogger(__name__)

# In-process credential cache, keyed by resolved profile slug.
_credentials: dict[str, Credentials] = {}


def get_credentials(profile: str | None = None, headless: bool = False) -> Credentials:
    """Return valid Google OAuth credentials for a profile.

    The returned credentials are valid for every API listed in
    :data:`mgdio.settings.GOOGLE_SCOPES`. Cached in-process per profile;
    persisted across runs in the OS keyring under ``mgdio:google:<slug>``.

    Args:
        profile: Explicit profile slug, or None to resolve via the
            waterfall (env var / sole profile). The profile must already
            exist -- use :func:`authorize_profile` to create one.
        headless: If True, use the copy-paste OAuth flow instead of the
            browser-based localhost setup page (for hosts without a
            browser). Only used if a fresh flow is needed.

    Returns:
        A valid ``google.oauth2.credentials.Credentials`` instance.

    Raises:
        MgdioAuthError: If no profile can be resolved (see
            :func:`resolve_profile`).
    """
    slug = resolve_profile(profile)
    cached = _credentials.get(slug)
    if cached is not None and cached.valid:
        return cached

    creds = _load_token_from_keyring(slug)
    if creds is not None and creds.expired and creds.refresh_token:
        logger.debug("Refreshing expired Google OAuth token for %r", slug)
        try:
            creds.refresh(Request())
            _save_token_to_keyring(slug, creds)
        except RefreshError as exc:
            if _is_definitive_rejection(exc):
                logger.warning(
                    "Google rejected the refresh token for %r (%s); "
                    "re-authorization required",
                    slug,
                    exc,
                )
                creds = None
            else:
                raise MgdioAPIError(
                    f"Google token refresh failed for profile {slug!r} "
                    f"(transient -- the stored token is likely still "
                    f"valid): {exc}"
                ) from exc
    if creds is None or not creds.valid:
        require_interactive(
            "Google",
            f"mgdio auth google --profile {slug}",
            f"no usable stored token for profile {slug!r}",
        )
        _ensure_token_slot_writable(slug)
        creds = _run_flow(headless)
        _save_token_to_keyring(slug, creds)
        add_to_index(slug)

    _credentials[slug] = creds
    return creds


def authorize_profile(slug: str, headless: bool = False) -> Credentials:
    """Run the consent flow for a (new or existing) profile and persist it.

    Unlike :func:`get_credentials`, this does NOT require a pre-existing
    token -- it is the entry point for *creating* a profile via
    ``mgdio auth google --profile <slug>``.

    Args:
        slug: The profile slug to authorize.
        headless: If True, use the copy-paste OAuth flow.

    Returns:
        The freshly authorized credentials.

    Raises:
        MgdioAuthError: If the slug is invalid, or the keyring slot for
            it cannot be written (checked before the consent flow runs).
    """
    validate_slug(slug)
    _ensure_token_slot_writable(slug)
    creds = _run_flow(headless)
    _save_token_to_keyring(slug, creds)
    add_to_index(slug)
    _credentials[slug] = creds
    return creds


def clear_stored_token(profile: str) -> None:
    """Delete one profile's keyring token, index entry, and cached creds.

    Args:
        profile: The profile slug to remove.

    Raises:
        MgdioKeyringError: If the token exists but the keyring refuses
            to delete it (after stale-item recovery).
    """
    _keyring.delete_password(google_keyring_service(profile), GOOGLE_KEYRING_USERNAME)
    remove_from_index(profile)
    reset_credentials_cache(profile)


def clear_legacy_token() -> None:
    """Delete the pre-profiles token at the bare ``mgdio:google`` service.

    No-op if absent. The legacy token has no profile slug, so
    :func:`clear_stored_token` can't target it.
    """
    _keyring.delete_password(LEGACY_GOOGLE_KEYRING_SERVICE, GOOGLE_KEYRING_USERNAME)


def reset_credentials_cache(profile: str | None = None) -> None:
    """Clear cached credentials for one profile, or all when None."""
    if profile is None:
        _credentials.clear()
    else:
        _credentials.pop(profile, None)


def _run_flow(headless: bool) -> Credentials:
    """Run the browser or headless OAuth flow and return credentials."""
    flow_fn = run_headless_flow if headless else run_setup_flow
    return flow_fn(GOOGLE_CLIENT_SECRET_PATH, list(GOOGLE_SCOPES))


def _load_token_from_keyring(slug: str) -> Credentials | None:
    raw = keyring.get_password(google_keyring_service(slug), GOOGLE_KEYRING_USERNAME)
    if not raw:
        return None
    # Note: if the stored token's recorded scopes are a strict subset of
    # GOOGLE_SCOPES (e.g. after a release that adds a new service),
    # google-auth still returns Credentials here; the next refresh will
    # surface the mismatch and we fall back to the setup flow.
    return Credentials.from_authorized_user_info(json.loads(raw), list(GOOGLE_SCOPES))


def _save_token_to_keyring(slug: str, creds: Credentials) -> None:
    _keyring.set_password(
        google_keyring_service(slug), GOOGLE_KEYRING_USERNAME, creds.to_json()
    )


def _is_definitive_rejection(exc: RefreshError) -> bool:
    """True when Google's response means the refresh token is dead.

    ``invalid_grant`` covers expired and revoked tokens -- the cases
    where only a fresh consent flow helps. Anything else (server-side
    hiccups, quota) is treated as transient so the stored token isn't
    abandoned over a blip; google-auth marks retryable failures via
    ``exc.retryable`` where available.
    """
    if getattr(exc, "retryable", False):
        return False
    return "invalid_grant" in str(exc).lower()


def _ensure_token_slot_writable(slug: str) -> None:
    """Fail fast if the profile's keyring slot can't be overwritten.

    Runs before the interactive consent flow so a stale/broken vault
    entry surfaces immediately instead of after the user has authorized.
    """
    _keyring.ensure_writable(google_keyring_service(slug), GOOGLE_KEYRING_USERNAME)
