"""Thin Google Maps Platform REST client built on :mod:`requests`.

Google Maps web-service endpoints return HTTP 200 with a ``status``
field in the JSON body rather than HTTP error codes. :func:`request`
GETs an endpoint with the API key injected as a query param, then:

* returns the parsed body for ``OK`` and ``ZERO_RESULTS`` (both mean the
  request authenticated and ran -- ``ZERO_RESULTS`` is an empty result,
  not an error), and
* raises :class:`MgdioAPIError` for every other status (``REQUEST_DENIED``,
  ``OVER_QUERY_LIMIT``, ``INVALID_REQUEST``, ``NOT_FOUND``, ...).

The API key is never included in raised messages or logs.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from mgdio.auth.maps import get_api_key
from mgdio.exceptions import MgdioAPIError
from mgdio.settings import MAPS_API_BASE

logger = logging.getLogger(__name__)

# Statuses that mean "authenticated and executed"; the caller shapes the
# (possibly empty) body. Everything else is a hard error.
_OK_STATUSES = frozenset({"OK", "ZERO_RESULTS"})

_session: requests.Session | None = None


def get_session() -> requests.Session:
    """Return the cached :class:`requests.Session` for Maps calls."""
    global _session
    if _session is None:
        _session = requests.Session()
    return _session


def reset_session_cache() -> None:
    """Clear the cached session (mainly for tests)."""
    global _session
    if _session is not None:
        _session.close()
    _session = None


def request(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    """GET a Maps endpoint and return the parsed JSON body.

    Args:
        endpoint: Path under the API base, e.g. ``"geocode/json"`` or
            ``"directions/json"``.
        params: Query parameters (the API key is added automatically).

    Returns:
        The parsed response body. Its ``status`` is guaranteed to be
        ``"OK"`` or ``"ZERO_RESULTS"``.

    Raises:
        MgdioAPIError: On transport failure, a non-2xx HTTP response, or
            any Maps ``status`` other than OK / ZERO_RESULTS.
    """
    url = f"{MAPS_API_BASE}/{endpoint}"
    query = {**params, "key": get_api_key()}
    session = get_session()
    try:
        resp = session.get(url, params=query, timeout=30)
    except requests.RequestException as exc:
        raise MgdioAPIError(f"Maps {endpoint} transport failed: {exc}") from exc

    if resp.status_code // 100 != 2:
        raise MgdioAPIError(f"Maps {endpoint} HTTP {resp.status_code}")

    try:
        body = resp.json()
    except ValueError as exc:
        raise MgdioAPIError(
            f"Maps {endpoint} returned non-JSON body: {resp.text[:200]!r}"
        ) from exc

    status = body.get("status", "")
    if status in _OK_STATUSES:
        return body

    detail = body.get("error_message", "")
    raise MgdioAPIError(
        f"Maps {endpoint} status {status}" + (f": {detail}" if detail else "")
    )
