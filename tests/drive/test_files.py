"""Unit tests for ``mgdio.drive.files``."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from mgdio.drive import files as files_mod
from mgdio.drive.files import FOLDER_MIME_TYPE
from mgdio.exceptions import MgdioAPIError


def _files_call(service):
    return service.files.return_value


def _sample_file_raw(**overrides):
    base = {
        "id": "f-1",
        "name": "report.pdf",
        "mimeType": "application/pdf",
        "parents": ["parent-1"],
        "size": "20480",
        "createdTime": "2026-05-01T10:00:00.000Z",
        "modifiedTime": "2026-05-12T08:30:00.000Z",
        "webViewLink": "https://drive.google.com/file/d/f-1/view",
        "webContentLink": "https://drive.google.com/uc?id=f-1",
        "trashed": False,
        "starred": True,
        "shared": False,
        "md5Checksum": "abc123",
        "fileExtension": "pdf",
        "iconLink": "https://icon",
        "owners": [{"emailAddress": "me@example.com"}],
    }
    base.update(overrides)
    return base


class TestToFile:
    def test_maps_all_fields(self):
        f = files_mod._to_file(_sample_file_raw())
        assert f.id == "f-1"
        assert f.name == "report.pdf"
        assert f.mime_type == "application/pdf"
        assert f.parents == ("parent-1",)
        assert f.size_bytes == 20480
        assert f.created_time.year == 2026
        assert f.modified_time.tzinfo is not None
        assert f.starred is True
        assert f.owner_emails == ("me@example.com",)
        assert f.is_folder is False
        assert f.is_google_native is False

    def test_folder_flags(self):
        f = files_mod._to_file(_sample_file_raw(mimeType=FOLDER_MIME_TYPE, size=None))
        assert f.is_folder is True
        assert f.size_bytes is None

    def test_google_native_flag(self):
        f = files_mod._to_file(
            _sample_file_raw(mimeType="application/vnd.google-apps.document", size=None)
        )
        assert f.is_google_native is True
        assert f.size_bytes is None


class TestListFiles:
    def test_builds_query_with_parent_and_excludes_trash(self, mock_drive_service):
        _files_call(mock_drive_service).list.return_value.execute.return_value = {
            "files": [_sample_file_raw()]
        }
        result = files_mod.list_files(
            query="name contains 'report'", parent_id="folder-9", max_results=10
        )
        assert len(result) == 1
        kwargs = _files_call(mock_drive_service).list.call_args.kwargs
        q = kwargs["q"]
        assert "(name contains 'report')" in q
        assert "'folder-9' in parents" in q
        assert "trashed = false" in q
        assert kwargs["pageSize"] == 10

    def test_include_trashed_omits_trash_clause(self, mock_drive_service):
        _files_call(mock_drive_service).list.return_value.execute.return_value = {
            "files": []
        }
        files_mod.list_files(include_trashed=True)
        kwargs = _files_call(mock_drive_service).list.call_args.kwargs
        # No query clauses at all -> q omitted.
        assert "q" not in kwargs

    def test_auto_paginates_to_max_records(self, mock_drive_service):
        page1 = {
            "files": [_sample_file_raw(id=f"a{i}") for i in range(100)],
            "nextPageToken": "tok",
        }
        page2 = {"files": [_sample_file_raw(id=f"b{i}") for i in range(100)]}
        _files_call(mock_drive_service).list.return_value.execute.side_effect = [
            page1,
            page2,
        ]
        result = files_mod.list_files(max_results=150)
        assert len(result) == 150
        # Second page requested only the remaining 50.
        second_kwargs = _files_call(mock_drive_service).list.call_args_list[1].kwargs
        assert second_kwargs["pageSize"] == 50
        assert second_kwargs["pageToken"] == "tok"

    def test_order_by_passed_through(self, mock_drive_service):
        _files_call(mock_drive_service).list.return_value.execute.return_value = {
            "files": []
        }
        files_mod.list_files(order_by="modifiedTime desc")
        kwargs = _files_call(mock_drive_service).list.call_args.kwargs
        assert kwargs["orderBy"] == "modifiedTime desc"

    def test_wraps_http_error(self, mock_drive_service):
        _files_call(mock_drive_service).list.return_value.execute.side_effect = (
            HttpError(resp=MagicMock(status=500, reason="boom"), content=b"err")
        )
        with pytest.raises(MgdioAPIError):
            files_mod.list_files()


class TestFetchFile:
    def test_happy_path(self, mock_drive_service):
        _files_call(mock_drive_service).get.return_value.execute.return_value = (
            _sample_file_raw()
        )
        f = files_mod.fetch_file("f-1")
        assert f.id == "f-1"
        kwargs = _files_call(mock_drive_service).get.call_args.kwargs
        assert kwargs["fileId"] == "f-1"

    def test_wraps_http_error(self, mock_drive_service):
        _files_call(mock_drive_service).get.return_value.execute.side_effect = (
            HttpError(resp=MagicMock(status=404, reason="nope"), content=b"err")
        )
        with pytest.raises(MgdioAPIError):
            files_mod.fetch_file("f-1")


class TestCreateFolder:
    def test_builds_folder_body(self, mock_drive_service):
        _files_call(mock_drive_service).create.return_value.execute.return_value = (
            _sample_file_raw(mimeType=FOLDER_MIME_TYPE, size=None)
        )
        f = files_mod.create_folder("My Folder", parent_id="root-1")
        assert f.is_folder
        body = _files_call(mock_drive_service).create.call_args.kwargs["body"]
        assert body["name"] == "My Folder"
        assert body["mimeType"] == FOLDER_MIME_TYPE
        assert body["parents"] == ["root-1"]

    def test_root_when_no_parent(self, mock_drive_service):
        _files_call(mock_drive_service).create.return_value.execute.return_value = (
            _sample_file_raw(mimeType=FOLDER_MIME_TYPE)
        )
        files_mod.create_folder("Top")
        body = _files_call(mock_drive_service).create.call_args.kwargs["body"]
        assert "parents" not in body


class TestUploadFile:
    def test_uploads_with_media_body(self, mock_drive_service, tmp_path, monkeypatch):
        local = tmp_path / "data.csv"
        local.write_text("a,b\n1,2\n", encoding="utf-8")
        media_sentinel = object()
        media_ctor = MagicMock(return_value=media_sentinel)
        monkeypatch.setattr(files_mod, "MediaFileUpload", media_ctor)
        _files_call(mock_drive_service).create.return_value.execute.return_value = (
            _sample_file_raw(name="data.csv")
        )

        f = files_mod.upload_file(local, parent_id="dest-1")

        assert f.name == "data.csv"
        media_ctor.assert_called_once()
        kwargs = _files_call(mock_drive_service).create.call_args.kwargs
        assert kwargs["media_body"] is media_sentinel
        assert kwargs["body"]["name"] == "data.csv"
        assert kwargs["body"]["parents"] == ["dest-1"]

    def test_missing_file_raises(self, mock_drive_service, tmp_path):
        with pytest.raises(FileNotFoundError):
            files_mod.upload_file(tmp_path / "nope.txt")


class TestDownloadAndExport:
    def test_download_writes_file(self, mock_drive_service, tmp_path, monkeypatch):
        dest = tmp_path / "out.bin"

        class FakeDownloader:
            def __init__(self, fh, request):
                self._fh = fh
                self._done = False

            def next_chunk(self):
                if not self._done:
                    self._fh.write(b"hello bytes")
                    self._done = True
                return (None, True)

        monkeypatch.setattr(files_mod, "MediaIoBaseDownload", FakeDownloader)
        _files_call(mock_drive_service).get_media.return_value = MagicMock()

        out = files_mod.download_file("f-1", dest)
        assert out == dest
        assert dest.read_bytes() == b"hello bytes"

    def test_export_writes_file(self, mock_drive_service, tmp_path, monkeypatch):
        dest = tmp_path / "doc.pdf"

        class FakeDownloader:
            def __init__(self, buffer, request):
                self._buffer = buffer
                self._done = False

            def next_chunk(self):
                if not self._done:
                    self._buffer.write(b"%PDF-fake")
                    self._done = True
                return (None, True)

        monkeypatch.setattr(files_mod, "MediaIoBaseDownload", FakeDownloader)
        _files_call(mock_drive_service).export_media.return_value = MagicMock()

        out = files_mod.export_file("doc-1", dest, mime_type="application/pdf")
        assert out == dest
        assert dest.read_bytes() == b"%PDF-fake"
        kwargs = _files_call(mock_drive_service).export_media.call_args.kwargs
        assert kwargs["mimeType"] == "application/pdf"

    def test_download_wraps_http_error(self, mock_drive_service, tmp_path):
        _files_call(mock_drive_service).get_media.side_effect = HttpError(
            resp=MagicMock(status=403, reason="no"), content=b"err"
        )
        with pytest.raises(MgdioAPIError):
            files_mod.download_file("f-1", tmp_path / "x")


class TestUpdateFile:
    def test_metadata_only(self, mock_drive_service):
        _files_call(mock_drive_service).update.return_value.execute.return_value = (
            _sample_file_raw(name="renamed.pdf")
        )
        f = files_mod.update_file("f-1", name="renamed.pdf", starred=False)
        assert f.name == "renamed.pdf"
        kwargs = _files_call(mock_drive_service).update.call_args.kwargs
        assert kwargs["body"] == {"name": "renamed.pdf", "starred": False}
        assert kwargs["media_body"] is None


class TestMoveFile:
    def test_adds_and_removes_parents(self, mock_drive_service):
        # First get() returns current parents, then update() returns moved file.
        _files_call(mock_drive_service).get.return_value.execute.return_value = {
            "parents": ["old-1", "old-2"]
        }
        _files_call(mock_drive_service).update.return_value.execute.return_value = (
            _sample_file_raw(parents=["new-1"])
        )
        f = files_mod.move_file("f-1", "new-1")
        assert f.parents == ("new-1",)
        kwargs = _files_call(mock_drive_service).update.call_args.kwargs
        assert kwargs["addParents"] == "new-1"
        assert kwargs["removeParents"] == "old-1,old-2"

    def test_keep_existing_parents(self, mock_drive_service):
        _files_call(mock_drive_service).update.return_value.execute.return_value = (
            _sample_file_raw()
        )
        files_mod.move_file("f-1", "new-1", remove_existing_parents=False)
        kwargs = _files_call(mock_drive_service).update.call_args.kwargs
        assert "removeParents" not in kwargs
        # get() should not be called when not removing parents.
        _files_call(mock_drive_service).get.assert_not_called()


class TestCopyTrashDelete:
    def test_copy_sends_name_and_parent(self, mock_drive_service):
        _files_call(mock_drive_service).copy.return_value.execute.return_value = (
            _sample_file_raw(id="copy-1")
        )
        f = files_mod.copy_file("f-1", name="dup", parent_id="dest")
        assert f.id == "copy-1"
        body = _files_call(mock_drive_service).copy.call_args.kwargs["body"]
        assert body == {"name": "dup", "parents": ["dest"]}

    def test_trash_sets_trashed_true(self, mock_drive_service):
        _files_call(mock_drive_service).update.return_value.execute.return_value = (
            _sample_file_raw(trashed=True)
        )
        files_mod.trash_file("f-1")
        body = _files_call(mock_drive_service).update.call_args.kwargs["body"]
        assert body == {"trashed": True}

    def test_restore_sets_trashed_false(self, mock_drive_service):
        _files_call(mock_drive_service).update.return_value.execute.return_value = (
            _sample_file_raw(trashed=False)
        )
        files_mod.trash_file("f-1", trashed=False)
        body = _files_call(mock_drive_service).update.call_args.kwargs["body"]
        assert body == {"trashed": False}

    def test_delete_calls_delete(self, mock_drive_service):
        _files_call(mock_drive_service).delete.return_value.execute.return_value = ""
        files_mod.delete_file("f-1")
        kwargs = _files_call(mock_drive_service).delete.call_args.kwargs
        assert kwargs["fileId"] == "f-1"

    def test_delete_wraps_http_error(self, mock_drive_service):
        _files_call(mock_drive_service).delete.return_value.execute.side_effect = (
            HttpError(resp=MagicMock(status=500, reason="boom"), content=b"err")
        )
        with pytest.raises(MgdioAPIError):
            files_mod.delete_file("f-1")

    def test_empty_trash(self, mock_drive_service):
        _files_call(mock_drive_service).emptyTrash.return_value.execute.return_value = (
            ""
        )
        files_mod.empty_trash()
        _files_call(mock_drive_service).emptyTrash.assert_called_once()
