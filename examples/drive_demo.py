"""Google Drive end-to-end demo for the mgdio package.

Run this after installing mgdio and completing the one-time OAuth setup
(``uv run mgdio auth google`` -- re-run with ``--reset`` if you added the
Drive scope after your last authorization).

Walks through a full create -> upload -> list -> download -> share ->
cleanup cycle on a throwaway folder, then deletes everything it made.

Usage:
    uv run python examples/drive_demo.py
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from mgdio.drive import (
    create_folder,
    delete_file,
    download_file,
    fetch_file,
    list_files,
    list_permissions,
    share_file,
    upload_file,
)


def main() -> None:
    """Run the full Drive demo cycle (creates + deletes a throwaway folder)."""
    token = uuid.uuid4().hex[:8]

    print("== 1. Recent files in My Drive ==")
    for f in list_files(order_by="modifiedTime desc", max_results=5):
        kind = "DIR " if f.is_folder else "FILE"
        print(f"   {kind}  {f.name[:50]:50}  [{f.id}]")

    print(f"\n== 2. Create a throwaway folder: mgdio-demo-{token} ==")
    folder = create_folder(f"mgdio-demo-{token}")
    print(f"   id:  {folder.id}")
    print(f"   url: {folder.web_view_link}")

    print("\n== 3. Upload a small file into it ==")
    local = Path(tempfile.gettempdir()) / f"mgdio_demo_{token}.txt"
    local.write_text(f"hello from mgdio drive demo\ntoken: {token}\n", encoding="utf-8")
    uploaded = upload_file(local, parent_id=folder.id)
    print(f"   uploaded: {uploaded.name}  [{uploaded.id}]  ({uploaded.size_bytes} B)")

    print("\n== 4. List the folder's contents ==")
    for f in list_files(parent_id=folder.id, max_results=10):
        print(f"   {f.name}  [{f.id}]")

    print("\n== 5. Fetch metadata + download the content back ==")
    meta = fetch_file(uploaded.id)
    print(f"   modified: {meta.modified_time}")
    dest = Path(tempfile.gettempdir()) / f"mgdio_demo_roundtrip_{token}.txt"
    download_file(uploaded.id, dest)
    print(f"   downloaded -> {dest}")
    print(f"   contents: {dest.read_text(encoding='utf-8').strip()!r}")

    print("\n== 6. Share the file with anyone who has the link (reader) ==")
    perm = share_file(uploaded.id, role="reader", anyone=True)
    print(f"   granted {perm.role} to {perm.type}  (permission {perm.id})")
    print("   current permissions:")
    for p in list_permissions(uploaded.id):
        who = p.email_address or p.domain or p.type
        print(f"     {p.role:10} {p.type:8} {who}")

    print("\n== 7. Clean up (delete the folder + its contents) ==")
    delete_file(folder.id)
    local.unlink(missing_ok=True)
    dest.unlink(missing_ok=True)
    print("   deleted.")

    print(f"\nDone. (Demo token: {token})")


if __name__ == "__main__":
    main()
