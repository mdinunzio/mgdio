"""Thin YNAB v1 REST client built on :mod:`requests`.

Module-singleton ``requests.Session`` with the Authorization header
pre-injected from :func:`mgdio.auth.ynab.get_token`. Service modules
call :func:`request` to get parsed JSON or :func:`raw_request` for a
:class:`requests.Response` (used by ``update_transaction`` when we want
the response body's ``data.transaction`` envelope).

Errors:
* Network failures wrap as :class:`MgdioAPIError`.
* Non-2xx responses parse YNAB's ``{"error": {"id": ..., "name": ...,
  "detail": ...}}`` envelope and raise :class:`MgdioAPIError` with the
  human-readable detail.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from mgdio.auth.ynab import get_token
from mgdio.exceptions import MgdioAPIError
from mgdio.settings import YNAB_API_BASE

logger = logging.getLogger(__name__)

_session: requests.Session | None = None


def get_session() -> requests.Session:
    """Return the cached :class:`requests.Session` for YNAB calls.

    The session has ``Authorization: Bearer <token>`` set from the
    keyring-cached personal access token.

    Returns:
        A configured :class:`requests.Session`.
    """
    global _session
    if _session is None:
        token = get_token()
        session = requests.Session()
        session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )
        _session = session
    return _session


def reset_session_cache() -> None:
    """Clear the cached session (mainly for tests + post-``clear_stored_token``)."""
    global _session
    if _session is not None:
        _session.close()
    _session = None


def request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make a YNAB API call and return the parsed ``data`` envelope.

    YNAB wraps every successful response as ``{"data": {...}}``; this
    helper unwraps it. Use :func:`raw_request` if you need the full
    response (status code, headers, etc.).

    Args:
        method: HTTP verb, e.g. ``"GET"``, ``"PATCH"``.
        path: Path beginning with ``/``, e.g. ``"/budgets"``. Joined to
            :data:`mgdio.settings.YNAB_API_BASE`.
        params: Optional query-string parameters.
        json: Optional JSON request body.

    Returns:
        The ``data`` sub-dict of the parsed response.

    Raises:
        MgdioAPIError: On any non-2xx response or transport failure.
    """
    resp = raw_request(method, path, params=params, json=json)
    body = _json_or_raise(resp)
    if "data" not in body:
        raise MgdioAPIError(
            f"YNAB {method} {path} returned no 'data' envelope: {body!r}"
        )
    return body["data"]


def raw_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> requests.Response:
    """Make a YNAB API call and return the raw :class:`requests.Response`.

    Args:
        method: HTTP verb.
        path: Path beginning with ``/``.
        params: Optional query-string parameters.
        json: Optional JSON request body.

    Returns:
        The full :class:`requests.Response`. Caller is responsible for
        error handling -- prefer :func:`request` when you just want
        ``data``.

    Raises:
        MgdioAPIError: On transport failure (DNS, connection reset, etc.).
    """
    url = f"{YNAB_API_BASE}{path}"
    session = get_session()
    try:
        return session.request(
            method=method, url=url, params=params, json=json, timeout=30
        )
    except requests.RequestException as exc:
        raise MgdioAPIError(f"YNAB {method} {path} transport failed: {exc}") from exc


def _json_or_raise(resp: requests.Response) -> dict[str, Any]:
    if resp.status_code // 100 == 2:
        try:
            return resp.json()
        except ValueError as exc:
            raise MgdioAPIError(
                f"YNAB returned non-JSON 2xx body: {resp.text[:200]!r}"
            ) from exc

    # Try to parse YNAB's error envelope; fall back to status+text.
    detail = ""
    try:
        err = resp.json().get("error") or {}
        detail = err.get("detail") or err.get("name") or ""
    except ValueError:
        pass
    raise MgdioAPIError(f"YNAB HTTP {resp.status_code}: {detail or resp.text[:200]}")
