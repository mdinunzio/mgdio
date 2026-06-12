"""Drive v3 file + folder operations.

Covers the full ``files`` resource surface: list/search, get metadata,
create folders, upload, download (binary) / export (Google-native),
update metadata, move (re-parent), copy, trash/untrash, delete, and
empty-trash.

Google-native files (Docs/Sheets/Slides -- mime type
``application/vnd.google-apps.*``) have no downloadable bytes; use
:func:`export_file` with a target mime type instead of
:func:`download_file`.
"""

from __future__ import annotations

import io
import logging
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from mgdio.drive.client import get_service
from mgdio.exceptions import MgdioAPIError

logger = logging.getLogger(__name__)

FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
_GOOGLE_NATIVE_PREFIX = "application/vnd.google-apps."
_MAX_PAGE_SIZE = 100

# Fields requested for each file. Keep in sync with DriveFile + _to_file.
_FILE_FIELDS = (
    "id, name, mimeType, parents, size, createdTime, modifiedTime, "
    "webViewLink, webContentLink, trashed, starred, shared, "
    "md5Checksum, fileExtension, iconLink, owners(emailAddress)"
)
_LIST_FIELDS = f"nextPageToken, files({_FILE_FIELDS})"


@dataclass(frozen=True, slots=True)
class DriveFile:
    """A Drive file or folder.

    Attributes:
        id: Drive file id.
        name: File / folder name.
        mime_type: MIME type. Folders are ``FOLDER_MIME_TYPE``; Google
            native docs start with ``application/vnd.google-apps.``.
        parents: Tuple of parent folder ids.
        size_bytes: Size in bytes (``None`` for folders / native docs).
        created_time: Creation time (tz-aware) or ``None``.
        modified_time: Last-modified time (tz-aware) or ``None``.
        web_view_link: Browser link to open the file, or empty string.
        web_content_link: Direct download link (binary files), or empty.
        trashed: Whether the file is in the trash.
        starred: Whether the user starred the file.
        shared: Whether the file has been shared.
        md5_checksum: MD5 of binary content, or empty string.
        file_extension: Extension component (binary files), or empty.
        icon_link: Static icon URL, or empty string.
        owner_emails: Tuple of owner email addresses.
    """

    id: str
    name: str
    mime_type: str
    parents: tuple[str, ...]
    size_bytes: int | None
    created_time: datetime | None
    modified_time: datetime | None
    web_view_link: str
    web_content_link: str
    trashed: bool
    starred: bool
    shared: bool
    md5_checksum: str
    file_extension: str
    icon_link: str
    owner_emails: tuple[str, ...]

    @property
    def is_folder(self) -> bool:
        """True if this entry is a folder."""
        return self.mime_type == FOLDER_MIME_TYPE

    @property
    def is_google_native(self) -> bool:
        """True for Google Docs/Sheets/Slides (export-only, no raw bytes)."""
        return self.mime_type.startswith(_GOOGLE_NATIVE_PREFIX)


def list_files(
    *,
    query: str = "",
    parent_id: str | None = None,
    include_trashed: bool = False,
    order_by: str | None = None,
    max_results: int = 100,
) -> list[DriveFile]:
    """List / search files, auto-paginating up to ``max_results``.

    Args:
        query: Raw Drive query string (the ``q`` parameter), e.g.
            ``"name contains 'report'"`` or ``"mimeType='application/pdf'"``.
            Combined (AND) with the ``parent_id`` / ``include_trashed``
            filters below.
        parent_id: Restrict to direct children of this folder id.
        include_trashed: Include trashed files (default excludes them).
        order_by: Sort key, e.g. ``"modifiedTime desc"`` or ``"name"``.
        max_results: Max files to return.

    Returns:
        List of :class:`DriveFile`.

    Raises:
        MgdioAPIError: On any Drive API error.
    """
    clauses: list[str] = []
    if query:
        clauses.append(f"({query})")
    if parent_id:
        clauses.append(f"'{parent_id}' in parents")
    if not include_trashed:
        clauses.append("trashed = false")
    q = " and ".join(clauses) if clauses else None

    service = get_service()
    out: list[DriveFile] = []
    page_token: str | None = None
    try:
        while len(out) < max_results:
            params: dict[str, Any] = {
                "pageSize": min(_MAX_PAGE_SIZE, max_results - len(out)),
                "fields": _LIST_FIELDS,
                "spaces": "drive",
            }
            if q:
                params["q"] = q
            if order_by:
                params["orderBy"] = order_by
            if page_token:
                params["pageToken"] = page_token
            resp = service.files().list(**params).execute()
            out.extend(_to_file(item) for item in resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
    except HttpError as exc:
        raise MgdioAPIError(f"Drive files.list failed: {exc}") from exc
    return out[:max_results]


def fetch_file(file_id: str) -> DriveFile:
    """Fetch a single file's metadata.

    Args:
        file_id: Drive file id.

    Returns:
        A populated :class:`DriveFile`.

    Raises:
        MgdioAPIError: On any Drive API error.
    """
    service = get_service()
    try:
        raw = service.files().get(fileId=file_id, fields=_FILE_FIELDS).execute()
    except HttpError as exc:
        raise MgdioAPIError(f"Drive files.get {file_id} failed: {exc}") from exc
    return _to_file(raw)


def create_folder(
    name: str,
    *,
    parent_id: str | None = None,
) -> DriveFile:
    """Create a folder.

    Args:
        name: Folder name.
        parent_id: Parent folder id; defaults to "My Drive" root.

    Returns:
        The created folder as a :class:`DriveFile`.

    Raises:
        MgdioAPIError: On any Drive API error.
    """
    body: dict[str, Any] = {"name": name, "mimeType": FOLDER_MIME_TYPE}
    if parent_id:
        body["parents"] = [parent_id]
    service = get_service()
    try:
        raw = service.files().create(body=body, fields=_FILE_FIELDS).execute()
    except HttpError as exc:
        raise MgdioAPIError(f"Drive create_folder failed: {exc}") from exc
    return _to_file(raw)


def upload_file(
    local_path: str | Path,
    *,
    name: str | None = None,
    parent_id: str | None = None,
    mime_type: str | None = None,
) -> DriveFile:
    """Upload a local file to Drive.

    Args:
        local_path: Path to the file on disk.
        name: Name to give the Drive file; defaults to the local name.
        parent_id: Parent folder id; defaults to "My Drive" root.
        mime_type: Content type; guessed from the extension if omitted.

    Returns:
        The created file as a :class:`DriveFile`.

    Raises:
        MgdioAPIError: On any Drive API error.
        FileNotFoundError: If ``local_path`` does not exist.
    """
    path = Path(local_path)
    if not path.is_file():
        raise FileNotFoundError(f"No such file: {path}")
    if mime_type is None:
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    body: dict[str, Any] = {"name": name or path.name}
    if parent_id:
        body["parents"] = [parent_id]
    media = MediaFileUpload(str(path), mimetype=mime_type, resumable=True)

    service = get_service()
    try:
        raw = (
            service.files()
            .create(body=body, media_body=media, fields=_FILE_FIELDS)
            .execute()
        )
    except HttpError as exc:
        raise MgdioAPIError(f"Drive upload {path.name} failed: {exc}") from exc
    return _to_file(raw)


def download_file(file_id: str, local_path: str | Path) -> Path:
    """Download a binary file's content to a local path.

    For Google-native docs (Docs/Sheets/Slides), use :func:`export_file`
    instead -- they have no directly downloadable bytes.

    Args:
        file_id: Drive file id.
        local_path: Destination path on disk.

    Returns:
        The destination :class:`~pathlib.Path`.

    Raises:
        MgdioAPIError: On any Drive API error.
    """
    dest = Path(local_path)
    service = get_service()
    try:
        request = service.files().get_media(fileId=file_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _status, done = downloader.next_chunk()
    except HttpError as exc:
        raise MgdioAPIError(f"Drive download {file_id} failed: {exc}") from exc
    return dest


def export_file(
    file_id: str,
    local_path: str | Path,
    *,
    mime_type: str,
) -> Path:
    """Export a Google-native doc to ``mime_type`` and save it locally.

    Examples of ``mime_type``: ``"application/pdf"``,
    ``"text/csv"`` (Sheets), ``"text/plain"`` (Docs),
    ``"application/vnd.openxmlformats-officedocument.wordprocessingml.document"``
    (Docs -> .docx).

    Args:
        file_id: Drive file id (must be a Google-native doc).
        local_path: Destination path on disk.
        mime_type: Export target MIME type.

    Returns:
        The destination :class:`~pathlib.Path`.

    Raises:
        MgdioAPIError: On any Drive API error.
    """
    dest = Path(local_path)
    service = get_service()
    try:
        request = service.files().export_media(fileId=file_id, mimeType=mime_type)
        dest.parent.mkdir(parents=True, exist_ok=True)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _status, done = downloader.next_chunk()
        dest.write_bytes(buffer.getvalue())
    except HttpError as exc:
        raise MgdioAPIError(
            f"Drive export {file_id} as {mime_type!r} failed: {exc}"
        ) from exc
    return dest


def update_file(
    file_id: str,
    *,
    name: str | None = None,
    starred: bool | None = None,
    local_path: str | Path | None = None,
    mime_type: str | None = None,
) -> DriveFile:
    """Update a file's metadata and/or replace its content.

    Args:
        file_id: Drive file id.
        name: New name (``None`` leaves it unchanged).
        starred: New starred state (``None`` leaves it unchanged).
        local_path: If given, replace the file's content with this file.
        mime_type: Content type for ``local_path``; guessed if omitted.

    Returns:
        The updated :class:`DriveFile`.

    Raises:
        MgdioAPIError: On any Drive API error.
    """
    body: dict[str, Any] = {}
    if name is not None:
        body["name"] = name
    if starred is not None:
        body["starred"] = starred

    media = None
    if local_path is not None:
        path = Path(local_path)
        if not path.is_file():
            raise FileNotFoundError(f"No such file: {path}")
        guessed = mime_type or mimetypes.guess_type(path.name)[0]
        media = MediaFileUpload(
            str(path), mimetype=guessed or "application/octet-stream", resumable=True
        )

    service = get_service()
    try:
        raw = (
            service.files()
            .update(
                fileId=file_id,
                body=body,
                media_body=media,
                fields=_FILE_FIELDS,
            )
            .execute()
        )
    except HttpError as exc:
        raise MgdioAPIError(f"Drive update {file_id} failed: {exc}") from exc
    return _to_file(raw)


def move_file(
    file_id: str,
    new_parent_id: str,
    *,
    remove_existing_parents: bool = True,
) -> DriveFile:
    """Move a file into ``new_parent_id``.

    Args:
        file_id: Drive file id.
        new_parent_id: Destination folder id.
        remove_existing_parents: If True (default), detach the file from
            its current parents (a true move). If False, the file ends up
            in multiple folders (Drive allows multi-parenting).

    Returns:
        The updated :class:`DriveFile`.

    Raises:
        MgdioAPIError: On any Drive API error.
    """
    service = get_service()
    try:
        kwargs: dict[str, Any] = {
            "fileId": file_id,
            "addParents": new_parent_id,
            "body": {},
            "fields": _FILE_FIELDS,
        }
        if remove_existing_parents:
            current = service.files().get(fileId=file_id, fields="parents").execute()
            old = current.get("parents", [])
            if old:
                kwargs["removeParents"] = ",".join(old)
        raw = service.files().update(**kwargs).execute()
    except HttpError as exc:
        raise MgdioAPIError(f"Drive move {file_id} failed: {exc}") from exc
    return _to_file(raw)


def copy_file(
    file_id: str,
    *,
    name: str | None = None,
    parent_id: str | None = None,
) -> DriveFile:
    """Copy a file.

    Args:
        file_id: Source file id.
        name: Name for the copy; defaults to "Copy of <original>".
        parent_id: Destination folder id; defaults to the source's folder.

    Returns:
        The new copy as a :class:`DriveFile`.

    Raises:
        MgdioAPIError: On any Drive API error.
    """
    body: dict[str, Any] = {}
    if name is not None:
        body["name"] = name
    if parent_id is not None:
        body["parents"] = [parent_id]
    service = get_service()
    try:
        raw = (
            service.files()
            .copy(fileId=file_id, body=body, fields=_FILE_FIELDS)
            .execute()
        )
    except HttpError as exc:
        raise MgdioAPIError(f"Drive copy {file_id} failed: {exc}") from exc
    return _to_file(raw)


def trash_file(file_id: str, *, trashed: bool = True) -> DriveFile:
    """Move a file to the trash (or restore it with ``trashed=False``).

    Args:
        file_id: Drive file id.
        trashed: ``True`` to trash, ``False`` to restore.

    Returns:
        The updated :class:`DriveFile`.

    Raises:
        MgdioAPIError: On any Drive API error.
    """
    service = get_service()
    try:
        raw = (
            service.files()
            .update(fileId=file_id, body={"trashed": trashed}, fields=_FILE_FIELDS)
            .execute()
        )
    except HttpError as exc:
        raise MgdioAPIError(f"Drive trash {file_id} failed: {exc}") from exc
    return _to_file(raw)


def delete_file(file_id: str) -> None:
    """Permanently delete a file (skips the trash -- irreversible).

    Args:
        file_id: Drive file id.

    Raises:
        MgdioAPIError: On any Drive API error.
    """
    service = get_service()
    try:
        service.files().delete(fileId=file_id).execute()
    except HttpError as exc:
        raise MgdioAPIError(f"Drive delete {file_id} failed: {exc}") from exc


def empty_trash() -> None:
    """Permanently delete every trashed file (irreversible).

    Raises:
        MgdioAPIError: On any Drive API error.
    """
    service = get_service()
    try:
        service.files().emptyTrash().execute()
    except HttpError as exc:
        raise MgdioAPIError(f"Drive emptyTrash failed: {exc}") from exc


def _to_file(raw: dict) -> DriveFile:
    size = raw.get("size")
    owners = tuple(
        o.get("emailAddress", "")
        for o in (raw.get("owners") or [])
        if o.get("emailAddress")
    )
    return DriveFile(
        id=raw.get("id", ""),
        name=raw.get("name", ""),
        mime_type=raw.get("mimeType", ""),
        parents=tuple(raw.get("parents", []) or []),
        size_bytes=int(size) if size is not None else None,
        created_time=_parse_rfc3339(raw.get("createdTime")),
        modified_time=_parse_rfc3339(raw.get("modifiedTime")),
        web_view_link=raw.get("webViewLink", ""),
        web_content_link=raw.get("webContentLink", ""),
        trashed=bool(raw.get("trashed", False)),
        starred=bool(raw.get("starred", False)),
        shared=bool(raw.get("shared", False)),
        md5_checksum=raw.get("md5Checksum", ""),
        file_extension=raw.get("fileExtension", ""),
        icon_link=raw.get("iconLink", ""),
        owner_emails=owners,
    )


def _parse_rfc3339(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _build_name_query(names: Sequence[str]) -> str:
    """Helper: OR-join name-equality clauses (used by tests / callers)."""
    return " or ".join(f"name = '{n}'" for n in names)
