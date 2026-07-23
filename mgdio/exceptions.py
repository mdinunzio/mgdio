"""Custom exceptions for mgdio."""

from __future__ import annotations


class MgdioError(Exception):
    """Base class for all mgdio errors."""


class MgdioAuthError(MgdioError):
    """Authentication or authorization failure."""


class MgdioKeyringError(MgdioAuthError):
    """The OS credential vault refused to store or delete an entry."""


class MgdioInteractionRequiredError(MgdioAuthError):
    """An interactive auth flow is needed but this session can't run one.

    Raised instead of starting a setup flow that would block forever on
    an unattended host (cron, systemd, CI). The message names the exact
    ``mgdio auth ...`` command to run in a terminal.
    """


class MgdioTokenRejectedError(MgdioAuthError):
    """The provider definitively rejected a stored refresh token.

    Distinct from transient failures (network, 5xx): rejection means the
    token is dead and re-authorization is genuinely required.
    """


class MissingClientSecretError(MgdioAuthError):
    """The OAuth client_secret.json file is not present on disk."""


class MissingWhoopCredentialsError(MgdioAuthError):
    """The Whoop Client ID / Secret have not been provided yet."""


class MgdioAPIError(MgdioError):
    """An external API returned an error (HTTP, transport, or schema)."""


class MgdioSendError(MgdioAPIError):
    """Sending a message via the Gmail API failed."""
