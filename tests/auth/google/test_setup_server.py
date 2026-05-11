"""Unit tests for ``mgdio.auth.google._setup_server``."""

from __future__ import annotations

from mgdio.auth.google import _setup_server


class TestRenderPage:
    def test_includes_target_path(self, tmp_path):
        target = tmp_path / "client_secret.json"
        page = _setup_server._render_page(target)
        assert str(target) in page

    def test_mentions_all_three_services(self, tmp_path):
        page = _setup_server._render_page(tmp_path / "x.json")
        assert "Gmail" in page
        assert "Calendar" in page
        assert "Sheets" in page

    def test_lists_three_scopes(self, tmp_path):
        page = _setup_server._render_page(tmp_path / "x.json")
        assert "https://www.googleapis.com/auth/gmail.modify" in page
        assert "https://www.googleapis.com/auth/calendar" in page
        assert "https://www.googleapis.com/auth/spreadsheets" in page

    def test_includes_drag_and_drop_slot(self, tmp_path):
        page = _setup_server._render_page(tmp_path / "x.json")
        assert "Drag &amp; drop" in page


class TestLooksLikeClientSecret:
    def test_accepts_installed_client_secret(self):
        assert _setup_server._looks_like_client_secret(
            {"installed": {"client_id": "x", "client_secret": "y"}}
        )

    def test_accepts_web_client_secret(self):
        assert _setup_server._looks_like_client_secret(
            {"web": {"client_id": "x", "client_secret": "y"}}
        )

    def test_rejects_empty_dict(self):
        assert not _setup_server._looks_like_client_secret({})

    def test_rejects_section_missing_client_secret(self):
        assert not _setup_server._looks_like_client_secret(
            {"installed": {"client_id": "x"}}
        )

    def test_rejects_non_dict_inputs(self):
        assert not _setup_server._looks_like_client_secret("not a dict")
        assert not _setup_server._looks_like_client_secret(
            {"installed": "string-not-dict"}
        )
