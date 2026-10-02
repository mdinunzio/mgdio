# Drive

List and search files, read metadata, create folders, upload, download binary
files or export Google-native docs, rename, move, copy, trash or delete, and
manage sharing. Uses the shared Google login from
[`mgdio auth google`](../auth.md#first-run-auth).

| | |
| --- | --- |
| Import | `from mgdio.drive import list_files, upload_file, share_file, ...` |
| Returns | [`DriveFile`](../reference/drive.md) and `Permission` frozen dataclasses |
| CLI | `mgdio drive list / get / mkdir / upload / download / export / rename / move / copy / trash / delete / empty-trash / perms / share / unshare` |
| Reference | [mgdio.drive](../reference/drive.md) |
| Example | [`examples/drive_demo.py`](https://github.com/mdinunzio/mgdio/blob/main/examples/drive_demo.py) |

!!! warning "Authorized before Drive existed?"
    Drive added the `https://www.googleapis.com/auth/drive` scope. A token
    issued before that will not carry it, and the first Drive call falls back
    to the setup flow. Run `mgdio auth google --profile <slug> --reset` and
    approve the consent screen once more.

## Python

```python
from pathlib import Path

from mgdio.drive import (
    copy_file,
    create_folder,
    delete_file,
    download_file,
    empty_trash,
    export_file,
    fetch_file,
    list_files,
    list_permissions,
    move_file,
    share_file,
    trash_file,
    unshare_file,
    update_file,
    update_permission,
    upload_file,
)

# List / search. Listing auto-paginates up to max_results.
recent = list_files(order_by="modifiedTime desc", max_results=10)
for f in recent:
    print("DIR " if f.is_folder else "FILE", f.name, f.id)

# `query` is the raw Drive `q` parameter.
pdfs = list_files(query="mimeType='application/pdf'", max_results=20)
hits = list_files(query="name contains 'invoice'")
children = list_files(parent_id="<folder_id>")
trashed = list_files(include_trashed=True)

# Metadata for one file.
meta = fetch_file("<file_id>")
print(meta.name, meta.size_bytes, meta.modified_time, meta.web_view_link)

# Folders and uploads.
folder = create_folder("Reports", parent_id="<parent_folder_id>")
up = upload_file(Path("report.pdf"), name="Q1.pdf", parent_id=folder.id)

# Download a BINARY file's bytes to disk.
download_file(up.id, Path("./Q1-local.pdf"))

# Google-native Docs/Sheets/Slides have no raw bytes: export instead.
export_file("<google_doc_id>", Path("./out.pdf"), mime_type="application/pdf")
export_file("<google_sheet_id>", Path("./out.csv"), mime_type="text/csv")

# Rename / star. update_file leaves unspecified fields untouched.
update_file(up.id, name="Q1-final.pdf")
update_file(up.id, starred=True)

# Move (re-parents; removes the old parent by default) and copy.
move_file(up.id, "<new_folder_id>")
copy_file(up.id, name="Q1-copy.pdf", parent_id=folder.id)

# Trash is recoverable; delete is PERMANENT and skips the trash.
trash_file(up.id)
trash_file(up.id, trashed=False)   # restore
delete_file(up.id)                 # irreversible
empty_trash()                      # irreversible

# Sharing. Exactly one grantee: email, domain, or anyone-with-the-link.
perm = share_file(folder.id, role="reader", email="alice@example.com")
share_file(folder.id, role="writer", anyone=True)
share_file(folder.id, role="reader", domain="example.com")
for p in list_permissions(folder.id):
    print(p.role, p.type, p.email_address or p.domain or p.type, p.id)
update_permission(folder.id, perm.id, role="writer")
unshare_file(folder.id, perm.id)
```

Every function accepts a trailing `profile=` keyword to pick a Google account.

## CLI

```bash
mgdio drive list --max 25
mgdio drive list --query "name contains 'invoice'" --max 10
mgdio drive list --parent <folder_id>
mgdio drive get <file_id>
mgdio drive mkdir "Reports" --parent <folder_id>
mgdio drive upload ./report.pdf --name "Q1.pdf" --parent <folder_id>
mgdio drive download <file_id> ./local.pdf
mgdio drive export <doc_id> ./out.pdf --mime application/pdf
mgdio drive rename <file_id> "new name.pdf"
mgdio drive move <file_id> <new_parent_folder_id>
mgdio drive copy <file_id> --name "copy" --parent <folder_id>
mgdio drive trash <file_id>            # recoverable
mgdio drive trash <file_id> --restore  # un-trash
mgdio drive delete <file_id>           # PERMANENT
mgdio drive empty-trash                # PERMANENT
mgdio drive perms <file_id>
mgdio drive share <file_id> --role reader --email alice@example.com
mgdio drive unshare <file_id> <permission_id>
```

Add `--profile <slug>` to any command to choose the Google account.
