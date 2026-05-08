"""Custom exceptions for mgdio."""

from __future__ import annotations


class MgdioError(Exception):
    """Base class for all mgdio errors."""


class MgdioAuthError(MgdioError):
    """Authentication or authorization failure."""


class MissingClientSecretError(MgdioAuthError):
    """The OAuth client_secret.json file is not present on disk."""


class MgdioAPIError(MgdioError):
    """Wraps a googleapiclient.errors.HttpError from a Google API call."""


class MgdioSendError(MgdioAPIError):
    """Sending a message via the Gmail API failed."""
