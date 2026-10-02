# Claude Code skills

mgdio ships with seven [Claude Code](https://claude.com/claude-code) skills,
one per service, that teach Claude how to drive the CLI for you. Once deployed
you can ask Claude things like *"list my 5 most recent emails"*, *"what's on
my calendar this week"*, *"edit transaction abc-123's memo to 'grocery run'"*,
*"upload this file to my Reports folder in Drive"*, or *"how far is it from
here to the airport"*, and it reaches for `mgdio` instead of inventing API
calls.

## Deploy

```bash
# Preview what's bundled
mgdio skills list

# Deploy to the CURRENT project (./.claude/skills/)
mgdio skills deploy

# Deploy GLOBALLY (~/.claude/skills/) so every project sees the skills
mgdio skills deploy --global

# Re-deploy after an mgdio upgrade
mgdio skills deploy --force
```

After deploying, restart Claude Code or run `/clear` to load the skills.

## The bundled skills

| Skill | Covers |
| --- | --- |
| `mgdio-gmail` | list / search / read / send email |
| `mgdio-sheets` | read / write / append / clear values, manage tabs, create spreadsheets |
| `mgdio-calendar` | list calendars, list / fetch / create / update / delete events, quick-add |
| `mgdio-drive` | list / search, metadata, folders, upload / download / export, rename / move / copy, trash / delete, sharing |
| `mgdio-ynab` | budgets / accounts / categories / transactions, edit a transaction's memo, cleared status, flag, or category |
| `mgdio-whoop` | recovery, sleep, workouts, cycles, profile, body measurements (read-only) |
| `mgdio-maps` | geocode, reverse-geocode, distance / duration / directions (read-only) |

## Safety contract

Every skill tells Claude that reads are fine to run on their own, but writes
(sending email, creating or changing events, writing to sheets, editing YNAB
transactions, uploading, moving, or deleting Drive files, changing sharing)
**must be confirmed with you before invocation**. Claude paraphrases the
action and waits for explicit approval, even when the conversation sounded
like permission was implied. Writes are never chained without re-confirming.
Drive's `delete` and `empty-trash` are flagged as irreversible, so Claude is
told to prefer the recoverable `trash`.
