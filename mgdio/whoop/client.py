"""Thin Whoop v2 REST client built on :mod:`requests`.

Each call fetches a fresh access token via
:func:`mgdio.auth.whoop.get_access_token` (which transparently refreshes
on expiry), so there's no long-lived ``Session`` with a baked-in
``Authorization`` header that could go stale.

Whoop collection endpoints paginate with ``limit`` (<=25) + ``nextToken``;
the response carries the cursor under ``next_token``. :func:`_paginate`
follows that cursor up to ``max_records``.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from mgdio.auth.whoop import get_access_token
from mgdio.exceptions import MgdioAPIError
from mgdio.settings import WHOOP_API_BASE

logger = logging.getLogger(__name__)

# Whoop caps page size at 25.
_MAX_PAGE_LIMIT = 25


def request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make a Whoop v2 API call and return the parsed JSON body.

    Args:
        method: HTTP verb, e.g. ``"GET"``.
        path: Path beginning with ``/``, joined to
            :data:`mgdio.settings.WHOOP_API_BASE` (e.g. ``"/v2/recovery"``).
        params: Optional query-string parameters.

    Returns:
        The parsed JSON response object.

    Raises:
        MgdioAPIError: On transport failure or any non-2xx response.
    """
    token = get_access_token()
    url = f"{WHOOP_API_BASE}{path}"
    try:
        resp = requests.request(
            method,
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise MgdioAPIError(f"Whoop {method} {path} transport failed: {exc}") from exc
    return _json_or_raise(resp, method, path)


def _paginate(
    path: str,
    *,
    params: dict[str, Any] | None = None,
    max_records: int = 100,
) -> list[dict[str, Any]]:
    """Follow ``next_token`` across pages, accumulating up to ``max_records``.

    Args:
        path: Collection endpoint path.
        params: Base query params (start/end, etc.); ``limit`` and
            ``nextToken`` are managed here.
        max_records: Hard cap on how many records to return.

    Returns:
        A list of raw record dicts (at most ``max_records``).
    """
    base = dict(params or {})
    out: list[dict[str, Any]] = []
    next_token: str | None = None

    while len(out) < max_records:
        page_params = dict(base)
        page_params["limit"] = min(_MAX_PAGE_LIMIT, max_records - len(out))
        if next_token:
            page_params["nextToken"] = next_token
        data = request("GET", path, params=page_params)
        out.extend(data.get("records", []))
        next_token = data.get("next_token")
        if not next_token:
            break

    return out[:max_records]


def reset_session_cache() -> None:
    """No-op kept for test symmetry with other service clients.

    The Whoop client holds no module-level session state (the token is
    fetched per-call), so there's nothing to clear here.
    """


def _json_or_raise(resp: requests.Response, method: str, path: str) -> dict[str, Any]:
    if resp.status_code // 100 == 2:
        try:
            return resp.json()
        except ValueError as exc:
            raise MgdioAPIError(
                f"Whoop {method} {path} returned non-JSON 2xx body: "
                f"{resp.text[:200]!r}"
            ) from exc
    raise MgdioAPIError(
        f"Whoop {method} {path} failed (HTTP {resp.status_code}): " f"{resp.text[:200]}"
    )
