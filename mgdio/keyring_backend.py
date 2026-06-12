"""Auto-select a working :mod:`keyring` backend, even on headless Linux.

On Windows (Credential Manager) and macOS (Keychain) the OS-native vault
always works, so this module does nothing there. On Linux, a minimal
image -- a headless VPS, a container, an SSH-only host -- frequently has
no Secret Service daemon (``gnome-keyring`` / ``kwallet`` /
``dbus-secret-service``) running. The default ``keyring`` backend then
either raises ``NoKeyringError`` on first use or resolves to the
inert "fail"/"null" backend, breaking every token read and write.

To make ``mgdio`` work out of the box in those environments,
:func:`ensure_keyring_backend` is called once at import time (from
:mod:`mgdio.settings`, which is imported before any keyring access). It:

1. leaves a working native/Secret-Service backend untouched;
2. otherwise falls back to a file-based backend from ``keyrings.alt``,
   defaulting to an **unencrypted** store (so unattended/cron use never
   blocks on an interactive password prompt), with a one-time warning;
3. always honours an explicit ``MGDIO_KEYRING_BACKEND`` /
   ``PYTHON_KEYRING_BACKEND`` override -- a user's deliberate choice
   wins over the auto-fallback.

The fallback store lives under the platform data dir and is locked to
the current user (``chmod 700`` dir, ``chmod 600`` file) since, when
unencrypted, file permissions are the only protection.

Set ``MGDIO_KEYRING_PLAINTEXT=0`` to prefer the encrypted file backend
instead; note that the encrypted backend prompts for a password on every
process, which is unsuitable for cron.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import keyring
import platformdirs

logger = logging.getLogger(__name__)

# Set once we've run, so repeated settings imports don't re-select or
# re-warn. Idempotent by design.
_backend_selected: bool = False


def _native_backend_works() -> bool:
    """Return True if the currently-resolved keyring backend is usable.

    A round-trip set/delete is the only reliable probe: on a headless
    Linux box the Secret Service backend imports fine but raises on first
    access. We use a throwaway service/username and clean up after.
    """
    try:
        backend = keyring.get_keyring()
    except Exception:  # pragma: no cover - defensive
        return False

    # The inert backends report a priority <= 0 and never persist data.
    name = type(backend).__module__ + "." + type(backend).__name__
    if "fail" in name.lower() or "null" in name.lower():
        return False

    probe_service = "mgdio:__backend_probe__"
    probe_user = "probe"
    try:
        keyring.set_password(probe_service, probe_user, "1")
        ok = keyring.get_password(probe_service, probe_user) == "1"
    except Exception:
        return False
    finally:
        try:
            keyring.delete_password(probe_service, probe_user)
        except Exception:
            pass
    return ok


def _fallback_dir() -> Path:
    """Return (creating) the locked-down dir for file-based keyring stores."""
    path = Path(platformdirs.user_data_dir("mgdio")) / "keyring"
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:  # pragma: no cover - best effort on exotic filesystems
        pass
    return path


def _lock_down(file_path: Path) -> None:
    """``chmod 600`` a keyring store file if it exists (best effort)."""
    try:
        if file_path.exists():
            os.chmod(file_path, 0o600)
    except OSError:  # pragma: no cover - best effort
        pass


def _select_file_backend() -> bool:
    """Install a ``keyrings.alt`` file backend. Returns True on success.

    Defaults to the plaintext store (no interactive password, cron-safe).
    Set ``MGDIO_KEYRING_PLAINTEXT=0`` to prefer the encrypted store.
    """
    # Plaintext is the default; only an explicit "0" opts into encryption.
    prefer_plaintext = os.getenv("MGDIO_KEYRING_PLAINTEXT", "1").strip() != "0"

    fallback_dir = _fallback_dir()

    if prefer_plaintext:
        try:
            from keyrings.alt.file import PlaintextKeyring
        except ImportError:
            logger.error(
                "No usable keyring backend and 'keyrings.alt' is not "
                "installed. Install it (Linux: `pip install keyrings.alt`) "
                "or set PYTHON_KEYRING_BACKEND to a backend that works."
            )
            return False
        backend = PlaintextKeyring()
        backend.file_path = str(fallback_dir / "mgdio_plaintext.cfg")
        keyring.set_keyring(backend)
        _lock_down(Path(backend.file_path))
        logger.warning(
            "No OS keyring available; storing credentials UNENCRYPTED at "
            "%s (file locked to your user). Set MGDIO_KEYRING_PLAINTEXT=0 "
            "for an encrypted store (note: it prompts for a password on "
            "every run, so it is unsuitable for cron).",
            backend.file_path,
        )
        return True

    # Encrypted fallback (opt-in).
    try:
        from keyrings.alt.file import EncryptedKeyring
    except ImportError:
        logger.error(
            "Encrypted keyring requested but 'keyrings.alt' is not "
            "installed. Install it (Linux: `pip install keyrings.alt`)."
        )
        return False
    backend = EncryptedKeyring()
    backend.file_path = str(fallback_dir / "mgdio_encrypted.cfg")
    keyring.set_keyring(backend)
    _lock_down(Path(backend.file_path))
    logger.info(
        "Using encrypted file keyring at %s. It prompts for a password "
        "on first access each run.",
        backend.file_path,
    )
    return True


def ensure_keyring_backend() -> None:
    """Ensure a usable keyring backend is selected. Idempotent.

    Called once from :mod:`mgdio.settings` at import time. Does nothing
    when a native/Secret-Service backend already works, or when the user
    has explicitly chosen a backend via ``MGDIO_KEYRING_BACKEND`` or
    ``PYTHON_KEYRING_BACKEND``.
    """
    global _backend_selected
    if _backend_selected:
        return
    _backend_selected = True

    # Respect an explicit user choice: if either env var is set, let
    # `keyring` resolve it natively and don't interfere.
    explicit = os.getenv("MGDIO_KEYRING_BACKEND") or os.getenv("PYTHON_KEYRING_BACKEND")
    if explicit:
        # mgdio's own var is an alias for keyring's; bridge it so keyring
        # picks it up if only MGDIO_KEYRING_BACKEND was set.
        os.environ.setdefault("PYTHON_KEYRING_BACKEND", explicit)
        logger.debug("Using explicitly configured keyring backend: %s", explicit)
        return

    # Windows (Credential Manager) and macOS (Keychain) have a reliable
    # native vault. Skip the probe there entirely -- it's a no-op anyway,
    # and avoiding it keeps every CLI invocation free of a spurious
    # write/read/delete against the OS vault on import.
    if sys.platform != "linux":
        return

    # On Linux the native backend may import fine yet fail on first use
    # (no Secret Service daemon), so a round-trip probe is the only
    # reliable signal. If it works, leave it alone.
    if _native_backend_works():
        return

    _select_file_backend()
