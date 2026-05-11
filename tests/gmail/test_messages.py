"""Unit tests for ``mgdio.gmail.messages``."""

from __future__ import annotations

import base64
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from mgdio.exceptions import MgdioAPIError
from mgdio.gmail import messages


def _b64(text: bytes) -> str:
    return base64.urlsafe_b64encode(text).decode("ascii").rstrip("=")


def _list_call(mock_service):
    return mock_service.users.return_value.messages.return_value.list.return_value


def _get_call(mock_service):
    return mock_service.users.return_value.messages.return_value.get.return_value


class TestParsePayload:
    def test_multipart_alternative_extracts_text_and_html(self):
        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64(b"plain")}},
                {"mimeType": "text/html", "body": {"data": _b64(b"<b>html</b>")}},
            ],
        }
        text, html = messages._parse_payload(payload)
        assert text == "plain"
        assert html == "<b>html</b>"

    def test_plain_text_only_returns_none_for_html(self):
        payload = {
            "mimeType": "text/plain",
            "body": {"data": _b64(b"only text")},
        }
        text, html = messages._parse_payload(payload)
        assert text == "only text"
        assert html is None

    def test_multipart_mixed_with_attachment_picks_inline_text(self):
        payload = {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {"mimeType": "text/plain", "body": {"data": _b64(b"hello")}},
                        {
                            "mimeType": "text/html",
                            "body": {"data": _b64(b"<i>hi</i>")},
                        },
                    ],
                },
                {
                    "mimeType": "application/pdf",
                    "filename": "report.pdf",
                    "body": {"attachmentId": "att-1", "size": 1024},
                },
            ],
        }
        text, html = messages._parse_payload(payload)
        assert text == "hello"
        assert html == "<i>hi</i>"


class TestFetchMessage:
    def test_happy_path(self, mock_gmail_service, sample_message_payload):
        _get_call(mock_gmail_service).execute.return_value = sample_message_payload

        msg = messages.fetch_message("msg-1")

        assert msg.id == "msg-1"
        assert msg.thread_id == "thread-1"
        assert msg.subject == "Greetings"
        assert msg.sender == "Alice <alice@example.com>"
        assert msg.to == ("bob@example.com", "c@example.com")
        assert msg.cc == ("d@example.com",)
        assert msg.body_text == "hello plain world"
        assert msg.body_html == "<p>hello <b>html</b> world</p>"
        assert msg.label_ids == ("INBOX", "UNREAD")
        assert msg.date.year == 2023  # 1700000000 -> 2023-11-14 UTC

    def test_http_error_wrapped(self, mock_gmail_service):
        _get_call(mock_gmail_service).execute.side_effect = HttpError(
            resp=MagicMock(status=500, reason="boom"), content=b"err"
        )
        with pytest.raises(MgdioAPIError):
            messages.fetch_message("msg-1")


class TestFetchMessages:
    def test_empty_listing_returns_empty(self, mock_gmail_service):
        _list_call(mock_gmail_service).execute.return_value = {}
        assert messages.fetch_messages() == []

    def test_batch_get_returns_messages_in_listed_order(
        self, mock_gmail_service, sample_message_payload
    ):
        _list_call(mock_gmail_service).execute.return_value = {
            "messages": [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        }

        responses_by_id = {}
        for mid in ("a", "b", "c"):
            payload = dict(sample_message_payload)
            payload["id"] = mid
            payload["snippet"] = f"snippet {mid}"
            responses_by_id[mid] = payload

        class FakeBatch:
            def __init__(self, callback):
                self._callback = callback
                self._items: list[tuple[str, object]] = []

            def add(self, request, request_id):
                self._items.append((request_id, request))

            def execute(self):
                for request_id, _request in self._items:
                    self._callback(request_id, responses_by_id[request_id], None)

        mock_gmail_service.new_batch_http_request.side_effect = (
            lambda callback: FakeBatch(callback)
        )

        result = messages.fetch_messages(query="x", max_results=3)

        assert [m.id for m in result] == ["a", "b", "c"]
        assert [m.snippet for m in result] == ["snippet a", "snippet b", "snippet c"]

    def test_list_http_error_wrapped(self, mock_gmail_service):
        _list_call(mock_gmail_service).execute.side_effect = HttpError(
            resp=MagicMock(status=500, reason="boom"), content=b"err"
        )
        with pytest.raises(MgdioAPIError):
            messages.fetch_messages()
