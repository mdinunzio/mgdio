"""Cached googleapiclient Gmail Resource builder.

Credentials come from :func:`mgdio.auth.google.get_credentials` -- the same
token used by Calendar and Sheets. No Gmail-specific auth here.
"""

from __future__ import annotations

from googleapiclient.discovery import Resource, build

from mgdio.auth.google import get_credentials

_service: Resource | None = None


def get_service() -> Resource:
    """Return the cached Gmail v1 ``Resource``, building it on first call.

    The resource is cached at module level so subsequent reads/sends in
    the same process reuse the underlying HTTP client and discovery
    document.

    Returns:
        A ``googleapiclient.discovery.Resource`` for the Gmail v1 API.
    """
    global _service
    if _service is None:
        _service = build(
            "gmail",
            "v1",
            credentials=get_credentials(),
            cache_discovery=False,
        )
    return _service


def reset_service_cache() -> None:
    """Clear the cached Gmail Resource (mainly for tests)."""
    global _service
    _service = None
