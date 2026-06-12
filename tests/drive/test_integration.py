"""Opt-in integration tests that hit the real Drive API.

Skipped unless ``MGDIO_RUN_INTEGRATION=1``. Creates a throwaway folder,
uploads a small file into it, lists it, downloads it back, then deletes
both. Requires a completed ``mgdio auth google`` (with the drive scope).
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.integration

if os.getenv("MGDIO_RUN_INTEGRATION") != "1":
    pytest.skip(
        "MGDIO_RUN_INTEGRATION!=1; skipping real-API tests",
        allow_module_level=True,
    )


def test_full_cycle(tmp_path):
    from mgdio.drive import (
        create_folder,
        delete_file,
        download_file,
        fetch_file,
        list_files,
        upload_file,
    )

    token = uuid.uuid4().hex[:8]
    folder = create_folder(f"mgdio-itest-{token}")
    assert folder.is_folder

    src = tmp_path / "hello.txt"
    src.write_text(f"mgdio drive integration {token}\n", encoding="utf-8")
    uploaded = upload_file(src, parent_id=folder.id)
    assert uploaded.name == "hello.txt"

    # The uploaded file shows up listing the folder's children.
    children = list_files(parent_id=folder.id, max_results=10)
    assert any(c.id == uploaded.id for c in children)

    # Round-trip the content.
    fetched = fetch_file(uploaded.id)
    assert fetched.id == uploaded.id
    dest = tmp_path / "roundtrip.txt"
    download_file(uploaded.id, dest)
    assert token in dest.read_text(encoding="utf-8")

    # Clean up (permanent delete; folder delete removes its contents).
    delete_file(folder.id)
