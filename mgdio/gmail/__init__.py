"""Gmail subpackage public API.

Built on top of :mod:`mgdio.auth.google` -- the unified Google OAuth flow
provides the credentials; this subpackage just wraps the Gmail v1 API.
"""

from __future__ import annotations

from mgdio.gmail.client import get_service
from mgdio.gmail.messages import GmailMessage, fetch_message, fetch_messages
from mgdio.gmail.sender import send_email

__all__ = [
    "GmailMessage",
    "fetch_message",
    "fetch_messages",
    "get_service",
    "send_email",
]
