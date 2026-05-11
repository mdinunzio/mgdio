"""Unit tests for ``mgdio.ynab.budgets``."""

from __future__ import annotations

from mgdio.ynab import budgets as budgets_mod


def _sample_budget_raw():
    return {
        "id": "budget-1",
        "name": "Personal",
        "last_modified_on": "2026-05-08T10:00:00.000Z",
        "first_month": "2024-01-01",
        "last_month": "2026-12-01",
        "currency_format": {
            "iso_code": "USD",
            "currency_symbol": "$",
            "decimal_digits": 2,
        },
    }


class TestFetchBudgets:
    def test_returns_populated_dataclasses(self, mock_ynab_request):
        mock_ynab_request.return_value = {"budgets": [_sample_budget_raw()]}

        result = budgets_mod.fetch_budgets()

        assert len(result) == 1
        b = result[0]
        assert b.id == "budget-1"
        assert b.name == "Personal"
        assert b.currency_iso_code == "USD"
        assert b.currency_symbol == "$"
        assert b.decimal_digits == 2
        assert b.first_month == "2024-01-01"
        assert b.last_modified_on.year == 2026
        assert b.last_modified_on.tzinfo is not None
        mock_ynab_request.assert_called_once_with("GET", "/budgets")

    def test_empty_response_returns_empty_list(self, mock_ynab_request):
        mock_ynab_request.return_value = {"budgets": []}
        assert budgets_mod.fetch_budgets() == []

    def test_missing_currency_format_defaults_to_empty_strings(self, mock_ynab_request):
        raw = _sample_budget_raw()
        raw.pop("currency_format")
        mock_ynab_request.return_value = {"budgets": [raw]}

        result = budgets_mod.fetch_budgets()
        assert result[0].currency_iso_code == ""
        assert result[0].currency_symbol == ""
        assert result[0].decimal_digits == 2  # the default
