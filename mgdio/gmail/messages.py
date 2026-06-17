"""Read-side Gmail API: fetch_messages, fetch_message, GmailMessage.

The Gmail API's ``users.messages.list`` returns only ``{id, threadId}`` per
result; full content requires a per-id GET. We use ``BatchHttpRequest`` to
collapse the N follow-up GETs into a single HTTP round trip.

Rate-limit handling
===================

Free / consumer Gmail accounts have a much lower per-user concurrency cap
than Workspace accounts. A 100-wide ``BatchHttpRequest`` of
``users.messages.get`` calls reliably trips ``rateLimitExceeded`` (HTTP
429) on personal accounts even though each individual call is cheap.

``fetch_messages`` exposes a ``batch_size`` parameter for that reason.
For personal accounts a value around 10-25 is usually safe; the default
of 100 is kept for backwards-compatibility and works fine for Workspace
accounts.

On top of that, the batch loop retries any 429 / quota responses with
exponential backoff (only the failed ids are re-issued, not the whole
batch). Tunable via ``max_retries`` and ``initial_backoff``.
"""

from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import getaddresses

from googleapiclient.errors import HttpError
from googleapiclient.http import BatchHttpRequest

from mgdio.exceptions import MgdioAPIError
from mgdio.gmail.client import get_service

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE: int = 100
DEFAULT_MAX_RETRIES: int = 5
DEFAULT_INITIAL_BACKOFF: float = 1.0


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
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_retries: int = DEFAULT_MAX_RETRIES,
    initial_backoff: float = DEFAULT_INITIAL_BACKOFF,
    profile: str | None = None,
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
        batch_size: How many ``messages.get`` calls to bundle into a single
            ``BatchHttpRequest``. Each request inside a batch dispatches
            concurrently from Google's side; free/consumer Gmail accounts
            cap concurrent requests-per-user lower than Workspace
            accounts, so a wide batch can trip ``rateLimitExceeded``
            (HTTP 429). If you see that error, drop this to ``10`` or
            ``25``. Default ``100`` works for Workspace.
        max_retries: How many times to retry ids that came back with a
            429 / quota error before giving up. Only the failed ids are
            re-issued, not the whole batch.
        initial_backoff: Seconds to wait before the first retry. Doubles
            on each subsequent retry (capped at 30s).
        profile: Google account profile slug, or None to resolve via the
            waterfall (env var / sole profile).

    Returns:
        List of populated :class:`GmailMessage` objects, possibly empty.

    Raises:
        MgdioAPIError: On any Gmail API HTTP error that survives the
            retry budget.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    if max_retries < 0:
        raise ValueError("max_retries must be >= 0")

    service = get_service(profile)
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

    for chunk_start in range(0, len(ids), batch_size):
        chunk = ids[chunk_start : chunk_start + batch_size]
        _fetch_chunk_with_retry(
            service,
            chunk,
            raws_by_id,
            max_retries=max_retries,
            initial_backoff=initial_backoff,
        )

    return [_to_dataclass(raws_by_id[mid]) for mid in ids if mid in raws_by_id]


def _fetch_chunk_with_retry(
    service,
    ids: list[str],
    raws_by_id: dict[str, dict],
    *,
    max_retries: int,
    initial_backoff: float,
) -> None:
    """Execute a single batch.get; retry any 429-tagged ids with backoff."""
    pending = list(ids)
    backoff = initial_backoff
    attempts_remaining = max_retries + 1

    while pending and attempts_remaining > 0:
        attempts_remaining -= 1
        fatal: list[Exception] = []
        retryable: list[str] = []

        def _on_response(
            request_id: str,
            response: dict,
            exception: Exception | None,
        ) -> None:
            if exception is None:
                raws_by_id[request_id] = response
                return
            if _is_rate_limit(exception):
                retryable.append(request_id)
            else:
                fatal.append(exception)

        batch: BatchHttpRequest = service.new_batch_http_request(callback=_on_response)
        for message_id in pending:
            batch.add(
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full"),
                request_id=message_id,
            )
        try:
            batch.execute()
        except HttpError as exc:
            raise MgdioAPIError(f"Gmail batch get failed: {exc}") from exc

        if fatal:
            raise MgdioAPIError(f"Gmail batch get returned errors: {fatal[0]}")

        if not retryable:
            return

        if attempts_remaining <= 0:
            raise MgdioAPIError(
                f"Gmail batch get returned errors: "
                f"rate-limited after {max_retries} retries on "
                f"{len(retryable)} id(s). Try a smaller batch_size."
            )

        logger.warning(
            "Gmail rate-limited on %d/%d ids; sleeping %.1fs before retry",
            len(retryable),
            len(pending),
            backoff,
        )
        time.sleep(backoff)
        backoff = min(backoff * 2, 30.0)
        pending = retryable


def _is_rate_limit(exception: Exception) -> bool:
    """Return True if `exception` is a Gmail 429 / quota error worth retrying."""
    if not isinstance(exception, HttpError):
        return False
    status = getattr(getattr(exception, "resp", None), "status", None)
    return status == 429


def fetch_message(message_id: str, *, profile: str | None = None) -> GmailMessage:
    """Fetch a single message by id (full format).

    Args:
        message_id: Gmail message id.
        profile: Google account profile slug, or None to resolve via the
            waterfall (env var / sole profile).

    Returns:
        A populated :class:`GmailMessage`.

    Raises:
        MgdioAPIError: On any Gmail API HTTP error.
    """
    service = get_service(profile)
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
        h["name"].lower(): h["value"] for h in raw.get("payload", {}).get("headers", [])
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
