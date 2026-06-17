---
name: mgdio-drive
description: Manage Google Drive files and folders via the `mgdio drive` CLI.
  Use this when the user wants to list/search their Drive, get file
  metadata, create folders, upload a local file, download or export a
  file, rename/move/copy files, trash or permanently delete files, empty
  the trash, or manage sharing (list/grant/revoke permissions). Handles
  binary files vs Google-native docs (Docs/Sheets/Slides need export).
---

# mgdio Drive

Read and manage the user's Google Drive via the `mgdio` CLI.

## Prerequisite

The user must have authenticated once with the Drive scope:
`mgdio auth google --profile <slug>`. Drive shares the per-account
`mgdio:google:<slug>` token with Gmail, Sheets, and Calendar. If Drive was
added after the user last authorized, the first Drive call triggers a
one-time re-consent — tell them to run
`mgdio auth google --profile <slug> --reset` and re-approve.

**Multiple accounts:** add `--profile <slug>` to any `mgdio drive` command
to target a specific Google account. Omit it to use `$MGDIO_GOOGLE_PROFILE`
or the sole configured profile. `mgdio auth google profiles` lists them.

## Safety contract

**Read** operations (`list`, `get`, `download`, `export`, `perms`) are
safe to perform on user request. **Write** operations — `mkdir`,
`upload`, `rename`, `move`, `copy`, `trash`, `delete`, `empty-trash`,
`share`, `unshare` — MUST be confirmed with the user before invocation.
Paraphrase exactly what you're about to do (which file/folder, the
target, who you're sharing with) and wait for explicit approval, even if
the user's prompt sounded like permission. Never chain multiple writes
without re-confirming each one.

**`delete` and `empty-trash` are irreversible** (permanent, skip the
trash). Be especially explicit before running them — prefer `trash` (which
is recoverable) unless the user clearly wants a permanent delete.

## CLI: read

```bash
# List / search. --query is the raw Drive `q` parameter.
mgdio drive list --max 25
mgdio drive list --query "name contains 'invoice'" --max 10
mgdio drive list --query "mimeType='application/pdf'" --order "modifiedTime desc"
mgdio drive list --parent <folder_id>              # children of a folder
mgdio drive list --trashed                          # include trashed

# Metadata for one file
mgdio drive get <file_id>

# Sharing permissions on a file
mgdio drive perms <file_id>

# Download a BINARY file's content
mgdio drive download <file_id> ./local.pdf

# Export a GOOGLE-NATIVE doc (Docs/Sheets/Slides) -- they have no raw bytes
mgdio drive export <doc_id> ./out.pdf --mime application/pdf
mgdio drive export <sheet_id> ./out.csv --mime text/csv
```

`mgdio drive list` prints one line per entry:
`FILE|DIR  <size>  <name>  [<file_id>]` (a `*` marks starred items).

## CLI: write (REQUIRES CONFIRMATION)

```bash
mgdio drive mkdir "Reports" --parent <folder_id>
mgdio drive upload ./report.pdf --name "Q1.pdf" --parent <folder_id>
mgdio drive rename <file_id> "new name.pdf"
mgdio drive move <file_id> <new_parent_folder_id>
mgdio drive copy <file_id> --name "copy" --parent <folder_id>
mgdio drive trash <file_id>            # recoverable
mgdio drive trash <file_id> --restore  # un-trash
mgdio drive delete <file_id>           # PERMANENT, irreversible
mgdio drive empty-trash                # PERMANENT, irreversible

# Sharing
mgdio drive share <file_id> --role reader --email alice@example.com
mgdio drive share <file_id> --role writer --anyone
mgdio drive share <file_id> --role reader --domain example.com
mgdio drive unshare <file_id> <permission_id>   # id from `drive perms`
```

## Python (when chaining is needed)

```python
from mgdio.drive import (
    list_files, fetch_file, create_folder, upload_file,
    download_file, export_file, update_file, move_file, copy_file,
    trash_file, delete_file, empty_trash,
    list_permissions, share_file, update_permission, unshare_file,
    DriveFile, Permission, FOLDER_MIME_TYPE,
)
```

`list_files(*, query="", parent_id=None, include_trashed=False,
order_by=None, max_results=100) -> list[DriveFile]` — auto-paginates.
`fetch_file(file_id) -> DriveFile`. `create_folder(name, *,
parent_id=None) -> DriveFile`. `upload_file(local_path, *, name=None,
parent_id=None, mime_type=None) -> DriveFile`. `download_file(file_id,
local_path) -> Path` (binary). `export_file(file_id, local_path, *,
mime_type) -> Path` (Google-native). `update_file(file_id, *, name=None,
starred=None, local_path=None) -> DriveFile`. `move_file(file_id,
new_parent_id, *, remove_existing_parents=True)`. `copy_file(...)`.
`trash_file(file_id, *, trashed=True)`. `delete_file(file_id)` /
`empty_trash()`.

Sharing: `list_permissions(file_id) -> list[Permission]`,
`share_file(file_id, *, role="reader", email=None, domain=None,
anyone=False, send_notification=False) -> Permission` (exactly one of
email/domain/anyone), `update_permission(file_id, permission_id, *,
role)`, `unshare_file(file_id, permission_id)`.

`DriveFile` fields: `id, name, mime_type, parents (tuple),
size_bytes (None for folders/native), created_time, modified_time
(tz-aware), web_view_link, web_content_link, trashed, starred, shared,
md5_checksum, file_extension, icon_link, owner_emails (tuple)`. Plus
properties `is_folder` and `is_google_native`.

`Permission` fields: `id, type, role, email_address, domain,
display_name`.

## Gotchas

- **Google-native vs binary.** Docs/Sheets/Slides (`is_google_native`,
  mime `application/vnd.google-apps.*`) have no raw bytes — `download`
  fails; use `export` with a target mime type. Folders are
  `FOLDER_MIME_TYPE` (`application/vnd.google-apps.folder`).
- **`delete` is permanent.** It skips the trash. Use `trash` for a
  recoverable removal.
- **`move` re-parents.** By default it removes the file from its old
  folder(s). Pass `remove_existing_parents=False` to multi-home it.
- **The `query` is raw Drive syntax.** Common terms: `name contains '...'`,
  `mimeType='...'`, `'<folderId>' in parents`, `starred = true`,
  `modifiedTime > '2026-01-01T00:00:00'`. Combine with `and` / `or`.
- **File ids** are the opaque strings in a file's URL (after `/d/`).
