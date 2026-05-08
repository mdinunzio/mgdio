"""Read-side Gmail API: fetch_messages, fetch_message, GmailMessage.

The Gmail API's ``users.messages.list`` returns only ``{id, threadId}`` per
result; full content requires a per-id GET. We use ``BatchHttpRequest`` to
collapse the N follow-up GETs into a single HTTP round trip.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import getaddresses

from googleapiclient.errors import HttpError
from googleapiclient.http import BatchHttpRequest

from mgdio.exceptions import MgdioAPIError
from mgdio.gmail.client import get_service

logger = logging.getLogger(__name__)

_BATCH_CHUNK_SIZE = 100


@dataclass(frozen=True, slots=True)
class GmailMessage:
    """A normalized Gmail message.

    Attributes:
        id: Gmail message id.
        thread_id: Thread the message belongs to.
        subject: Subject header (``""`` if missing).
        sender: ``From`` header value.
        to: Tuple of recipient addresses parsed from ``To``.
        cc: Tuple of cc addresses.
        date: UTC datetime parsed from ``internalDate`` (epoch ms).
        snippet: Gmail-provided short snippet of the body.
        body_text: Best-effort plain-text body. Empty if none found.
        body_html: HTML body if present, else ``None``.
        label_ids: Tuple of Gmail label ids (e.g. ``INBOX``, ``UNREAD``).
    """

    id: str
    thread_id: str
    subject: str
    sender: str
    to: tuple[str, ...]
    cc: tuple[str, ...]
    date: datetime
    snippet: str
    body_text: str
    body_html: str | None
    label_ids: tuple[str, ...]


def fetch_messages(
    query: str = "",
    max_results: int = 50,
) -> list[GmailMessage]:
    """List messages matching ``query`` and fetch their full content.

    Uses ``users.messages.list`` to discover ids, then a
    ``BatchHttpRequest`` of ``users.messages.get`` calls to populate each
    :class:`GmailMessage`. Order matches the list response (newest first
    by default).

    Args:
        query: Gmail search syntax, e.g.
            ``"from:foo@bar.com after:2026/01/01"``. Empty string returns
            the most recent inbox messages.
        max_results: Maximum number of messages to return.

    Returns:
        List of populated :class:`GmailMessage` objects, possibly empty.

    Raises:
        MgdioAPIError: On any Gmail API HTTP error.
    """
    service = get_service()
    try:
        listing = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
    except HttpError as exc:
        raise MgdioAPIError(f"Gmail list failed: {exc}") from exc

    ids: list[str] = [item["id"] for item in listing.get("messages", [])]
    if not ids:
        return []

    raws_by_id: dict[str, dict] = {}
    errors: list[Exception] = []

    def _on_response(request_id: str, response: dict, exception: Exception | None):
        if exception is not None:
            errors.append(exception)
            return
        raws_by_id[request_id] = response

    for chunk_start in range(0, len(ids), _BATCH_CHUNK_SIZE):
        chunk = ids[chunk_start : chunk_start + _BATCH_CHUNK_SIZE]
        batch: BatchHttpRequest = service.new_batch_http_request(callback=_on_response)
        for message_id in chunk:
            batch.add(
                service.users().messages().get(
                    userId="me", id=message_id, format="full"
                ),
                request_id=message_id,
            )
        try:
            batch.execute()
        except HttpError as exc:
            raise MgdioAPIError(f"Gmail batch get failed: {exc}") from exc

    if errors:
        raise MgdioAPIError(f"Gmail batch get returned errors: {errors[0]}")

    return [_to_dataclass(raws_by_id[mid]) for mid in ids if mid in raws_by_id]


def fetch_message(message_id: str) -> GmailMessage:
    """Fetch a single message by id (full format).

    Args:
        message_id: Gmail message id.

    Returns:
        A populated :class:`GmailMessage`.

    Raises:
        MgdioAPIError: On any Gmail API HTTP error.
    """
    service = get_service()
    try:
        raw = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
    except HttpError as exc:
        raise MgdioAPIError(f"Gmail get failed for {message_id}: {exc}") from exc
    return _to_dataclass(raw)


def _to_dataclass(raw: dict) -> GmailMessage:
    headers = {
        h["name"].lower(): h["value"]
        for h in raw.get("payload", {}).get("headers", [])
    }
    body_text, body_html = _parse_payload(raw.get("payload", {}))

    internal_ms = int(raw.get("internalDate", "0"))
    date = datetime.fromtimestamp(internal_ms / 1000.0, tz=timezone.utc)

    return GmailMessage(
        id=raw["id"],
        thread_id=raw.get("threadId", ""),
        subject=headers.get("subject", ""),
        sender=headers.get("from", ""),
        to=_split_addresses(headers.get("to", "")),
        cc=_split_addresses(headers.get("cc", "")),
        date=date,
        snippet=raw.get("snippet", ""),
        body_text=body_text,
        body_html=body_html,
        label_ids=tuple(raw.get("labelIds", [])),
    )


def _split_addresses(header_value: str) -> tuple[str, ...]:
    if not header_value:
        return ()
    return tuple(addr for _name, addr in getaddresses([header_value]) if addr)


def _parse_payload(payload: dict) -> tuple[str, str | None]:
    """Walk the MIME tree and return ``(text, html)`` decoded as strings.

    Picks the first ``text/plain`` and ``text/html`` parts encountered.
    Attachments and other parts are ignored.
    """
    text_chunks: list[str] = []
    html_chunks: list[str] = []

    def _walk(part: dict) -> None:
        mime_type = part.get("mimeType", "")
        body = part.get("body", {}) or {}
        data = body.get("data")
        if data and mime_type == "text/plain" and not text_chunks:
            text_chunks.append(_decode_b64url(data))
        elif data and mime_type == "text/html" and not html_chunks:
            html_chunks.append(_decode_b64url(data))
        for sub_part in part.get("parts", []) or []:
            _walk(sub_part)

    _walk(payload)
    text = text_chunks[0] if text_chunks else ""
    html = html_chunks[0] if html_chunks else None
    return text, html


def _decode_b64url(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode(
        "utf-8", errors="replace"
    )
