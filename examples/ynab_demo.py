"""YNAB end-to-end demo for the mgdio package.

Run this after installing mgdio and completing the one-time setup
(``uv run mgdio auth ynab``).

Walks through the read paths and one safe write path:

1. List every budget the token can see, then pick the first.
2. List accounts on that budget with current balances.
3. Show category groups + this month's budgeted/activity/balance.
4. Show the 5 most recent transactions on the budget.
5. Round-trip a memo edit on the most recent transaction (we restore
   the original memo at the end so the demo leaves no trace).

Usage:
    uv run python examples/ynab_demo.py
"""

from __future__ import annotations

from mgdio.ynab import (
    CLEAR,
    fetch_accounts,
    fetch_budgets,
    fetch_categories,
    fetch_transactions,
    update_transaction,
)


def main() -> None:
    """Run the full YNAB demo cycle."""
    print("== 1. Budgets visible to this token ==")
    budgets = fetch_budgets()
    if not budgets:
        print("   (none)")
        return
    for b in budgets:
        print(f"   {b.id}  {b.name}  ({b.currency_iso_code})")
    budget = budgets[0]
    print(f"\n-> using budget: {budget.name} ({budget.id})")

    print("\n== 2. Accounts ==")
    for acct in fetch_accounts(budget.id):
        if acct.closed or acct.deleted:
            continue
        marker = " " if acct.on_budget else "T"
        print(
            f"   {marker} {acct.type:12} {acct.name[:30]:30} "
            f"{acct.balance_dollars:>12.2f}"
        )

    print("\n== 3. Categories (this month) ==")
    for group in fetch_categories(budget.id):
        if group.hidden or group.deleted:
            continue
        print(f"\n   # {group.name}")
        for cat in group.categories:
            if cat.hidden or cat.deleted:
                continue
            print(
                f"     {cat.name[:30]:30} "
                f"budgeted {cat.budgeted_dollars:>10.2f}  "
                f"activity {cat.activity_dollars:>10.2f}  "
                f"balance {cat.balance_dollars:>10.2f}"
            )

    print("\n== 4. 5 most recent transactions ==")
    txns = fetch_transactions(budget.id)
    if not txns:
        print("   (none)")
        return
    for tx in txns[:5]:
        print(
            f"   {tx.date}  {tx.amount_dollars:>10.2f}  "
            f"{tx.payee_name[:24]:24} {(tx.memo or '')[:30]:30} [{tx.id}]"
        )

    print("\n== 5. Round-trip a memo edit on the most recent transaction ==")
    target = txns[0]
    original_memo = target.memo
    print(f"   original memo on {target.id!r}: {original_memo!r}")
    edited = update_transaction(
        target.id,
        budget_id=budget.id,
        memo="(mgdio demo edited this memo)",
    )
    print(f"   after edit:  {edited.memo!r}")
    restored = update_transaction(
        target.id,
        budget_id=budget.id,
        memo=original_memo if original_memo else CLEAR,
    )
    print(f"   restored to: {restored.memo!r}")

    print("\nDone.")


if __name__ == "__main__":
    main()
