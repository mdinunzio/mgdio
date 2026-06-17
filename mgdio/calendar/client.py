"""Cached googleapiclient Calendar Resource builder.

Credentials come from :func:`mgdio.auth.google.get_credentials` -- the same
token used by Gmail, Sheets, and Drive. Services are cached per resolved
profile slug.
"""

from __future__ import annotations

from googleapiclient.discovery import Resource, build

from mgdio.auth.google import get_credentials, resolve_profile

_services: dict[str, Resource] = {}


def get_service(profile: str | None = None) -> Resource:
    """Return the cached Calendar v3 ``Resource`` for a profile.

    The resource is cached per profile so subsequent reads/writes in the
    same process reuse the underlying HTTP client and discovery document.

    Args:
        profile: Explicit profile slug, or None to resolve via the
            waterfall (env var / sole profile).

    Returns:
        A ``googleapiclient.discovery.Resource`` for the Calendar v3 API.
    """
    slug = resolve_profile(profile)
    service = _services.get(slug)
    if service is None:
        service = build(
            "calendar",
            "v3",
            credentials=get_credentials(slug),
            cache_discovery=False,
        )
        _services[slug] = service
    return service


def reset_service_cache() -> None:
    """Clear all cached Calendar Resources (mainly for tests)."""
    _services.clear()
