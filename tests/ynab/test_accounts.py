"""Unit tests for ``mgdio.ynab.accounts``."""

from __future__ import annotations

from mgdio.ynab import accounts as accounts_mod


def _sample_account_raw(**overrides):
    base = {
        "id": "acct-1",
        "name": "Checking",
        "type": "checking",
        "on_budget": True,
        "closed": False,
        "balance": 12340,
        "cleared_balance": 12000,
        "uncleared_balance": 340,
        "deleted": False,
    }
    base.update(overrides)
    return base


class TestFetchAccounts:
    def test_returns_dataclasses_with_milliunit_balances(self, mock_ynab_request):
        mock_ynab_request.return_value = {
            "accounts": [_sample_account_raw(), _sample_account_raw(name="Savings")]
        }

        result = accounts_mod.fetch_accounts("budget-1")

        assert [a.name for a in result] == ["Checking", "Savings"]
        assert result[0].balance_milliunits == 12340
        assert result[0].balance_dollars == 12.34
        assert result[0].cleared_balance_dollars == 12.00
        assert abs(result[0].uncleared_balance_dollars - 0.34) < 1e-9
        assert result[0].on_budget is True
        mock_ynab_request.assert_called_once_with("GET", "/budgets/budget-1/accounts")

    def test_passes_through_last_used_alias(self, mock_ynab_request):
        mock_ynab_request.return_value = {"accounts": []}
        accounts_mod.fetch_accounts()  # default budget_id="last-used"
        mock_ynab_request.assert_called_once_with("GET", "/budgets/last-used/accounts")

    def test_tracking_account_off_budget(self, mock_ynab_request):
        mock_ynab_request.return_value = {
            "accounts": [_sample_account_raw(on_budget=False, type="otherAsset")]
        }
        result = accounts_mod.fetch_accounts("b1")
        assert result[0].on_budget is False

    def test_empty_accounts_list(self, mock_ynab_request):
        mock_ynab_request.return_value = {"accounts": []}
        assert accounts_mod.fetch_accounts("b1") == []
