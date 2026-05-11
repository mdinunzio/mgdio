"""Opt-in integration tests that hit the real YNAB API.

Skipped unless ``MGDIO_RUN_INTEGRATION=1``. Lists budgets, picks the
first one, and exercises read paths against it. Does NOT modify any
transactions (the modify path is unit-tested with mocks; uncomment the
final test block locally if you want to round-trip a memo edit).
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration

if os.getenv("MGDIO_RUN_INTEGRATION") != "1":
    pytest.skip(
        "MGDIO_RUN_INTEGRATION!=1; skipping real-API tests",
        allow_module_level=True,
    )


def test_fetch_budgets_returns_at_least_one():
    from mgdio.ynab import fetch_budgets

    budgets = fetch_budgets()
    assert isinstance(budgets, list)
    assert len(budgets) >= 1


def test_fetch_accounts_categories_transactions_on_first_budget():
    from mgdio.ynab import (
        fetch_accounts,
        fetch_budgets,
        fetch_categories,
        fetch_transactions,
    )

    budget = fetch_budgets()[0]

    accounts = fetch_accounts(budget.id)
    assert isinstance(accounts, list)

    groups = fetch_categories(budget.id)
    assert isinstance(groups, list)

    txns = fetch_transactions(budget.id)
    assert isinstance(txns, list)
