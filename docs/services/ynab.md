# YNAB

Budgets, accounts, categories, transactions, and transaction edits (memo,
cleared status, flag, category, approval, amount).

| | |
| --- | --- |
| Import | `from mgdio.ynab import fetch_budgets, fetch_transactions, update_transaction, CLEAR, ...` |
| Returns | [`Budget`](../reference/ynab.md), `Account`, `CategoryGroup`, `Category`, `Transaction` frozen dataclasses |
| CLI | `mgdio ynab budgets / accounts / categories / transactions / update-tx` |
| Reference | [mgdio.ynab](../reference/ynab.md) |
| Example | [`examples/ynab_demo.py`](https://github.com/mdinunzio/mgdio/blob/main/examples/ynab_demo.py) |

## Setup

YNAB uses a personal access token, not OAuth.

```bash
mgdio auth ynab              # opens a setup page
mgdio auth ynab --headless   # paste the token on the terminal instead
mgdio auth ynab --reset      # paste a new one
```

The setup page links to <https://app.ynab.com/settings/developer> where you
mint a token. Paste it in; mgdio validates it against `GET /v1/user` before
saving to the keyring under `mgdio:ynab`, so typos surface immediately.

## Money is milliunits

YNAB stores money as integer **milliunits** on the wire (`$12.34` is `12340`).
Every dataclass exposes both the raw field and a `..._dollars` property, so
you can stay exact or get a float for display.

## Python

```python
from datetime import date

from mgdio.ynab import (
    CLEAR,
    fetch_accounts,
    fetch_budgets,
    fetch_categories,
    fetch_transactions,
    update_transaction,
)

# Discover budgets. The "last-used" alias also works everywhere below.
for b in fetch_budgets():
    print(b.id, b.name, b.currency_iso_code)

# Accounts and balances on a budget.
for acct in fetch_accounts(budget_id="last-used"):
    print(acct.name, acct.balance_dollars, "on-budget" if acct.on_budget else "tracking")

# This month's categories with budgeted / activity / balance.
for group in fetch_categories():
    for cat in group.categories:
        if cat.hidden or cat.deleted:
            continue
        print(group.name, cat.name, cat.balance_dollars)

# Transactions, optionally filtered.
txns = fetch_transactions(since_date=date(2026, 4, 1), account_id="<acct-id>")

# Edit a transaction's memo (the headline use case).
update_transaction(txns[0].id, memo="grocery run")
update_transaction(txns[0].id, memo=CLEAR)   # explicit clear
update_transaction(txns[0].id, cleared="cleared", flag_color="blue")
```

## CLI

```bash
mgdio ynab budgets
mgdio ynab accounts --budget last-used
mgdio ynab categories --budget last-used
mgdio ynab transactions --since 2026-04-01 --max 20
mgdio ynab transactions --account <acct-id>
mgdio ynab update-tx <tx-id> --memo "new note"
mgdio ynab update-tx <tx-id> --clear-memo
mgdio ynab update-tx <tx-id> --cleared cleared --flag blue
```
