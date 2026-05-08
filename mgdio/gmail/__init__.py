"""Gmail subpackage public API."""

from __future__ import annotations

from mgdio.gmail.auth import clear_stored_token, get_credentials
from mgdio.gmail.client import get_service
from mgdio.gmail.messages import GmailMessage, fetch_message, fetch_messages
from mgdio.gmail.sender import send_email

__all__ = [
    "GmailMessage",
    "clear_stored_token",
    "fetch_message",
    "fetch_messages",
    "get_credentials",
    "get_service",
    "send_email",
]
