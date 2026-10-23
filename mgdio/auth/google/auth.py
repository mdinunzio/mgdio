"""Google OAuth: per-profile vault-backed token cache + setup flow.

Tokens are stored in the shared `mgdvault
<https://github.com/mdinunzio/mgdvault>`_ credential vault (an encrypted
KeePass file by default, unlocked by ``MGDVAULT_PASSWORD``; see the
README). One OAuth client requests the union of every Google scope mgdio
uses (see :data:`mgdio.settings.GOOGLE_SCOPES`); the ``client_secret.json``
is shared. Each Google *account* is a named "profile" with its own token
at vault key ``mgdio/google/<slug>``. A single consent flow per profile,
shared by every Google service subpackage. Which profile a call uses is
resolved by :func:`mgdio.auth.google._profiles.resolve_profile`.

Token refresh is written back through :func:`mgdvault.update`, which
holds the vault's inter-process write lock across the refresh, so
several processes sharing one profile cannot clobber each other.
"""

from __future__ import annotations

import json
import logging

import mgdvault
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from mgdio.auth._interactive import require_interactive
from mgdio.auth.google._headless_flow import run_headless_flow
from mgdio.auth.google._profiles import resolve_profile, validate_slug
from mgdio.auth.google._setup_server import run_setup_flow
from mgdio.exceptions import MgdioAPIError
from mgdio.settings import GOOGLE_CLIENT_SECRET_PATH, GOOGLE_SCOPES, google_vault_key

logger = logging.getLogger(__name__)

# In-process credential cache, keyed by resolved profile slug.
_credentials: dict[str, Credentials] = {}


def get_credentials(profile: str | None = None, headless: bool = False) -> Credentials:
    """Return valid Google OAuth credentials for a profile.

    The returned credentials are valid for every API listed in
    :data:`mgdio.settings.GOOGLE_SCOPES`. Cached in-process per profile;
    persisted across runs in the vault under ``mgdio/google/<slug>``.

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
        MgdioAPIError: On a transient refresh failure; the stored token
            is likely still valid.
    """
    slug = resolve_profile(profile)
    cached = _credentials.get(slug)
    if cached is not None and cached.valid:
        return cached

    creds = _load_token(slug)
    if creds is not None and creds.expired and creds.refresh_token:
        logger.debug("Refreshing expired Google OAuth token for %r", slug)
        try:
            creds = _refresh_and_store(slug)
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
        creds = _run_flow(headless)
        _save_token(slug, creds)

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
        MgdioAuthError: If the slug is invalid.
    """
    validate_slug(slug)
    creds = _run_flow(headless)
    _save_token(slug, creds)
    _credentials[slug] = creds
    return creds


def clear_stored_token(profile: str) -> None:
    """Delete one profile's vault token and cached creds (no-op if absent).

    Args:
        profile: The profile slug to remove.
    """
    mgdvault.delete(google_vault_key(profile))
    reset_credentials_cache(profile)


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


def _creds_from_json(raw: str) -> Credentials:
    # Note: if the stored token's recorded scopes are a strict subset of
    # GOOGLE_SCOPES (e.g. after a release that adds a new service),
    # google-auth still returns Credentials here; the next refresh will
    # surface the mismatch and we fall back to the setup flow.
    return Credentials.from_authorized_user_info(json.loads(raw), list(GOOGLE_SCOPES))


def _load_token(slug: str) -> Credentials | None:
    raw = mgdvault.get(google_vault_key(slug), default=None)
    if not raw:
        return None
    return _creds_from_json(raw)


def _save_token(slug: str, creds: Credentials) -> None:
    mgdvault.set(google_vault_key(slug), creds.to_json())


def _refresh_and_store(slug: str) -> Credentials | None:
    """Refresh the stored token under the vault's write lock and persist it.

    The callback re-reads the stored value inside the lock, so if another
    process refreshed the same profile a moment ago we simply adopt its
    token instead of refreshing again. Returns None if the token was
    removed from the vault in the meantime.

    Raises:
        RefreshError: Propagated from google-auth when Google rejects or
            fails the refresh; the stored value is left untouched.
    """
    result: dict[str, Credentials] = {}

    def _refresh(current: str | None) -> str | None:
        if current is None:
            return None
        creds = _creds_from_json(current)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            result["creds"] = creds
            return creds.to_json()
        result["creds"] = creds  # already refreshed by another process
        return current

    mgdvault.update(google_vault_key(slug), _refresh)
    return result.get("creds")


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
