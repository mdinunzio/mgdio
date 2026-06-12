"""Unit tests for ``mgdio.drive.permissions``."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from mgdio.drive import permissions as perms_mod
from mgdio.exceptions import MgdioAPIError


def _perms_call(service):
    return service.permissions.return_value


def _sample_perm(**overrides):
    base = {
        "id": "perm-1",
        "type": "user",
        "role": "reader",
        "emailAddress": "alice@example.com",
        "domain": "",
        "displayName": "Alice",
    }
    base.update(overrides)
    return base


class TestListPermissions:
    def test_maps_permissions(self, mock_drive_service):
        _perms_call(mock_drive_service).list.return_value.execute.return_value = {
            "permissions": [
                _sample_perm(),
                _sample_perm(
                    id="perm-2", type="anyone", emailAddress="", role="writer"
                ),
            ]
        }
        result = perms_mod.list_permissions("f-1")
        assert [p.id for p in result] == ["perm-1", "perm-2"]
        assert result[0].email_address == "alice@example.com"
        assert result[1].type == "anyone"

    def test_wraps_http_error(self, mock_drive_service):
        _perms_call(mock_drive_service).list.return_value.execute.side_effect = (
            HttpError(resp=MagicMock(status=500, reason="boom"), content=b"err")
        )
        with pytest.raises(MgdioAPIError):
            perms_mod.list_permissions("f-1")


class TestShareFile:
    def test_user_share(self, mock_drive_service):
        _perms_call(mock_drive_service).create.return_value.execute.return_value = (
            _sample_perm()
        )
        p = perms_mod.share_file("f-1", role="writer", email="bob@example.com")
        assert p.id == "perm-1"
        kwargs = _perms_call(mock_drive_service).create.call_args.kwargs
        assert kwargs["body"] == {
            "role": "writer",
            "type": "user",
            "emailAddress": "bob@example.com",
        }
        assert kwargs["sendNotificationEmail"] is False

    def test_anyone_share(self, mock_drive_service):
        _perms_call(mock_drive_service).create.return_value.execute.return_value = (
            _sample_perm(type="anyone", emailAddress="")
        )
        perms_mod.share_file("f-1", anyone=True)
        body = _perms_call(mock_drive_service).create.call_args.kwargs["body"]
        assert body["type"] == "anyone"
        assert "emailAddress" not in body

    def test_domain_share(self, mock_drive_service):
        _perms_call(mock_drive_service).create.return_value.execute.return_value = (
            _sample_perm(type="domain", emailAddress="", domain="example.com")
        )
        perms_mod.share_file("f-1", domain="example.com")
        body = _perms_call(mock_drive_service).create.call_args.kwargs["body"]
        assert body["type"] == "domain"
        assert body["domain"] == "example.com"

    def test_no_target_raises(self, mock_drive_service):
        with pytest.raises(ValueError, match="exactly one"):
            perms_mod.share_file("f-1")

    def test_multiple_targets_raises(self, mock_drive_service):
        with pytest.raises(ValueError, match="exactly one"):
            perms_mod.share_file("f-1", email="a@b.c", anyone=True)

    def test_wraps_http_error(self, mock_drive_service):
        _perms_call(mock_drive_service).create.return_value.execute.side_effect = (
            HttpError(resp=MagicMock(status=403, reason="no"), content=b"err")
        )
        with pytest.raises(MgdioAPIError):
            perms_mod.share_file("f-1", email="a@b.c")


class TestUpdateAndUnshare:
    def test_update_role(self, mock_drive_service):
        _perms_call(mock_drive_service).update.return_value.execute.return_value = (
            _sample_perm(role="writer")
        )
        p = perms_mod.update_permission("f-1", "perm-1", role="writer")
        assert p.role == "writer"
        kwargs = _perms_call(mock_drive_service).update.call_args.kwargs
        assert kwargs["body"] == {"role": "writer"}
        assert kwargs["permissionId"] == "perm-1"

    def test_unshare_calls_delete(self, mock_drive_service):
        _perms_call(mock_drive_service).delete.return_value.execute.return_value = ""
        perms_mod.unshare_file("f-1", "perm-1")
        kwargs = _perms_call(mock_drive_service).delete.call_args.kwargs
        assert kwargs == {"fileId": "f-1", "permissionId": "perm-1"}

    def test_unshare_wraps_http_error(self, mock_drive_service):
        _perms_call(mock_drive_service).delete.return_value.execute.side_effect = (
            HttpError(resp=MagicMock(status=404, reason="no"), content=b"err")
        )
        with pytest.raises(MgdioAPIError):
            perms_mod.unshare_file("f-1", "perm-1")
