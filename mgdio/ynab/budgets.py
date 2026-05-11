"""YNAB ``/budgets`` -- list every budget the token can see."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from mgdio.ynab.client import request

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Budget:
    """A YNAB budget summary (from ``/budgets``).

    Attributes:
        id: Budget id (use as ``budget_id`` in account/category/
            transaction functions; ``"last-used"`` is a valid alias).
        name: Display name.
        last_modified_on: Tz-aware datetime of the last server-side change.
        first_month: First budget month (``"YYYY-MM-01"`` per YNAB).
        last_month: Last budget month.
        currency_iso_code: e.g. ``"USD"``.
        currency_symbol: e.g. ``"$"``.
        decimal_digits: Currency precision (e.g. ``2`` for USD).
    """

    id: str
    name: str
    last_modified_on: datetime
    first_month: str
    last_month: str
    currency_iso_code: str
    currency_symbol: str
    decimal_digits: int


def fetch_budgets() -> list[Budget]:
    """List every budget the authenticated token can access.

    Returns:
        List of :class:`Budget`, possibly empty.

    Raises:
        MgdioAPIError: On any YNAB API error.
    """
    data = request("GET", "/budgets")
    return [_to_budget(item) for item in data.get("budgets", [])]


def _to_budget(raw: dict) -> Budget:
    fmt = raw.get("currency_format") or {}
    return Budget(
        id=raw.get("id", ""),
        name=raw.get("name", ""),
        last_modified_on=_parse_rfc3339(raw.get("last_modified_on", "")),
        first_month=raw.get("first_month", ""),
        last_month=raw.get("last_month", ""),
        currency_iso_code=fmt.get("iso_code", ""),
        currency_symbol=fmt.get("currency_symbol", ""),
        decimal_digits=int(fmt.get("decimal_digits", 2)),
    )


def _parse_rfc3339(value: str) -> datetime:
    if not value:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
