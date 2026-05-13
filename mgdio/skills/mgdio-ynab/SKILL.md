---
name: mgdio-ynab
description: Read YNAB budgets/accounts/categories/transactions and edit
  individual transactions via the `mgdio ynab` CLI. Use this when the
  user asks about YNAB balances, account totals, category spending
  ("how much have I spent on groceries this month"), recent
  transactions, or wants to edit a transaction's memo / cleared status /
  flag / category / approval / amount. Handles milliunit money on the
  user's behalf (never asks the user to enter milliunits).
---

# mgdio YNAB

Read budgets, accounts, categories, and transactions; edit transaction
fields. Backed by YNAB's REST API and the user's personal access token.

## Prerequisite

The user must have authenticated once: `mgdio auth ynab`. This opens a
local web page where the user pastes a token they mint at
<https://app.ynab.com/settings/developer>. YNAB uses its own auth, not
the same Google token as Gmail/Sheets/Calendar.

## Safety contract

**Read** operations (`budgets`, `accounts`, `categories`, `transactions`)
are safe to perform on user request. **Write** operations (`update-tx`,
including the `--clear-memo` flag) MUST be confirmed with the user
before invocation. Paraphrase the change — which transaction, what
field, what new value — and wait for explicit approval, even if the
user's prompt sounded like permission. Never chain multiple writes
without re-confirming each one. YNAB writes are reversible by editing
the field back, but it's still the user's ledger.

## CLI: read

```bash
# List every budget the token can see (the id of the first one is usually
# what the user wants; "last-used" is a magic alias on all other commands)
mgdio ynab budgets

# Accounts on a budget with balances
mgdio ynab accounts --budget last-used
mgdio ynab accounts --budget <budget_id>

# Category groups + this month's budgeted/activity/balance
mgdio ynab categories --budget last-used

# Transactions, optionally filtered. --account and --category are
# mutually exclusive. --since accepts ISO YYYY-MM-DD.
mgdio ynab transactions --budget last-used --max 20
mgdio ynab transactions --since 2026-04-01 --account <account_id>
mgdio ynab transactions --since 2026-04-01 --category <category_id>
```

`accounts` prints one line per account: type, name, dollar balance, id.
`categories` prints groups + nested categories with dollar totals.
`transactions` prints `YYYY-MM-DD  <amount $>  <payee>  <category>  <memo>  [<tx_id>]`.

## CLI: write (REQUIRES CONFIRMATION)

```bash
# Edit a memo (the most common use)
mgdio ynab update-tx <transaction_id> --memo "grocery run, target trip"

# Clear an existing memo
mgdio ynab update-tx <transaction_id> --clear-memo

# Mark cleared / approved
mgdio ynab update-tx <transaction_id> --cleared cleared
mgdio ynab update-tx <transaction_id> --approved

# Add or change a flag color
mgdio ynab update-tx <transaction_id> --flag blue
```

`update-tx` prints the updated transaction's id, date, dollar amount,
new memo, and cleared status.

## Python (when chaining is needed)

```python
from datetime import date
from mgdio.ynab import (
    CLEAR,
    fetch_budgets, fetch_accounts, fetch_categories, fetch_transactions,
    update_transaction,
    Budget, Account, Category, CategoryGroup, Transaction,
)
```

`fetch_budgets() -> list[Budget]`.
`fetch_accounts(budget_id="last-used") -> list[Account]`.
`fetch_categories(budget_id="last-used") -> list[CategoryGroup]` —
returns groups with `.categories` nested.
`fetch_transactions(budget_id="last-used", *, since_date=None, account_id=None,
category_id=None, transaction_type=None) -> list[Transaction]` —
`account_id` and `category_id` are mutually exclusive (`ValueError`);
`transaction_type` accepts `"uncategorized"` or `"unapproved"`.

`update_transaction(transaction_id, *, budget_id="last-used", memo=...,
cleared=..., approved=..., flag_color=..., category_id=..., payee_name=...,
date=..., amount_milliunits=...) -> Transaction`. Tri-state PATCH:
`None` (default) leaves the field alone, `CLEAR` nulls it, a value sets it.

Dataclass fields worth knowing:

- `Budget`: `id, name, currency_iso_code, decimal_digits, last_modified_on`.
- `Account`: `id, name, type, on_budget, closed, balance_milliunits,
  cleared_balance_milliunits, uncleared_balance_milliunits, deleted`.
  **Property: `balance_dollars` (and similar) returns the float.**
- `Category`: `id, category_group_id, name, hidden, budgeted_milliunits,
  activity_milliunits, balance_milliunits, note, deleted`. Properties:
  `budgeted_dollars`, `activity_dollars`, `balance_dollars`.
- `CategoryGroup`: `id, name, hidden, deleted, categories: tuple[Category, ...]`.
- `Transaction`: `id, date: str ("YYYY-MM-DD"), amount_milliunits,
  memo, cleared, approved, flag_color, account_id, account_name,
  payee_id, payee_name, category_id, category_name, transfer_account_id,
  deleted`. Property: `amount_dollars`. **`amount_milliunits` is negative
  for outflows.**

## Gotchas

- **Money is integer milliunits on the wire.** `$12.34` is `12340`,
  `-$5.00` is `-5000`. **Always present and accept dollars to the
  user**; convert silently. When you must pass `amount_milliunits=`,
  multiply the user's dollar amount by 1000 and round.
- **`budget_id="last-used"`** is a magic alias the API accepts on every
  budget-scoped endpoint. Use it when the user hasn't named a specific
  budget. Otherwise pull the id from `fetch_budgets()` or
  `mgdio ynab budgets`.
- **`account_id` and `category_id` are mutually exclusive** in
  `fetch_transactions` — YNAB exposes three different endpoints (plain,
  account-scoped, category-scoped) under the hood.
- **`CLEAR` sentinel** for `update_transaction`: `memo=CLEAR` nulls the
  memo; `memo=None` (the default) leaves it alone; `memo="..."` sets it.
- **`flag_color`** is one of `"red" | "orange" | "yellow" | "green" |
  "blue" | "purple"` or `CLEAR`. The CLI uses `--flag <color>`.
- **`cleared`** is one of `"cleared" | "uncleared" | "reconciled"`. The
  CLI uses `--cleared <state>`.
- **`approved`** is a bool. On the CLI: `--approved` / `--unapproved`.
- **`date`** in `update_transaction` accepts a `date` object or a
  `"YYYY-MM-DD"` string — pick whichever is more natural for the
  context.
