"""Custom exceptions for mgdio."""

from __future__ import annotations


class MgdioError(Exception):
    """Base class for all mgdio errors."""


class MgdioAuthError(MgdioError):
    """Authentication or authorization failure."""


class MissingClientSecretError(MgdioAuthError):
    """The OAuth client_secret.json file is not present on disk."""


class MgdioAPIError(MgdioError):
    """An external API returned an error (HTTP, transport, or schema)."""


class MgdioSendError(MgdioAPIError):
    """Sending a message via the Gmail API failed."""
