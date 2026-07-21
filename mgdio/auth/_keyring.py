"""Robust keyring writes/deletes shared by every auth provider.

macOS binds each Keychain item's ACL to the application that created it.
When that binary is later replaced -- most commonly a rebuilt or
relinked ``.venv`` python -- the Keychain refuses to let the new binary
overwrite or delete the old item, surfacing as
``errSecInvalidOwnerEdit`` (``-25244``) from
:func:`keyring.set_password` / :func:`keyring.delete_password`. Apple's
``security`` CLI is not subject to a generic-password item's
application ACL, so deleting the stale item with it and retrying
recovers without user intervention.

All credential writes in mgdio should go through :func:`set_password` /
:func:`delete_password` here rather than calling :mod:`keyring`
directly, and interactive flows should call :func:`ensure_writable`
*before* prompting the user, so a broken vault entry fails fast instead
of after a completed consent screen.
"""

from __future__ import annotations

import logging
import subprocess
import sys

import keyring

from mgdio.exceptions import MgdioKeyringError

logger = logging.getLogger(__name__)

# ``security delete-generic-password`` exit status for "no such item".
_SECURITY_NOT_FOUND = 44


def set_password(service: str, username: str, secret: str) -> None:
    """Store ``secret``, recovering from a stale macOS Keychain item.

    Args:
        service: Keyring service id, e.g. ``mgdio:google:<slug>``.
        username: Keyring account name within the service.
        secret: The credential payload to store.

    Raises:
        MgdioKeyringError: If the backend refuses the write and recovery
            fails. The message includes the manual fix.
    """
    try:
        keyring.set_password(service, username, secret)
        return
    except keyring.errors.PasswordSetError as exc:
        logger.warning("Keyring refused to store %r/%r: %s", service, username, exc)
        if _force_delete_macos_item(service, username):
            try:
                keyring.set_password(service, username, secret)
                logger.info(
                    "Recovered: replaced stale Keychain item at %r/%r.",
                    service,
                    username,
                )
                return
            except keyring.errors.PasswordSetError as retry_exc:
                exc = retry_exc
        raise MgdioKeyringError(
            f"Could not store a credential at keyring service {service!r}. "
            + _manual_fix_hint(service, username)
        ) from exc


def delete_password(service: str, username: str) -> None:
    """Delete an entry; silent if absent, loud if the backend refuses.

    Args:
        service: Keyring service id.
        username: Keyring account name within the service.

    Raises:
        MgdioKeyringError: If the entry exists but cannot be deleted,
            even after stale-item recovery.
    """
    try:
        keyring.delete_password(service, username)
        return
    except keyring.errors.PasswordDeleteError as exc:
        if not _item_exists(service, username):
            return
        logger.warning("Keyring refused to delete %r/%r: %s", service, username, exc)
        if _force_delete_macos_item(service, username):
            return
        raise MgdioKeyringError(
            f"Could not delete the keyring entry at service {service!r}. "
            + _manual_fix_hint(service, username)
        ) from exc


def ensure_writable(service: str, username: str) -> None:
    """Prove an existing entry can be overwritten, before an interactive flow.

    Rewrites the entry with its current value -- keyring's set is
    delete-then-add, the exact operation the post-flow save performs --
    which triggers the same stale-item recovery as :func:`set_password`.
    A missing or unreadable entry is fine: a fresh add cannot hit the
    stale-ACL problem.

    Args:
        service: Keyring service id.
        username: Keyring account name within the service.

    Raises:
        MgdioKeyringError: If the entry exists and cannot be rewritten.
    """
    try:
        current = keyring.get_password(service, username)
    except Exception:
        return
    if current is None:
        return
    set_password(service, username, current)


def _item_exists(service: str, username: str) -> bool:
    try:
        return keyring.get_password(service, username) is not None
    except Exception:
        # Delete was refused and the entry can't even be read -- assume
        # it exists so the caller surfaces the failure.
        return True


def _using_macos_keychain() -> bool:
    """True only when the active backend is the real macOS Keychain."""
    if sys.platform != "darwin":
        return False
    try:
        backend = keyring.get_keyring()
    except Exception:
        return False
    return "macos" in type(backend).__module__.lower()


def _force_delete_macos_item(service: str, username: str) -> bool:
    """Remove a stale Keychain item with Apple's ``security`` CLI.

    Returns True if the item is now gone (deleted, or already absent).
    Always False on non-Keychain backends and other platforms.
    """
    if not _using_macos_keychain():
        return False
    try:
        proc = subprocess.run(
            ["security", "delete-generic-password", "-s", service, "-a", username],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        logger.warning("Could not run the `security` CLI: %s", exc)
        return False
    if proc.returncode in (0, _SECURITY_NOT_FOUND):
        return True
    logger.warning(
        "`security delete-generic-password` failed (exit %s): %s",
        proc.returncode,
        proc.stderr.strip(),
    )
    return False


def _manual_fix_hint(service: str, username: str) -> str:
    if sys.platform == "darwin":
        return (
            "This usually means the Keychain item was created by a binary "
            "that no longer exists (e.g. a rebuilt .venv). Delete the stale "
            "item manually with:\n"
            f'  security delete-generic-password -s "{service}" -a "{username}"\n'
            "then re-run the auth command."
        )
    return (
        "Remove the entry from your OS credential store (Windows Credential "
        "Manager / Secret Service) and re-run the auth command."
    )
