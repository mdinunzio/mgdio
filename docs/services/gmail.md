# Gmail

Read and send mail on the shared Google login. Once
[`mgdio auth google`](../auth.md#first-run-auth) has run, Gmail needs no
further setup.

| | |
| --- | --- |
| Import | `from mgdio.gmail import fetch_messages, fetch_message, send_email` |
| Returns | [`GmailMessage`](../reference/gmail.md) frozen dataclass |
| CLI | `mgdio gmail list / get / send` |
| Reference | [mgdio.gmail](../reference/gmail.md) |
| Example | [`examples/gmail.py`](https://github.com/mdinunzio/mgdio/blob/main/examples/gmail.py) |

## Python

```python
from pathlib import Path

from mgdio.gmail import fetch_message, fetch_messages, send_email

# List the 5 most recent messages.
for m in fetch_messages(max_results=5):
    print(m.date, m.sender, m.subject, m.id)

# Search with Gmail's query syntax.
hits = fetch_messages(query="from:foo@bar.com after:2026/01/01", max_results=20)

# Fetch one message's full content (headers, snippet, plain + HTML body).
msg = fetch_message("199a8b3c...")
print(msg.body_text)

# Send plain text.
send_email(to="someone@example.com", subject="hi", body="hello from mgdio")

# Send HTML + attachment, with cc/bcc.
send_email(
    to=["a@example.com", "b@example.com"],
    subject="weekly report",
    body="See attached. Plain-text fallback.",
    html="<p>See <b>attached</b>.</p>",
    cc="boss@example.com",
    attachments=[Path("report.pdf")],
)
```

Every function accepts a trailing `profile=` keyword to pick a Google account.
See [profiles](../auth.md#multiple-google-accounts-profiles).

!!! info "Personal accounts and rate limits"
    `fetch_messages` collapses the per-message GETs into one batched HTTP
    round trip. Consumer `@gmail.com` accounts have a much lower concurrency
    cap than Workspace accounts, so a 100-wide batch can trip
    `rateLimitExceeded`. Pass `batch_size=20` for personal accounts. Failed
    ids are retried with exponential backoff (`max_retries`,
    `initial_backoff`).

## CLI

```bash
mgdio gmail list --max 5
mgdio gmail list --query "from:noreply@github.com" --max 3
mgdio gmail get <message_id>
mgdio gmail send --to me@example.com --subject hi --body "hello"
mgdio gmail send --to me@example.com --subject report \
  --body "see attached" --attach report.pdf --attach summary.csv
```

Add `--profile <slug>` to any command to choose the Google account.
