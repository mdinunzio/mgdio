---
name: mgdio-gmail
description: Read and send Gmail using the `mgdio gmail` CLI. Use this when the
  user asks about their inbox, wants to list/search/read recent emails, fetch a
  specific message by id, draft and send a new message (plain text or HTML),
  reply with attachments, or check whether a message arrived. Covers both
  one-off CLI invocations and Python-API chaining for follow-up reasoning.
---

# mgdio Gmail

Read and send email through the user's Gmail account via the `mgdio` CLI.

## Prerequisite

The user must have authenticated once:
`mgdio auth google --profile <slug>`. If any command below fails with an
auth error (HTTP 401, "no token", or "no Google profiles"), tell the user
to authorize a profile first. On a headless box, add `--headless`. Add
`--profile <slug>` to any `mgdio gmail` command to target a specific
account; omit it to use `$MGDIO_GOOGLE_PROFILE` or the sole profile.

## Safety contract

**Read** operations (list, search, get) are safe to perform on user request.
**Send** is a write operation: it MUST be confirmed with the user before
invocation. Paraphrase what you're about to send (recipient, subject, body
summary, any attachments) and wait for explicit approval, even if the
user's prompt sounded like permission. Never send multiple emails in a
chain without re-confirming each one.

## CLI: read

```bash
# List 5 most recent inbox messages
mgdio gmail list --max 5

# Search with Gmail's query syntax
mgdio gmail list --query "is:unread" --max 10
mgdio gmail list --query "from:noreply@github.com newer_than:7d" --max 5
mgdio gmail list --query "subject:invoice has:attachment" --max 20

# Fetch one full message by id (id comes from `list`)
mgdio gmail get <message_id>
```

`mgdio gmail list` prints one line per message:
`YYYY-MM-DD HH:MM  <sender truncated to 40>  <subject>  [<message_id>]`

`mgdio gmail get` prints headers (id, date, from, to, cc, subject, labels),
snippet, then the plain-text body.

## CLI: send (REQUIRES CONFIRMATION)

```bash
# Plain text
mgdio gmail send --to alice@example.com --subject "hi" --body "hello"

# cc + bcc
mgdio gmail send --to a@x.com --cc b@x.com --bcc c@x.com \
  --subject "..." --body "..."

# HTML alternative (plain-text body is still required as the fallback)
mgdio gmail send --to a@x.com --subject "report" \
  --body "see attached, plain-text fallback" \
  --html "<p>See <b>attached</b>.</p>"

# Attachments (repeatable)
mgdio gmail send --to a@x.com --subject "files" --body "see attached" \
  --attach ./report.pdf --attach ./summary.csv
```

Each `send` prints `Sent: <message_id>` on success and exits non-zero on
failure.

## Python (when chaining is needed)

```python
from mgdio.gmail import fetch_messages, fetch_message, send_email, GmailMessage
```

`fetch_messages(query: str = "", max_results: int = 50, *, batch_size: int = 100,
max_retries: int = 5, initial_backoff: float = 1.0) -> list[GmailMessage]`
returns newest-first. `fetch_message(message_id: str) -> GmailMessage`
fetches one. `send_email(to, subject, body, *, cc=None, bcc=None,
attachments=None, html=None, sender=None) -> str` returns the new
message id. Recipients accept `str` or `Sequence[str]`.

**Rate-limit knob**: `fetch_messages` bundles `messages.get` calls into
a `BatchHttpRequest` and dispatches them concurrently. Workspace
accounts handle the default `batch_size=100` fine; **personal /
consumer Gmail accounts have a lower concurrency cap** and may return
`rateLimitExceeded` (HTTP 429) on a wide batch. If a call to
`fetch_messages(max_results=100)` fails with
`MgdioAPIError: ... rateLimitExceeded`, drop the batch size:

```python
receipts = fetch_messages(query="newer_than:30d", max_results=100,
                          batch_size=10)
```

The function also retries any 429-tagged ids automatically with
exponential backoff (1s, 2s, 4s, ..., capped at 30s; default 5
retries). Tune via `max_retries` and `initial_backoff` if needed.

`GmailMessage` (frozen dataclass) fields:

- `id: str`, `thread_id: str`
- `subject: str`, `sender: str` (the `From` header)
- `to: tuple[str, ...]`, `cc: tuple[str, ...]`
- `date: datetime` (UTC, tz-aware)
- `snippet: str`, `body_text: str`, `body_html: str | None`
- `label_ids: tuple[str, ...]`

## Gmail search query syntax (most useful)

- `from:foo@bar.com`, `to:`, `subject:`, `has:attachment`
- `is:unread`, `is:read`, `is:starred`, `in:inbox`, `in:trash`
- `newer_than:7d` / `older_than:1y`, `after:2026/01/01`, `before:2026/02/01`
- Combine with spaces (AND), `OR`, or `-` for NOT.
