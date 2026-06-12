"""Google Drive subpackage public API.

Built on top of :mod:`mgdio.auth.google` -- the unified Google OAuth flow
provides the credentials; this subpackage wraps the Drive v3 API with
typed dataclasses.

Full file/folder surface (list/search, get, create folders, upload,
download/export, update, move, copy, trash, delete, empty-trash) plus
sharing (list/grant/update/revoke permissions).
"""

from __future__ import annotations

from mgdio.drive.client import get_service, reset_service_cache
from mgdio.drive.files import (
    FOLDER_MIME_TYPE,
    DriveFile,
    copy_file,
    create_folder,
    delete_file,
    download_file,
    empty_trash,
    export_file,
    fetch_file,
    list_files,
    move_file,
    trash_file,
    update_file,
    upload_file,
)
from mgdio.drive.permissions import (
    Permission,
    list_permissions,
    share_file,
    unshare_file,
    update_permission,
)

__all__ = [
    "FOLDER_MIME_TYPE",
    "DriveFile",
    "Permission",
    "copy_file",
    "create_folder",
    "delete_file",
    "download_file",
    "empty_trash",
    "export_file",
    "fetch_file",
    "get_service",
    "list_files",
    "list_permissions",
    "move_file",
    "reset_service_cache",
    "share_file",
    "trash_file",
    "unshare_file",
    "update_file",
    "update_permission",
    "upload_file",
]
