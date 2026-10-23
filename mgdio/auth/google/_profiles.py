"""Google account "profiles": per-account token bookkeeping + resolution.

mgdio can hold one OAuth token per Google account, each named by a slug
and stored in the credential vault at ``mgdio/google/<slug>``. The set
of known profiles is simply the set of keys under that prefix: the vault
is the single source of truth, so there is no separate index to drift.

There is no stored "default" profile. Which profile is the default for a
given environment is set purely via the ``MGDIO_GOOGLE_PROFILE`` env var
(e.g. in a project's ``.env``).
"""

from __future__ import annotations

import logging
import os

import mgdvault

from mgdio import settings
from mgdio.exceptions import MgdioAuthError

logger = logging.getLogger(__name__)


def validate_slug(slug: str) -> str:
    """Return ``slug`` if it is a valid profile slug, else raise.

    Args:
        slug: Candidate profile name.

    Returns:
        The same slug, unchanged.

    Raises:
        MgdioAuthError: If the slug is empty or contains characters other
            than lowercase letters, digits, hyphen, or underscore.
    """
    if not slug or not settings.GOOGLE_PROFILE_SLUG_RE.match(slug):
        raise MgdioAuthError(
            f"invalid profile slug {slug!r}; use lowercase letters, digits, "
            "'-' or '_' (e.g. 'mdinunziosvc')."
        )
    return slug


def profile_has_token(slug: str) -> bool:
    """Return True if a vault token exists for ``slug``."""
    return mgdvault.exists(settings.google_vault_key(slug))


def live_profiles() -> list[str]:
    """Return the sorted slugs that have a token in the vault."""
    prefix = settings.GOOGLE_VAULT_PREFIX + "/"
    slugs = []
    for key in mgdvault.list_keys(settings.GOOGLE_VAULT_PREFIX):
        tail = key[len(prefix) :] if key.startswith(prefix) else ""
        # Exactly one segment below the prefix, and a well-formed slug.
        if tail and "/" not in tail and settings.GOOGLE_PROFILE_SLUG_RE.match(tail):
            slugs.append(tail)
    return sorted(slugs)


def resolve_profile(explicit: str | None = None) -> str:
    """Resolve the active profile slug via the documented waterfall.

    Order (most specific wins):

    1. ``explicit`` (CLI ``--profile`` / Python ``profile=``): must be a
       valid slug with an existing token, else raise.
    2. ``MGDIO_GOOGLE_PROFILE`` env var: used if set; must name an
       existing token, else raise (no silent fall-through).
    3. The sole profile, if exactly one exists in the vault.
    4. Otherwise raise, listing what to do.

    Args:
        explicit: An explicitly requested slug, or None to fall through.

    Returns:
        The resolved profile slug.

    Raises:
        MgdioAuthError: If the requested/declared profile is missing, or
            no unambiguous profile can be selected.
    """
    if explicit is not None:
        validate_slug(explicit)
        if not profile_has_token(explicit):
            raise MgdioAuthError(
                f"profile {explicit!r} not found; run "
                f"`mgdio auth google --profile {explicit}`."
            )
        return explicit

    env_slug = os.environ.get(settings.GOOGLE_PROFILE_ENV_VAR)
    if env_slug:
        validate_slug(env_slug)
        if not profile_has_token(env_slug):
            raise MgdioAuthError(
                f"{settings.GOOGLE_PROFILE_ENV_VAR}={env_slug!r} names a profile "
                f"with no token; run `mgdio auth google --profile {env_slug}`."
            )
        return env_slug

    live = live_profiles()
    if len(live) == 1:
        return live[0]
    if not live:
        raise MgdioAuthError(
            "no Google profiles configured; run "
            "`mgdio auth google --profile <slug>`."
        )
    raise MgdioAuthError(
        f"multiple Google profiles ({', '.join(live)}); set "
        f"{settings.GOOGLE_PROFILE_ENV_VAR} or pass --profile / profile=."
    )
