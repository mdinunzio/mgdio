"""Drive v3 ``permissions`` resource: list / grant / update / revoke sharing."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from googleapiclient.errors import HttpError

from mgdio.drive.client import get_service
from mgdio.exceptions import MgdioAPIError

logger = logging.getLogger(__name__)

_PERMISSION_FIELDS = "id, type, role, emailAddress, domain, displayName"
_LIST_FIELDS = f"permissions({_PERMISSION_FIELDS})"


@dataclass(frozen=True, slots=True)
class Permission:
    """A sharing permission on a Drive file.

    Attributes:
        id: Permission id (use with ``unshare_file`` / ``update_permission``).
        type: ``"user" | "group" | "domain" | "anyone"``.
        role: ``"owner" | "organizer" | "fileOrganizer" | "writer" |
            "commenter" | "reader"``.
        email_address: Grantee email (for ``user`` / ``group``), or empty.
        domain: Grantee domain (for ``domain`` type), or empty.
        display_name: Human-readable name, or empty.
    """

    id: str
    type: str
    role: str
    email_address: str
    domain: str
    display_name: str


def list_permissions(file_id: str) -> list[Permission]:
    """List all sharing permissions on a file.

    Args:
        file_id: Drive file id.

    Returns:
        List of :class:`Permission`.

    Raises:
        MgdioAPIError: On any Drive API error.
    """
    service = get_service()
    try:
        resp = service.permissions().list(fileId=file_id, fields=_LIST_FIELDS).execute()
    except HttpError as exc:
        raise MgdioAPIError(f"Drive permissions.list {file_id} failed: {exc}") from exc
    return [_to_permission(item) for item in resp.get("permissions", [])]


def share_file(
    file_id: str,
    *,
    role: str = "reader",
    email: str | None = None,
    domain: str | None = None,
    anyone: bool = False,
    send_notification: bool = False,
) -> Permission:
    """Grant a sharing permission on a file.

    Exactly one grantee must be specified: ``email`` (a person/group),
    ``domain`` (everyone in a Google Workspace domain), or ``anyone=True``
    (anyone with the link).

    Args:
        file_id: Drive file id.
        role: ``"reader" | "commenter" | "writer" | "owner" |
            "organizer" | "fileOrganizer"``. Default ``"reader"``.
        email: Grantee email for a user/group share.
        domain: Grantee domain for a domain share.
        anyone: If True, share with anyone who has the link.
        send_notification: Email the grantee (only valid for user/group).

    Returns:
        The created :class:`Permission`.

    Raises:
        MgdioAPIError: On any Drive API error.
        ValueError: If not exactly one grantee is specified.
    """
    targets = [bool(email), bool(domain), anyone]
    if sum(targets) != 1:
        raise ValueError("Specify exactly one of email=, domain=, or anyone=True.")

    body: dict[str, Any] = {"role": role}
    if email:
        body["type"] = "user"
        body["emailAddress"] = email
    elif domain:
        body["type"] = "domain"
        body["domain"] = domain
    else:
        body["type"] = "anyone"

    service = get_service()
    try:
        raw = (
            service.permissions()
            .create(
                fileId=file_id,
                body=body,
                sendNotificationEmail=send_notification,
                fields=_PERMISSION_FIELDS,
            )
            .execute()
        )
    except HttpError as exc:
        raise MgdioAPIError(
            f"Drive permissions.create {file_id} failed: {exc}"
        ) from exc
    return _to_permission(raw)


def update_permission(
    file_id: str,
    permission_id: str,
    *,
    role: str,
) -> Permission:
    """Change the role of an existing permission.

    Args:
        file_id: Drive file id.
        permission_id: The permission to change (from ``list_permissions``).
        role: New role.

    Returns:
        The updated :class:`Permission`.

    Raises:
        MgdioAPIError: On any Drive API error.
    """
    service = get_service()
    try:
        raw = (
            service.permissions()
            .update(
                fileId=file_id,
                permissionId=permission_id,
                body={"role": role},
                fields=_PERMISSION_FIELDS,
            )
            .execute()
        )
    except HttpError as exc:
        raise MgdioAPIError(
            f"Drive permissions.update {file_id}/{permission_id} failed: {exc}"
        ) from exc
    return _to_permission(raw)


def unshare_file(file_id: str, permission_id: str) -> None:
    """Revoke a sharing permission.

    Args:
        file_id: Drive file id.
        permission_id: The permission to delete (from ``list_permissions``).

    Raises:
        MgdioAPIError: On any Drive API error.
    """
    service = get_service()
    try:
        service.permissions().delete(
            fileId=file_id, permissionId=permission_id
        ).execute()
    except HttpError as exc:
        raise MgdioAPIError(
            f"Drive permissions.delete {file_id}/{permission_id} failed: {exc}"
        ) from exc


def _to_permission(raw: dict) -> Permission:
    return Permission(
        id=raw.get("id", ""),
        type=raw.get("type", ""),
        role=raw.get("role", ""),
        email_address=raw.get("emailAddress", ""),
        domain=raw.get("domain", ""),
        display_name=raw.get("displayName", ""),
    )
