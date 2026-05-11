"""YNAB ``/budgets/{id}/accounts`` -- list accounts + balances."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from mgdio.ynab.client import request

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Account:
    """A YNAB account.

    Money fields are integer **milliunits** -- ``$12.34`` is ``12340``.
    Use the ``..._dollars`` properties when you want a float.

    Attributes:
        id: Account id.
        name: Display name.
        type: e.g. ``"checking"``, ``"savings"``, ``"creditCard"``.
        on_budget: True for budget accounts, False for tracking accounts.
        closed: True if the account is closed in YNAB.
        balance_milliunits: Current balance in milliunits.
        cleared_balance_milliunits: Cleared balance in milliunits.
        uncleared_balance_milliunits: Uncleared balance in milliunits.
        deleted: True if the account was soft-deleted.
    """

    id: str
    name: str
    type: str
    on_budget: bool
    closed: bool
    balance_milliunits: int
    cleared_balance_milliunits: int
    uncleared_balance_milliunits: int
    deleted: bool

    @property
    def balance_dollars(self) -> float:
        """Current balance as a float (milliunits / 1000)."""
        return self.balance_milliunits / 1000.0

    @property
    def cleared_balance_dollars(self) -> float:
        """Cleared balance as a float (milliunits / 1000)."""
        return self.cleared_balance_milliunits / 1000.0

    @property
    def uncleared_balance_dollars(self) -> float:
        """Uncleared balance as a float (milliunits / 1000)."""
        return self.uncleared_balance_milliunits / 1000.0


def fetch_accounts(budget_id: str = "last-used") -> list[Account]:
    """List every account on a budget (including closed/deleted).

    Args:
        budget_id: Budget id (or the ``"last-used"`` alias).

    Returns:
        List of :class:`Account`.

    Raises:
        MgdioAPIError: On any YNAB API error.
    """
    data = request("GET", f"/budgets/{budget_id}/accounts")
    return [_to_account(item) for item in data.get("accounts", [])]


def _to_account(raw: dict) -> Account:
    return Account(
        id=raw.get("id", ""),
        name=raw.get("name", ""),
        type=raw.get("type", ""),
        on_budget=bool(raw.get("on_budget", False)),
        closed=bool(raw.get("closed", False)),
        balance_milliunits=int(raw.get("balance", 0)),
        cleared_balance_milliunits=int(raw.get("cleared_balance", 0)),
        uncleared_balance_milliunits=int(raw.get("uncleared_balance", 0)),
        deleted=bool(raw.get("deleted", False)),
    )
