"""Decide whether an interactive auth flow may run in this session.

Every provider's getter (``get_access_token``, ``get_credentials``, ...)
falls back to an interactive setup flow when no usable token exists.
Those flows block forever waiting for a human -- the browser-based ones
on a localhost callback that never fires without a browser, the headless
ones on stdin. On an unattended host (cron, systemd, CI) that turns a
stale token into a silent, indefinite hang instead of an error.

:func:`require_interactive` is called by each getter just before its
interactive fallback. Whether a flow may run is decided by:

1. ``MGDIO_NONINTERACTIVE`` -- ``1``/``true``/``yes`` always forbids,
   ``0``/``false``/``no`` always allows. An explicit choice wins.
2. Otherwise, a tty heuristic: allowed only when stdin is a terminal.
   Cron/systemd/piped contexts get an immediate, actionable error.

Explicit ``mgdio auth <provider>`` runs from a real terminal have a tty,
so the guard never blocks a user who deliberately started an auth flow.
A GUI-launched process with no tty but a working browser is the one case
the heuristic gets wrong -- set ``MGDIO_NONINTERACTIVE=0`` there.
"""

from __future__ import annotations

import os
import sys

from mgdio.exceptions import MgdioInteractionRequiredError

_FORBID_VALUES = ("1", "true", "yes")
_ALLOW_VALUES = ("0", "false", "no")


def interactive_allowed() -> bool:
    """Return True if an interactive auth flow may run in this session."""
    env = os.getenv("MGDIO_NONINTERACTIVE", "").strip().lower()
    if env in _FORBID_VALUES:
        return False
    if env in _ALLOW_VALUES:
        return True
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        # stdin replaced or closed (e.g. some daemon setups).
        return False


def require_interactive(provider: str, auth_command: str, reason: str) -> None:
    """Raise unless an interactive auth flow may run in this session.

    Args:
        provider: Human-readable provider name, e.g. ``"Whoop"``.
        auth_command: The CLI command that fixes it, e.g.
            ``"mgdio auth whoop"``.
        reason: Why a flow is needed, e.g. ``"no stored token"``.

    Raises:
        MgdioInteractionRequiredError: If interactive flows are
            disallowed (``MGDIO_NONINTERACTIVE=1`` or no tty).
    """
    if interactive_allowed():
        return
    raise MgdioInteractionRequiredError(
        f"{provider}: {reason}, and this session cannot run an interactive "
        f"auth flow (no tty, or MGDIO_NONINTERACTIVE=1). Run "
        f"`{auth_command}` in a terminal on this machine to re-authorize."
    )
