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


def _make_responses_by_id(ids, sample_payload):
    """Build a {mid: payload} dict for a fake batch to drain."""
    out = {}
    for mid in ids:
        payload = dict(sample_payload)
        payload["id"] = mid
        payload["snippet"] = f"snippet {mid}"
        out[mid] = payload
    return out


def _make_batch_factory(responses_by_id, error_plan=None):
    """Build a `new_batch_http_request`-compatible factory.

    Args:
        responses_by_id: mapping from message id to the JSON payload to
            deliver on success.
        error_plan: optional dict mapping message id -> list of
            exceptions to deliver, one per call. After the list is
            drained the next call returns the successful payload.
            Lets a test simulate "id X fails once, succeeds on retry".

    Returns:
        A callable + a list that tracks how many batches were created
        (use ``len(batch_log)`` to assert chunk count).
    """
    error_plan = error_plan or {}
    batch_log: list[int] = []

    class FakeBatch:
        def __init__(self, callback):
            self._callback = callback
            self._items: list[tuple[str, object]] = []
            batch_log.append(len(batch_log))

        def add(self, request, request_id):
            self._items.append((request_id, request))

        def execute(self):
            for request_id, _request in self._items:
                queue = error_plan.get(request_id)
                if queue:
                    self._callback(request_id, None, queue.pop(0))
                else:
                    self._callback(request_id, responses_by_id[request_id], None)

    return (lambda callback: FakeBatch(callback)), batch_log


class TestFetchMessagesBatchSize:
    def test_batch_size_chunks_split_correctly(
        self, mock_gmail_service, sample_message_payload
    ):
        ids = [f"m{i}" for i in range(25)]
        _list_call(mock_gmail_service).execute.return_value = {
            "messages": [{"id": mid} for mid in ids]
        }
        responses = _make_responses_by_id(ids, sample_message_payload)
        factory, batch_log = _make_batch_factory(responses)
        mock_gmail_service.new_batch_http_request.side_effect = factory

        result = messages.fetch_messages(max_results=25, batch_size=10)

        assert [m.id for m in result] == ids
        # 25 ids at batch_size=10 -> 3 batches (10 + 10 + 5).
        assert len(batch_log) == 3

    def test_batch_size_one_creates_n_batches(
        self, mock_gmail_service, sample_message_payload
    ):
        ids = [f"m{i}" for i in range(5)]
        _list_call(mock_gmail_service).execute.return_value = {
            "messages": [{"id": mid} for mid in ids]
        }
        responses = _make_responses_by_id(ids, sample_message_payload)
        factory, batch_log = _make_batch_factory(responses)
        mock_gmail_service.new_batch_http_request.side_effect = factory

        messages.fetch_messages(max_results=5, batch_size=1)
        assert len(batch_log) == 5

    def test_invalid_batch_size_raises(self, mock_gmail_service):
        with pytest.raises(ValueError, match="batch_size"):
            messages.fetch_messages(batch_size=0)

    def test_invalid_max_retries_raises(self, mock_gmail_service):
        with pytest.raises(ValueError, match="max_retries"):
            messages.fetch_messages(max_retries=-1)


class TestFetchMessagesRetry:
    def test_429_on_one_id_recovers_on_retry(
        self, mock_gmail_service, sample_message_payload, monkeypatch
    ):
        ids = ["a", "b", "c"]
        _list_call(mock_gmail_service).execute.return_value = {
            "messages": [{"id": mid} for mid in ids]
        }
        responses = _make_responses_by_id(ids, sample_message_payload)
        rate_limit = HttpError(
            resp=MagicMock(status=429, reason="Too Many Requests"),
            content=b"rateLimitExceeded",
        )
        factory, batch_log = _make_batch_factory(
            responses, error_plan={"b": [rate_limit]}
        )
        mock_gmail_service.new_batch_http_request.side_effect = factory

        # Eliminate the real sleep so tests stay fast.
        sleeps: list[float] = []
        monkeypatch.setattr(
            "mgdio.gmail.messages.time.sleep", lambda s: sleeps.append(s)
        )

        result = messages.fetch_messages(
            max_results=3, batch_size=10, initial_backoff=0.1
        )

        assert [m.id for m in result] == ids
        # First batch fetched all 3 ids; second batch only re-fetched "b".
        assert len(batch_log) == 2
        # Sleep happened once between attempts.
        assert sleeps == [0.1]

    def test_429_exhausts_retries_raises_with_helpful_message(
        self, mock_gmail_service, sample_message_payload, monkeypatch
    ):
        ids = ["a", "b"]
        _list_call(mock_gmail_service).execute.return_value = {
            "messages": [{"id": mid} for mid in ids]
        }
        responses = _make_responses_by_id(ids, sample_message_payload)
        # "b" returns 429 every single time.
        error_plan = {
            "b": [
                HttpError(resp=MagicMock(status=429), content=b"x") for _ in range(10)
            ]
        }
        factory, batch_log = _make_batch_factory(responses, error_plan=error_plan)
        mock_gmail_service.new_batch_http_request.side_effect = factory
        monkeypatch.setattr("mgdio.gmail.messages.time.sleep", lambda _s: None)

        with pytest.raises(MgdioAPIError, match="rate-limited|batch_size"):
            messages.fetch_messages(
                max_results=2,
                batch_size=10,
                max_retries=2,
                initial_backoff=0.01,
            )

        # max_retries=2 -> 1 original + 2 retries = 3 attempts on the failed id.
        assert len(batch_log) == 3

    def test_non_429_http_error_is_not_retried(
        self, mock_gmail_service, sample_message_payload, monkeypatch
    ):
        ids = ["a", "b"]
        _list_call(mock_gmail_service).execute.return_value = {
            "messages": [{"id": mid} for mid in ids]
        }
        responses = _make_responses_by_id(ids, sample_message_payload)
        error_plan = {"b": [HttpError(resp=MagicMock(status=500), content=b"boom")]}
        factory, batch_log = _make_batch_factory(responses, error_plan=error_plan)
        mock_gmail_service.new_batch_http_request.side_effect = factory
        monkeypatch.setattr("mgdio.gmail.messages.time.sleep", lambda _s: None)

        with pytest.raises(MgdioAPIError):
            messages.fetch_messages(max_results=2, batch_size=10, max_retries=5)

        # Only one batch was attempted; 500 should NOT trigger a retry.
        assert len(batch_log) == 1

    def test_backoff_doubles_then_caps(
        self, mock_gmail_service, sample_message_payload, monkeypatch
    ):
        ids = ["a"]
        _list_call(mock_gmail_service).execute.return_value = {
            "messages": [{"id": "a"}]
        }
        responses = _make_responses_by_id(ids, sample_message_payload)
        # 4 consecutive 429s, then success.
        error_plan = {
            "a": [HttpError(resp=MagicMock(status=429), content=b"x") for _ in range(4)]
        }
        factory, _ = _make_batch_factory(responses, error_plan=error_plan)
        mock_gmail_service.new_batch_http_request.side_effect = factory
        sleeps: list[float] = []
        monkeypatch.setattr(
            "mgdio.gmail.messages.time.sleep", lambda s: sleeps.append(s)
        )

        messages.fetch_messages(
            max_results=1,
            batch_size=10,
            max_retries=10,
            initial_backoff=1.0,
        )

        # Initial 1.0, then 2.0, 4.0, 8.0 -- doubling each retry, capped at 30.
        assert sleeps == [1.0, 2.0, 4.0, 8.0]
