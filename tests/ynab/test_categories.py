"""Unit tests for ``mgdio.ynab.categories``."""

from __future__ import annotations

from mgdio.ynab import categories as categories_mod


def _category_raw(**overrides):
    base = {
        "id": "cat-1",
        "category_group_id": "grp-1",
        "name": "Groceries",
        "hidden": False,
        "budgeted": 50000,
        "activity": -32500,
        "balance": 17500,
        "note": "weekly target",
        "deleted": False,
    }
    base.update(overrides)
    return base


def _group_raw(**overrides):
    base = {
        "id": "grp-1",
        "name": "Everyday Spending",
        "hidden": False,
        "deleted": False,
        "categories": [_category_raw()],
    }
    base.update(overrides)
    return base


class TestFetchCategories:
    def test_returns_groups_with_nested_categories(self, mock_ynab_request):
        mock_ynab_request.return_value = {"category_groups": [_group_raw()]}

        result = categories_mod.fetch_categories("budget-1")

        assert len(result) == 1
        group = result[0]
        assert group.name == "Everyday Spending"
        assert len(group.categories) == 1
        cat = group.categories[0]
        assert cat.name == "Groceries"
        assert cat.budgeted_milliunits == 50000
        assert cat.budgeted_dollars == 50.00
        assert cat.activity_dollars == -32.50
        assert cat.balance_dollars == 17.50
        assert cat.note == "weekly target"
        mock_ynab_request.assert_called_once_with("GET", "/budgets/budget-1/categories")

    def test_default_budget_id_is_last_used(self, mock_ynab_request):
        mock_ynab_request.return_value = {"category_groups": []}
        categories_mod.fetch_categories()
        mock_ynab_request.assert_called_once_with(
            "GET", "/budgets/last-used/categories"
        )

    def test_empty_category_groups(self, mock_ynab_request):
        mock_ynab_request.return_value = {"category_groups": []}
        assert categories_mod.fetch_categories("b1") == []

    def test_null_note_becomes_empty_string(self, mock_ynab_request):
        cat = _category_raw(note=None)
        group = _group_raw(categories=[cat])
        mock_ynab_request.return_value = {"category_groups": [group]}
        result = categories_mod.fetch_categories("b1")
        assert result[0].categories[0].note == ""
