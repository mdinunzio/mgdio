"""YNAB ``/budgets/{id}/categories`` -- category groups with monthly state."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from mgdio.ynab.client import request

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Category:
    """A single category within a group, with current-month state.

    Money fields are integer **milliunits**.

    Attributes:
        id: Category id.
        category_group_id: Owning group's id.
        name: Display name.
        hidden: True if hidden from the current month's view.
        budgeted_milliunits: Amount budgeted this month, in milliunits.
        activity_milliunits: Total spend this month, in milliunits
            (negative for expenses).
        balance_milliunits: Remaining budget this month, in milliunits.
        note: Free-text note attached in YNAB, or empty string.
        deleted: True if the category was soft-deleted.
    """

    id: str
    category_group_id: str
    name: str
    hidden: bool
    budgeted_milliunits: int
    activity_milliunits: int
    balance_milliunits: int
    note: str
    deleted: bool

    @property
    def budgeted_dollars(self) -> float:
        """Budgeted amount as a float (milliunits / 1000)."""
        return self.budgeted_milliunits / 1000.0

    @property
    def activity_dollars(self) -> float:
        """Activity (spend) amount as a float (milliunits / 1000)."""
        return self.activity_milliunits / 1000.0

    @property
    def balance_dollars(self) -> float:
        """Remaining balance as a float (milliunits / 1000)."""
        return self.balance_milliunits / 1000.0


@dataclass(frozen=True, slots=True)
class CategoryGroup:
    """A category group (e.g. "Monthly Bills") containing :class:`Category` rows.

    Attributes:
        id: Group id.
        name: Display name.
        hidden: True if the entire group is hidden.
        deleted: True if soft-deleted.
        categories: Tuple of :class:`Category` inside this group.
    """

    id: str
    name: str
    hidden: bool
    deleted: bool
    categories: tuple[Category, ...]


def fetch_categories(budget_id: str = "last-used") -> list[CategoryGroup]:
    """Return every category group on a budget with this month's state.

    Args:
        budget_id: Budget id (or the ``"last-used"`` alias).

    Returns:
        List of :class:`CategoryGroup`, in YNAB's display order.

    Raises:
        MgdioAPIError: On any YNAB API error.
    """
    data = request("GET", f"/budgets/{budget_id}/categories")
    return [_to_group(group) for group in data.get("category_groups", [])]


def _to_group(raw: dict) -> CategoryGroup:
    return CategoryGroup(
        id=raw.get("id", ""),
        name=raw.get("name", ""),
        hidden=bool(raw.get("hidden", False)),
        deleted=bool(raw.get("deleted", False)),
        categories=tuple(_to_category(c) for c in raw.get("categories", [])),
    )


def _to_category(raw: dict) -> Category:
    return Category(
        id=raw.get("id", ""),
        category_group_id=raw.get("category_group_id", ""),
        name=raw.get("name", ""),
        hidden=bool(raw.get("hidden", False)),
        budgeted_milliunits=int(raw.get("budgeted", 0)),
        activity_milliunits=int(raw.get("activity", 0)),
        balance_milliunits=int(raw.get("balance", 0)),
        note=raw.get("note") or "",
        deleted=bool(raw.get("deleted", False)),
    )
