"""YNAB subpackage public API.

Built on top of :mod:`mgdio.auth.ynab` -- the auth subsystem provides
the personal access token; this subpackage just wraps the YNAB v1 REST
API with a thin :mod:`requests` client.

Money is stored as integer **milliunits** on the wire (``$12.34`` ->
``12340``). All dataclasses expose both the raw milliunit field and a
convenience ``..._dollars`` property.
"""

from __future__ import annotations

from mgdio.ynab.accounts import Account, fetch_accounts
from mgdio.ynab.budgets import Budget, fetch_budgets
from mgdio.ynab.categories import Category, CategoryGroup, fetch_categories
from mgdio.ynab.client import get_session, reset_session_cache
from mgdio.ynab.transactions import (
    CLEAR,
    Transaction,
    fetch_transactions,
    update_transaction,
)

__all__ = [
    "CLEAR",
    "Account",
    "Budget",
    "Category",
    "CategoryGroup",
    "Transaction",
    "fetch_accounts",
    "fetch_budgets",
    "fetch_categories",
    "fetch_transactions",
    "get_session",
    "reset_session_cache",
    "update_transaction",
]
