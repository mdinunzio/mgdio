"""Unit tests for ``mgdio.gmail.sender``."""

from __future__ import annotations

import base64
from email import message_from_bytes
from email.policy import default as default_policy
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from mgdio.exceptions import MgdioSendError
from mgdio.gmail import sender


def _send_call(mock_service: MagicMock) -> MagicMock:
    return mock_service.users.return_value.messages.return_value.send


def _decode_sent_raw(mock_service: MagicMock):
    """Pull the ``raw`` arg the sender passed to users().messages().send()."""
    raw_b64 = _send_call(mock_service).call_args.kwargs["body"]["raw"]
    raw_b64 += "=" * (-len(raw_b64) % 4)
    raw_bytes = base64.urlsafe_b64decode(raw_b64.encode("ascii"))
    return message_from_bytes(raw_bytes, policy=default_policy)


class TestSendEmailMime:
    def test_plain_text_headers_and_body(self, mock_gmail_service):
        _send_call(mock_gmail_service).return_value.execute.return_value = {
            "id": "msg-123"
        }

        result = sender.send_email(
            to="alice@example.com",
            subject="Hi",
            body="hello there",
        )

        assert result == "msg-123"
        msg = _decode_sent_raw(mock_gmail_service)
        assert msg["To"] == "alice@example.com"
        assert msg["Subject"] == "Hi"
        assert msg.get_content().strip() == "hello there"

    def test_multiple_recipients_and_cc_bcc(self, mock_gmail_service):
        _send_call(mock_gmail_service).return_value.execute.return_value = {"id": "id"}

        sender.send_email(
            to=["a@example.com", "b@example.com"],
            subject="multi",
            body="body",
            cc="c@example.com",
            bcc=["d@example.com", "e@example.com"],
        )

        msg = _decode_sent_raw(mock_gmail_service)
        assert msg["To"] == "a@example.com, b@example.com"
        assert msg["Cc"] == "c@example.com"
        assert msg["Bcc"] == "d@example.com, e@example.com"

    def test_html_alternative_produces_multipart(self, mock_gmail_service):
        _send_call(mock_gmail_service).return_value.execute.return_value = {"id": "id"}

        sender.send_email(
            to="a@example.com",
            subject="s",
            body="plain body",
            html="<p>html body</p>",
        )

        msg = _decode_sent_raw(mock_gmail_service)
        assert msg.is_multipart()
        bodies = {
            part.get_content_type(): part.get_content() for part in msg.iter_parts()
        }
        assert bodies["text/plain"].strip() == "plain body"
        assert bodies["text/html"].strip() == "<p>html body</p>"

    def test_attachment_added(self, mock_gmail_service, tmp_path):
        attachment = tmp_path / "report.bin"
        attachment.write_bytes(b"file content")
        _send_call(mock_gmail_service).return_value.execute.return_value = {"id": "id"}

        sender.send_email(
            to="a@example.com",
            subject="s",
            body="b",
            attachments=[attachment],
        )

        msg = _decode_sent_raw(mock_gmail_service)
        attachments = [
            p for p in msg.iter_attachments() if p.get_filename() == "report.bin"
        ]
        assert len(attachments) == 1
        assert attachments[0].get_content() == b"file content"
        assert attachments[0].get_content_type() == "application/octet-stream"


class TestSendEmailErrors:
    def test_http_error_wrapped(self, mock_gmail_service):
        _send_call(mock_gmail_service).return_value.execute.side_effect = HttpError(
            resp=MagicMock(status=500, reason="boom"), content=b"err"
        )
        with pytest.raises(MgdioSendError):
            sender.send_email(to="a@example.com", subject="s", body="b")
