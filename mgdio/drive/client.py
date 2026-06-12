"""Cached googleapiclient Drive Resource builder.

Credentials come from :func:`mgdio.auth.google.get_credentials` -- the same
token used by Gmail, Calendar, and Sheets.
"""

from __future__ import annotations

from googleapiclient.discovery import Resource, build

from mgdio.auth.google import get_credentials

_service: Resource | None = None


def get_service() -> Resource:
    """Return the cached Drive v3 ``Resource``, building it on first call.

    The resource is cached at module level so subsequent calls in the
    same process reuse the underlying HTTP client and discovery document.

    Returns:
        A ``googleapiclient.discovery.Resource`` for the Drive v3 API.
    """
    global _service
    if _service is None:
        _service = build(
            "drive",
            "v3",
            credentials=get_credentials(),
            cache_discovery=False,
        )
    return _service


def reset_service_cache() -> None:
    """Clear the cached Drive Resource (mainly for tests)."""
    global _service
    _service = None
