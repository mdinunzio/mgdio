"""YNAB transactions: list (with filters) + PATCH updates.

Update semantics
================

:func:`update_transaction` uses tri-state PATCH semantics for each optional
field, mirroring :func:`mgdio.calendar.update_event`:

* ``None`` (default)  -- field is omitted from the body (no-op).
* :data:`CLEAR` sentinel  -- field is sent as null (clears it on YNAB).
* Any value           -- field is set to that value.

The primary use case is editing a transaction's ``memo`` (note) without
disturbing other fields, but the same function handles ``cleared``,
``approved``, ``flag_color``, and ``category_id`` reassignments.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date as date_type
from typing import Any

from mgdio.ynab.client import raw_request, request

logger = logging.getLogger(__name__)


class _ClearType:
    """Sentinel: pass :data:`CLEAR` to ``update_transaction`` to null a field."""

    _instance: "_ClearType | None" = None

    def __new__(cls) -> "_ClearType":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "CLEAR"


CLEAR = _ClearType()


@dataclass(frozen=True, slots=True)
class Transaction:
    """A YNAB transaction.

    Amount fields are integer **milliunits** -- ``-$12.34`` is ``-12340``.

    Attributes:
        id: Transaction id.
        date: ISO date string (``YYYY-MM-DD``) of the transaction.
        amount_milliunits: Signed amount in milliunits (negative = outflow).
        memo: Free-text note (called "memo" in YNAB), or empty string.
        cleared: ``"cleared" | "uncleared" | "reconciled"``.
        approved: Whether the user has approved the auto-imported transaction.
        flag_color: Color flag, or empty string.
        account_id: Owning account id.
        account_name: Owning account name (for convenience).
        payee_id: Payee id, or empty string.
        payee_name: Payee name, or empty string.
        category_id: Category id, or empty string (split/uncategorized).
        category_name: Category name, or empty string.
        transfer_account_id: If a transfer, the other side's account id.
        deleted: True if soft-deleted.
    """

    id: str
    date: str
    amount_milliunits: int
    memo: str
    cleared: str
    approved: bool
    flag_color: str
    account_id: str
    account_name: str
    payee_id: str
    payee_name: str
    category_id: str
    category_name: str
    transfer_account_id: str
    deleted: bool

    @property
    def amount_dollars(self) -> float:
        """Signed amount as a float (milliunits / 1000)."""
        return self.amount_milliunits / 1000.0


def fetch_transactions(
    budget_id: str = "last-used",
    *,
    since_date: date_type | str | None = None,
    account_id: str | None = None,
    category_id: str | None = None,
    transaction_type: str | None = None,
) -> list[Transaction]:
    """List transactions on a budget, optionally filtered.

    YNAB exposes three endpoints under the hood:

    * Plain ``/budgets/{id}/transactions`` (default).
    * ``/budgets/{id}/accounts/{account_id}/transactions`` (when ``account_id``).
    * ``/budgets/{id}/categories/{category_id}/transactions`` (when
      ``category_id``).

    ``account_id`` and ``category_id`` are mutually exclusive.

    Args:
        budget_id: Budget id (or the ``"last-used"`` alias).
        since_date: Optional lower bound. Accepts a ``date`` or
            ``"YYYY-MM-DD"`` string.
        account_id: Scope to one account's transactions.
        category_id: Scope to one category's transactions.
        transaction_type: Optional YNAB-side filter -- ``"uncategorized"``
            or ``"unapproved"``.

    Returns:
        List of :class:`Transaction`, ordered by date descending (YNAB default).

    Raises:
        MgdioAPIError: On any YNAB API error.
        ValueError: If both ``account_id`` and ``category_id`` are supplied.
    """
    if account_id and category_id:
        raise ValueError(
            "Pass at most one of account_id / category_id (YNAB scopes the "
            "endpoint by one or the other)."
        )

    if account_id:
        path = f"/budgets/{budget_id}/accounts/{account_id}/transactions"
    elif category_id:
        path = f"/budgets/{budget_id}/categories/{category_id}/transactions"
    else:
        path = f"/budgets/{budget_id}/transactions"

    params: dict[str, Any] = {}
    if since_date is not None:
        params["since_date"] = (
            since_date.isoformat()
            if isinstance(since_date, date_type)
            else str(since_date)
        )
    if transaction_type is not None:
        params["type"] = transaction_type

    data = request("GET", path, params=params or None)
    return [_to_transaction(item) for item in data.get("transactions", [])]


def update_transaction(
    transaction_id: str,
    *,
    budget_id: str = "last-used",
    memo: str | _ClearType | None = None,
    cleared: str | None = None,
    approved: bool | None = None,
    flag_color: str | _ClearType | None = None,
    category_id: str | _ClearType | None = None,
    payee_name: str | _ClearType | None = None,
    date: date_type | str | None = None,
    amount_milliunits: int | None = None,
) -> Transaction:
    """PATCH a transaction. ``None`` = no-op, :data:`CLEAR` = null the field.

    The most common use is editing the ``memo``:

    >>> update_transaction("abc-123", memo="grocery run")
    >>> update_transaction("abc-123", memo=CLEAR)  # clear the memo

    Args:
        transaction_id: Transaction id.
        budget_id: Budget id (or ``"last-used"``).
        memo: New memo / note; ``CLEAR`` to clear; ``None`` to leave alone.
        cleared: One of ``"cleared" | "uncleared" | "reconciled"``.
        approved: Approve / unapprove flag.
        flag_color: One of ``"red"``, ``"orange"``, ``"yellow"``, ``"green"``,
            ``"blue"``, ``"purple"``; ``CLEAR`` to clear.
        category_id: Reassign category; ``CLEAR`` to uncategorize.
        payee_name: Rename the payee (YNAB will find/create by name).
        date: New transaction date (``date`` or ``"YYYY-MM-DD"``).
        amount_milliunits: New signed amount in milliunits.

    Returns:
        The updated :class:`Transaction`.

    Raises:
        MgdioAPIError: On any YNAB API error.
    """
    fields: dict[str, Any] = {}
    if memo is not None:
        fields["memo"] = None if memo is CLEAR else memo
    if cleared is not None:
        fields["cleared"] = cleared
    if approved is not None:
        fields["approved"] = bool(approved)
    if flag_color is not None:
        fields["flag_color"] = None if flag_color is CLEAR else flag_color
    if category_id is not None:
        fields["category_id"] = None if category_id is CLEAR else category_id
    if payee_name is not None:
        fields["payee_name"] = None if payee_name is CLEAR else payee_name
    if date is not None:
        fields["date"] = date.isoformat() if isinstance(date, date_type) else str(date)
    if amount_milliunits is not None:
        fields["amount"] = int(amount_milliunits)

    body = {"transaction": fields}
    resp = raw_request(
        "PATCH",
        f"/budgets/{budget_id}/transactions/{transaction_id}",
        json=body,
    )
    parsed = _json_or_raise_for_update(resp)
    return _to_transaction(parsed["data"]["transaction"])


def _json_or_raise_for_update(resp) -> dict[str, Any]:
    """Mirror ``client._json_or_raise`` semantics inline for the update path."""
    from mgdio.exceptions import MgdioAPIError

    if resp.status_code // 100 == 2:
        try:
            return resp.json()
        except ValueError as exc:
            raise MgdioAPIError(
                f"YNAB returned non-JSON 2xx body: {resp.text[:200]!r}"
            ) from exc
    detail = ""
    try:
        err = resp.json().get("error") or {}
        detail = err.get("detail") or err.get("name") or ""
    except ValueError:
        pass
    raise MgdioAPIError(f"YNAB HTTP {resp.status_code}: {detail or resp.text[:200]}")


def _to_transaction(raw: dict) -> Transaction:
    return Transaction(
        id=raw.get("id", ""),
        date=raw.get("date", ""),
        amount_milliunits=int(raw.get("amount", 0)),
        memo=raw.get("memo") or "",
        cleared=raw.get("cleared", ""),
        approved=bool(raw.get("approved", False)),
        flag_color=raw.get("flag_color") or "",
        account_id=raw.get("account_id", ""),
        account_name=raw.get("account_name") or "",
        payee_id=raw.get("payee_id") or "",
        payee_name=raw.get("payee_name") or "",
        category_id=raw.get("category_id") or "",
        category_name=raw.get("category_name") or "",
        transfer_account_id=raw.get("transfer_account_id") or "",
        deleted=bool(raw.get("deleted", False)),
    )
