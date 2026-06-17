"""Google account "profiles": per-account token bookkeeping + resolution.

mgdio can hold one OAuth token per Google account, each named by a slug
and stored at keyring service ``mgdio:google:<slug>``. Because the
``keyring`` library has no portable way to *list* stored entries (Secret
Service, Windows Credential Manager, and the ``keyrings.alt`` plaintext
fallback all differ), the set of known profiles is tracked in an on-disk
index file (:data:`mgdio.settings.GOOGLE_PROFILE_INDEX_PATH`). The index
lists which slugs *should* exist; the keyring remains the source of truth
for the token bytes, so :func:`resolve_profile` only ever auto-selects a
slug that actually has a token (defending against a stale index).

There is no stored "default" profile. Which profile is the default for a
given environment is set purely via the ``MGDIO_GOOGLE_PROFILE`` env var
(e.g. in a project's ``.env``).
"""

from __future__ import annotations

import json
import logging
import os
import tempfile

import keyring

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


def read_index() -> list[str]:
    """Return the sorted list of known profile slugs from the index file.

    Returns an empty list if the index is absent, empty, or corrupt -- a
    missing/garbled index simply means "no known profiles", never a crash.
    """
    path = settings.GOOGLE_PROFILE_INDEX_PATH
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Profile index %s is corrupt; treating as empty.", path)
        return []
    # Accept both the object shape {"version":1,"profiles":[...]} and a
    # bare list (tolerant of hand edits / future shapes).
    if isinstance(data, dict):
        slugs = data.get("profiles", [])
    elif isinstance(data, list):
        slugs = data
    else:
        return []
    return sorted({s for s in slugs if isinstance(s, str)})


def _write_index(slugs: list[str]) -> None:
    """Atomically write the sorted, de-duplicated slug list to the index."""
    path = settings.GOOGLE_PROFILE_INDEX_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "profiles": sorted(set(slugs))}
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        os.replace(tmp_name, path)
    except OSError:
        try:
            os.unlink(tmp_name)
        except OSError:  # pragma: no cover - best effort cleanup
            pass
        raise
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover - best effort
        pass


def add_to_index(slug: str) -> None:
    """Add ``slug`` to the profile index (idempotent)."""
    slugs = read_index()
    if slug not in slugs:
        slugs.append(slug)
        _write_index(slugs)


def remove_from_index(slug: str) -> None:
    """Remove ``slug`` from the profile index (idempotent)."""
    slugs = read_index()
    if slug in slugs:
        slugs.remove(slug)
        _write_index(slugs)


def profile_has_token(slug: str) -> bool:
    """Return True if a keyring token exists for ``slug``."""
    try:
        raw = keyring.get_password(
            settings.google_keyring_service(slug), settings.GOOGLE_KEYRING_USERNAME
        )
    except Exception:  # pragma: no cover - backend hiccup -> treat as absent
        return False
    return bool(raw)


def live_profiles() -> list[str]:
    """Return indexed slugs that actually have a token (the live set)."""
    return [s for s in read_index() if profile_has_token(s)]


def detect_legacy_token() -> bool:
    """Return True if a pre-profiles token exists at ``mgdio:google``."""
    try:
        raw = keyring.get_password(
            settings.LEGACY_GOOGLE_KEYRING_SERVICE, settings.GOOGLE_KEYRING_USERNAME
        )
    except Exception:  # pragma: no cover
        return False
    return bool(raw)


def resolve_profile(explicit: str | None = None) -> str:
    """Resolve the active profile slug via the documented waterfall.

    Order (most specific wins):

    1. ``explicit`` (CLI ``--profile`` / Python ``profile=``): must be a
       valid slug with an existing token, else raise.
    2. ``MGDIO_GOOGLE_PROFILE`` env var: used if set; must name an
       existing token, else raise (no silent fall-through).
    3. The sole profile, if exactly one exists in the keyring.
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
