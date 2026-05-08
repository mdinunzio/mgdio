"""Send-side Gmail API: build a MIME message and post it via users.messages.send."""

from __future__ import annotations

import base64
import logging
import mimetypes
from collections.abc import Sequence
from email.message import EmailMessage
from pathlib import Path

from googleapiclient.errors import HttpError

from mgdio.exceptions import MgdioSendError
from mgdio.gmail.client import get_service

logger = logging.getLogger(__name__)


def send_email(
    to: str | Sequence[str],
    subject: str,
    body: str,
    *,
    cc: str | Sequence[str] | None = None,
    bcc: str | Sequence[str] | None = None,
    attachments: Sequence[Path | str] | None = None,
    html: str | None = None,
    sender: str | None = None,
) -> str:
    """Send an email via the Gmail API. Returns the sent message id.

    Args:
        to: Recipient address or sequence of addresses.
        subject: Subject line.
        body: Plain-text body.
        cc: Optional cc address(es).
        bcc: Optional bcc address(es).
        attachments: Optional file paths to attach.
        html: Optional HTML body. If provided, sent as a multipart/alternative
            with ``body`` as the plain-text fallback.
        sender: Optional ``From`` value. Defaults to ``"me"`` (the
            authenticated user); the Gmail API rewrites this to the
            authenticated address.

    Returns:
        The ``id`` of the message Gmail accepted.

    Raises:
        MgdioSendError: On any Gmail API HTTP error.
    """
    msg = _build_mime(
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        bcc=bcc,
        attachments=attachments,
        html=html,
        sender=sender,
    )
    encoded = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

    service = get_service()
    try:
        result = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": encoded})
            .execute()
        )
    except HttpError as exc:
        raise MgdioSendError(f"Gmail send failed: {exc}") from exc

    message_id = result.get("id", "")
    logger.debug("Sent message id=%s", message_id)
    return message_id


def _build_mime(
    *,
    to: str | Sequence[str],
    subject: str,
    body: str,
    cc: str | Sequence[str] | None,
    bcc: str | Sequence[str] | None,
    attachments: Sequence[Path | str] | None,
    html: str | None,
    sender: str | None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["To"] = _join(to)
    if cc:
        msg["Cc"] = _join(cc)
    if bcc:
        msg["Bcc"] = _join(bcc)
    if sender:
        msg["From"] = sender
    msg["Subject"] = subject
    msg.set_content(body)
    if html is not None:
        msg.add_alternative(html, subtype="html")
    for attachment in attachments or ():
        _attach_file(msg, Path(attachment))
    return msg


def _join(addrs: str | Sequence[str]) -> str:
    if isinstance(addrs, str):
        return addrs
    return ", ".join(addrs)


def _attach_file(msg: EmailMessage, path: Path) -> None:
    data = path.read_bytes()
    ctype, encoding = mimetypes.guess_type(path.name)
    if ctype is None or encoding is not None:
        ctype = "application/octet-stream"
    maintype, _, subtype = ctype.partition("/")
    msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=path.name)
