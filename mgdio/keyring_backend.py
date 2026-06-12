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
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import keyring
import platformdirs

logger = logging.getLogger(__name__)


@contextmanager
def _no_interactive_stdin() -> Iterator[None]:
    """Temporarily point stdin at os.devnull so prompts can't block.

    Some keyring backends (notably ``keyrings.alt``'s ``EncryptedKeyring``)
    call ``getpass`` on first access. During our probe we never want that
    to hang waiting for a human -- redirecting stdin to ``/dev/null`` makes
    ``getpass`` hit EOF and raise instead, which we treat as "unusable".
    """
    try:
        devnull = open(os.devnull, "r")
    except OSError:  # pragma: no cover - no /dev/null is exotic
        yield
        return
    saved = sys.stdin
    sys.stdin = devnull
    try:
        yield
    finally:
        sys.stdin = saved
        try:
            devnull.close()
        except OSError:  # pragma: no cover
            pass


# Set once we've run, so repeated settings imports don't re-select or
# re-warn. Idempotent by design.
_backend_selected: bool = False

# Guards the unencrypted-storage notice so it logs at most once per process.
_unencrypted_notice_logged: bool = False


def _iter_candidate_backends(backend: object) -> list[object]:
    """Flatten a backend, expanding a ChainerBackend into its children.

    ``keyring``'s default resolver is a ``ChainerBackend`` that delegates
    to the highest-priority viable backend. Once ``keyrings.alt`` is
    installed, that chain can include the interactive ``EncryptedKeyring``
    -- which we must NOT treat as a usable "native" vault. Flattening lets
    us inspect what the chain would actually use.
    """
    children = getattr(backend, "backends", None)
    if children:
        out: list[object] = []
        for child in children:
            out.extend(_iter_candidate_backends(child))
        return out
    return [backend]


def _is_secret_service(backend: object) -> bool:
    """True only for the genuine OS Secret Service backend on Linux."""
    name = type(backend).__module__ + "." + type(backend).__name__
    return "secretservice" in name.lower()


def _native_backend_works() -> bool:
    """Return True only if a genuine Secret Service vault is usable.

    We deliberately do NOT accept file backends from ``keyrings.alt`` here
    (plaintext or encrypted): the encrypted one prompts for a password and
    the plaintext one we want to manage ourselves with locked-down paths.
    So this returns True only when the resolved chain contains a working
    Secret Service backend.

    The probe is guarded against blocking on input: if any backend tries
    to read a password interactively (``getpass``), stdin is pointed at
    ``/dev/null`` so it raises EOF instead of hanging, and we report the
    backend as unusable.
    """
    try:
        resolved = keyring.get_keyring()
    except Exception:  # pragma: no cover - defensive
        return False

    candidates = _iter_candidate_backends(resolved)
    if not any(_is_secret_service(b) for b in candidates):
        return False

    probe_service = "mgdio:__backend_probe__"
    probe_user = "probe"
    with _no_interactive_stdin():
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


def _warn_unencrypted_write_once(file_path: str) -> None:
    """Warn (once per process) that a credential was stored unencrypted.

    Fired only when a credential is actually *written* (i.e. during an
    auth/setup flow), not on every read. Normal functionality that only
    reads tokens stays silent. WARNING level because it is a real,
    setup-time security notice the user should see.
    """
    global _unencrypted_notice_logged
    if _unencrypted_notice_logged:
        return
    _unencrypted_notice_logged = True
    logger.warning(
        "No OS keyring available; storing credentials UNENCRYPTED at %s "
        "(chmod 600, dir chmod 700). Set MGDIO_KEYRING_PLAINTEXT=0 for an "
        "encrypted store (prompts for a password every run, so it is "
        "unsuitable for cron).",
        file_path,
    )


def _make_locked_plaintext_keyring(base_cls: type) -> object:
    """Return a PlaintextKeyring instance that ``chmod 600``s after writes.

    ``keyrings.alt`` creates the store file lazily on first write, so a
    one-shot ``chmod`` at selection time can't lock a file that doesn't
    exist yet. Subclass ``set_password`` to re-apply ``0o600`` right after
    each write, guaranteeing the unencrypted token file is owner-only even
    if it is later copied out of the (``0o700``) parent directory.

    Writing is also the only moment the unencrypted-storage warning is
    relevant -- it fires here (once per process), so commands that merely
    *read* a token never emit it.
    """

    class _LockedPlaintextKeyring(base_cls):  # type: ignore[valid-type,misc]
        def set_password(self, service: str, username: str, password: str):
            result = super().set_password(service, username, password)
            _lock_down(Path(self.file_path))
            _warn_unencrypted_write_once(str(self.file_path))
            return result

    return _LockedPlaintextKeyring()


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
        backend = _make_locked_plaintext_keyring(PlaintextKeyring)
        backend.file_path = str(fallback_dir / "mgdio_plaintext.cfg")
        keyring.set_keyring(backend)
        _lock_down(Path(backend.file_path))
        # Note: selecting the backend is SILENT. The unencrypted-storage
        # warning fires only when a credential is actually written (see
        # _LockedPlaintextKeyring.set_password), so read-only commands
        # never emit it.
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
