"""Unit tests for ``mgdio.ynab.transactions``."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from mgdio.exceptions import MgdioAPIError
from mgdio.ynab import transactions as tx_mod
from mgdio.ynab.transactions import CLEAR


def _tx_raw(**overrides):
    base = {
        "id": "tx-1",
        "date": "2026-05-08",
        "amount": -12340,
        "memo": "lunch",
        "cleared": "uncleared",
        "approved": True,
        "flag_color": "red",
        "account_id": "acct-1",
        "account_name": "Checking",
        "payee_id": "payee-1",
        "payee_name": "Bistro",
        "category_id": "cat-1",
        "category_name": "Restaurants",
        "transfer_account_id": None,
        "deleted": False,
    }
    base.update(overrides)
    return base


def _mock_patch_response(transaction_raw):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"data": {"transaction": transaction_raw}}
    return resp


class TestFetchTransactions:
    def test_default_path(self, mock_ynab_request):
        mock_ynab_request.return_value = {"transactions": [_tx_raw()]}

        result = tx_mod.fetch_transactions("budget-1")

        assert len(result) == 1
        assert result[0].id == "tx-1"
        assert result[0].amount_dollars == -12.34
        assert result[0].memo == "lunch"
        args, kwargs = (
            mock_ynab_request.call_args.args,
            mock_ynab_request.call_args.kwargs,
        )
        assert args == ("GET", "/budgets/budget-1/transactions")
        # Default: no params at all when no filters are set.
        assert kwargs.get("params") is None

    def test_account_scoped_endpoint(self, mock_ynab_request):
        mock_ynab_request.return_value = {"transactions": []}
        tx_mod.fetch_transactions("b1", account_id="acct-1")
        assert (
            mock_ynab_request.call_args.args[1]
            == "/budgets/b1/accounts/acct-1/transactions"
        )

    def test_category_scoped_endpoint(self, mock_ynab_request):
        mock_ynab_request.return_value = {"transactions": []}
        tx_mod.fetch_transactions("b1", category_id="cat-1")
        assert (
            mock_ynab_request.call_args.args[1]
            == "/budgets/b1/categories/cat-1/transactions"
        )

    def test_account_and_category_together_rejected(self, mock_ynab_request):
        with pytest.raises(ValueError, match="mutually exclusive|at most one"):
            tx_mod.fetch_transactions("b1", account_id="a", category_id="c")

    def test_since_date_accepts_date_object(self, mock_ynab_request):
        mock_ynab_request.return_value = {"transactions": []}
        tx_mod.fetch_transactions("b1", since_date=date(2026, 4, 1))
        params = mock_ynab_request.call_args.kwargs["params"]
        assert params == {"since_date": "2026-04-01"}

    def test_since_date_accepts_iso_string(self, mock_ynab_request):
        mock_ynab_request.return_value = {"transactions": []}
        tx_mod.fetch_transactions("b1", since_date="2026-04-01")
        params = mock_ynab_request.call_args.kwargs["params"]
        assert params == {"since_date": "2026-04-01"}

    def test_transaction_type_filter(self, mock_ynab_request):
        mock_ynab_request.return_value = {"transactions": []}
        tx_mod.fetch_transactions("b1", transaction_type="unapproved")
        params = mock_ynab_request.call_args.kwargs["params"]
        assert params == {"type": "unapproved"}


class TestToTransaction:
    def test_populates_all_fields_from_raw(self):
        tx = tx_mod._to_transaction(_tx_raw())
        assert tx.id == "tx-1"
        assert tx.date == "2026-05-08"
        assert tx.amount_milliunits == -12340
        assert tx.amount_dollars == -12.34
        assert tx.cleared == "uncleared"
        assert tx.payee_name == "Bistro"

    def test_null_strings_normalize_to_empty(self):
        raw = _tx_raw(memo=None, payee_name=None, category_id=None, flag_color=None)
        tx = tx_mod._to_transaction(raw)
        assert tx.memo == ""
        assert tx.payee_name == ""
        assert tx.category_id == ""
        assert tx.flag_color == ""
        assert tx.transfer_account_id == ""


class TestUpdateTransaction:
    def test_memo_only_sends_only_memo(self, mock_ynab_raw_request):
        mock_ynab_raw_request.return_value = _mock_patch_response(_tx_raw(memo="new"))

        result = tx_mod.update_transaction("tx-1", memo="new")

        assert result.memo == "new"
        kwargs = mock_ynab_raw_request.call_args.kwargs
        assert mock_ynab_raw_request.call_args.args[:2] == (
            "PATCH",
            "/budgets/last-used/transactions/tx-1",
        )
        assert kwargs["json"] == {"transaction": {"memo": "new"}}

    def test_memo_clear_emits_null(self, mock_ynab_raw_request):
        mock_ynab_raw_request.return_value = _mock_patch_response(_tx_raw(memo=""))
        tx_mod.update_transaction("tx-1", memo=CLEAR)
        assert mock_ynab_raw_request.call_args.kwargs["json"] == {
            "transaction": {"memo": None}
        }

    def test_no_args_sends_empty_transaction_object(self, mock_ynab_raw_request):
        mock_ynab_raw_request.return_value = _mock_patch_response(_tx_raw())
        tx_mod.update_transaction("tx-1")
        assert mock_ynab_raw_request.call_args.kwargs["json"] == {"transaction": {}}

    def test_cleared_passes_through(self, mock_ynab_raw_request):
        mock_ynab_raw_request.return_value = _mock_patch_response(_tx_raw())
        tx_mod.update_transaction("tx-1", cleared="reconciled")
        assert mock_ynab_raw_request.call_args.kwargs["json"] == {
            "transaction": {"cleared": "reconciled"}
        }

    def test_approved_passes_through(self, mock_ynab_raw_request):
        mock_ynab_raw_request.return_value = _mock_patch_response(_tx_raw())
        tx_mod.update_transaction("tx-1", approved=False)
        assert mock_ynab_raw_request.call_args.kwargs["json"] == {
            "transaction": {"approved": False}
        }

    def test_flag_color_set_and_clear(self, mock_ynab_raw_request):
        mock_ynab_raw_request.return_value = _mock_patch_response(_tx_raw())

        tx_mod.update_transaction("tx-1", flag_color="blue")
        assert mock_ynab_raw_request.call_args.kwargs["json"] == {
            "transaction": {"flag_color": "blue"}
        }

        tx_mod.update_transaction("tx-1", flag_color=CLEAR)
        assert mock_ynab_raw_request.call_args.kwargs["json"] == {
            "transaction": {"flag_color": None}
        }

    def test_category_id_clear(self, mock_ynab_raw_request):
        mock_ynab_raw_request.return_value = _mock_patch_response(_tx_raw())
        tx_mod.update_transaction("tx-1", category_id=CLEAR)
        assert mock_ynab_raw_request.call_args.kwargs["json"] == {
            "transaction": {"category_id": None}
        }

    def test_date_accepts_date_object(self, mock_ynab_raw_request):
        mock_ynab_raw_request.return_value = _mock_patch_response(_tx_raw())
        tx_mod.update_transaction("tx-1", date=date(2026, 4, 1))
        assert mock_ynab_raw_request.call_args.kwargs["json"] == {
            "transaction": {"date": "2026-04-01"}
        }

    def test_amount_milliunits_passes_through(self, mock_ynab_raw_request):
        mock_ynab_raw_request.return_value = _mock_patch_response(_tx_raw())
        tx_mod.update_transaction("tx-1", amount_milliunits=-9990)
        assert mock_ynab_raw_request.call_args.kwargs["json"] == {
            "transaction": {"amount": -9990}
        }

    def test_non_2xx_raises_with_ynab_detail(self, mock_ynab_raw_request):
        resp = MagicMock()
        resp.status_code = 400
        resp.json.return_value = {
            "error": {"id": "400", "name": "bad_request", "detail": "missing date"}
        }
        resp.text = ""
        mock_ynab_raw_request.return_value = resp
        with pytest.raises(MgdioAPIError, match="missing date"):
            tx_mod.update_transaction("tx-1", memo="x")


class TestClearSingleton:
    def test_clear_is_singleton(self):
        from mgdio.ynab.transactions import _ClearType

        assert _ClearType() is CLEAR
        assert _ClearType() is _ClearType()
        assert repr(CLEAR) == "CLEAR"
