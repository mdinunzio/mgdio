"""Tests for :mod:`mgdio.keyring_backend` auto-selection logic."""

from __future__ import annotations

import sys
import types

import pytest

from mgdio import keyring_backend


@pytest.fixture(autouse=True)
def _reset_selection_flag(monkeypatch):
    """Each test starts with backend selection un-run."""
    monkeypatch.setattr(keyring_backend, "_backend_selected", False)
    monkeypatch.setattr(keyring_backend, "_unencrypted_notice_logged", False)
    # Clear env vars that influence selection so tests are hermetic.
    for var in (
        "MGDIO_KEYRING_BACKEND",
        "PYTHON_KEYRING_BACKEND",
        "MGDIO_KEYRING_PLAINTEXT",
    ):
        monkeypatch.delenv(var, raising=False)
    yield


def _patch_keyring(monkeypatch, *, set_keyring=None, get_keyring=None):
    """Patch the keyring functions used by the module under test."""
    if set_keyring is not None:
        monkeypatch.setattr(keyring_backend.keyring, "set_keyring", set_keyring)
    if get_keyring is not None:
        monkeypatch.setattr(keyring_backend.keyring, "get_keyring", get_keyring)


class TestExplicitOverride:
    def test_mgdio_var_bridges_to_keyring_var_and_skips_fallback(self, monkeypatch):
        monkeypatch.setenv("MGDIO_KEYRING_BACKEND", "some.backend.Class")
        called = []
        _patch_keyring(monkeypatch, set_keyring=lambda b: called.append(b))

        keyring_backend.ensure_keyring_backend()

        # Bridged so keyring's own resolver can pick it up.
        assert sys.modules  # sanity
        import os

        assert os.environ["PYTHON_KEYRING_BACKEND"] == "some.backend.Class"
        # We must NOT have installed a fallback backend ourselves.
        assert called == []

    def test_python_keyring_var_respected(self, monkeypatch):
        monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "x.y.Z")
        called = []
        _patch_keyring(monkeypatch, set_keyring=lambda b: called.append(b))

        keyring_backend.ensure_keyring_backend()

        assert called == []


class TestNativeBackendWorks:
    def test_no_fallback_when_native_probe_succeeds(self, monkeypatch):
        monkeypatch.setattr(keyring_backend, "_native_backend_works", lambda: True)
        called = []
        _patch_keyring(monkeypatch, set_keyring=lambda b: called.append(b))

        keyring_backend.ensure_keyring_backend()

        assert called == []

    def _secret_service_backend(self):
        """A stand-in object whose type looks like the SecretService backend."""

        class SecretServiceKeyring:
            pass

        SecretServiceKeyring.__module__ = "keyring.backends.SecretService"
        return SecretServiceKeyring()

    def test_probe_roundtrips_and_cleans_up(self, monkeypatch):
        store = {}
        ss = self._secret_service_backend()
        fake = types.SimpleNamespace(
            get_keyring=lambda: ss,
            set_password=lambda s, u, p: store.__setitem__((s, u), p),
            get_password=lambda s, u: store.get((s, u)),
            delete_password=lambda s, u: store.pop((s, u), None),
        )
        monkeypatch.setattr(keyring_backend, "keyring", fake)

        assert keyring_backend._native_backend_works() is True
        # Probe key cleaned up.
        assert store == {}

    def test_probe_false_for_non_secret_service_backend(self, monkeypatch):
        """A plaintext/encrypted file backend is NOT accepted as native."""

        class PlaintextKeyring:
            pass

        PlaintextKeyring.__module__ = "keyrings.alt.file"
        fake = types.SimpleNamespace(get_keyring=lambda: PlaintextKeyring())
        monkeypatch.setattr(keyring_backend, "keyring", fake)

        assert keyring_backend._native_backend_works() is False

    def test_probe_unwraps_chainer_and_finds_secret_service(self, monkeypatch):
        store = {}
        ss = self._secret_service_backend()
        chainer = types.SimpleNamespace(backends=[ss])
        fake = types.SimpleNamespace(
            get_keyring=lambda: chainer,
            set_password=lambda s, u, p: store.__setitem__((s, u), p),
            get_password=lambda s, u: store.get((s, u)),
            delete_password=lambda s, u: store.pop((s, u), None),
        )
        monkeypatch.setattr(keyring_backend, "keyring", fake)

        assert keyring_backend._native_backend_works() is True

    def test_probe_false_when_set_raises(self, monkeypatch):
        def boom(*_a, **_k):
            raise RuntimeError("no secret service")

        ss = self._secret_service_backend()
        fake = types.SimpleNamespace(
            get_keyring=lambda: ss,
            set_password=boom,
            get_password=lambda s, u: None,
            delete_password=lambda s, u: None,
        )
        monkeypatch.setattr(keyring_backend, "keyring", fake)

        assert keyring_backend._native_backend_works() is False

    def test_chainer_with_only_encrypted_is_not_native(self, monkeypatch):
        """An EncryptedKeyring in the chain must not be accepted as native.

        Regression for the headless VPS hang: keyrings.alt's
        EncryptedKeyring prompts for a password, so it must never be
        treated as a usable native vault.
        """

        class EncryptedKeyring:
            pass

        EncryptedKeyring.__module__ = "keyrings.alt.file"
        chainer = types.SimpleNamespace(backends=[EncryptedKeyring()])
        fake = types.SimpleNamespace(get_keyring=lambda: chainer)
        monkeypatch.setattr(keyring_backend, "keyring", fake)

        # No SecretService in the chain -> not native, and we never call
        # set_password (so no getpass prompt could fire).
        assert keyring_backend._native_backend_works() is False


class TestNoInteractiveStdin:
    def test_getpass_gets_eof_instead_of_hanging(self):
        import getpass

        with keyring_backend._no_interactive_stdin():
            with pytest.raises(EOFError):
                # With stdin redirected to /dev/null, getpass hits EOF.
                getpass.getpass("prompt: ")

    def test_stdin_restored_after(self):
        before = sys.stdin
        with keyring_backend._no_interactive_stdin():
            assert sys.stdin is not before
        assert sys.stdin is before


class TestLinuxFallback:
    def test_selects_plaintext_by_default(self, monkeypatch, tmp_path):
        monkeypatch.setattr(keyring_backend.sys, "platform", "linux")
        monkeypatch.setattr(keyring_backend, "_native_backend_works", lambda: False)
        monkeypatch.setattr(keyring_backend, "_fallback_dir", lambda: tmp_path)
        installed = []
        _patch_keyring(monkeypatch, set_keyring=lambda b: installed.append(b))

        keyring_backend.ensure_keyring_backend()

        assert len(installed) == 1
        backend = installed[0]
        # A PlaintextKeyring subclass that locks the file after writes.
        from keyrings.alt.file import PlaintextKeyring

        assert isinstance(backend, PlaintextKeyring)
        # Stored under our locked-down dir.
        assert str(tmp_path) in backend.file_path

    def test_plaintext_chmods_file_after_write(self, monkeypatch, tmp_path):
        monkeypatch.setattr(keyring_backend.sys, "platform", "linux")
        monkeypatch.setattr(keyring_backend, "_native_backend_works", lambda: False)
        monkeypatch.setattr(keyring_backend, "_fallback_dir", lambda: tmp_path)
        installed = []
        _patch_keyring(monkeypatch, set_keyring=lambda b: installed.append(b))

        locked = []
        monkeypatch.setattr(keyring_backend, "_lock_down", lambda p: locked.append(p))

        keyring_backend.ensure_keyring_backend()
        backend = installed[0]
        # Writing a password re-locks the file.
        backend.set_password("svc", "user", "secret")

        # set_password triggered a _lock_down on the store path.
        assert any("mgdio_plaintext.cfg" in str(p) for p in locked)

    def test_selects_encrypted_when_opted_in(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MGDIO_KEYRING_PLAINTEXT", "0")
        monkeypatch.setattr(keyring_backend.sys, "platform", "linux")
        monkeypatch.setattr(keyring_backend, "_native_backend_works", lambda: False)
        monkeypatch.setattr(keyring_backend, "_fallback_dir", lambda: tmp_path)
        installed = []
        _patch_keyring(monkeypatch, set_keyring=lambda b: installed.append(b))

        keyring_backend.ensure_keyring_backend()

        assert len(installed) == 1
        assert type(installed[0]).__name__ == "EncryptedKeyring"

    def test_notifies_about_plaintext_once_at_info(self, monkeypatch, tmp_path, caplog):
        monkeypatch.setattr(keyring_backend.sys, "platform", "linux")
        monkeypatch.setattr(keyring_backend, "_native_backend_works", lambda: False)
        monkeypatch.setattr(keyring_backend, "_fallback_dir", lambda: tmp_path)
        _patch_keyring(monkeypatch, set_keyring=lambda b: None)

        with caplog.at_level("INFO"):
            keyring_backend.ensure_keyring_backend()
            # A second selection pass must NOT re-log (once per process).
            monkeypatch.setattr(keyring_backend, "_backend_selected", False)
            keyring_backend.ensure_keyring_backend()

        notices = [r for r in caplog.records if "UNENCRYPTED" in r.message]
        assert len(notices) == 1
        assert notices[0].levelname == "INFO"


class TestNonLinux:
    def test_no_probe_and_no_fallback_on_windows(self, monkeypatch):
        monkeypatch.setattr(keyring_backend.sys, "platform", "win32")
        probed = {"n": 0}

        def _native():
            probed["n"] += 1
            return True

        monkeypatch.setattr(keyring_backend, "_native_backend_works", _native)
        installed = []
        _patch_keyring(monkeypatch, set_keyring=lambda b: installed.append(b))

        keyring_backend.ensure_keyring_backend()

        # On Windows/macOS we trust the native vault: no probe, no fallback.
        assert probed["n"] == 0
        assert installed == []


class TestIdempotency:
    def test_second_call_is_a_noop(self, monkeypatch):
        monkeypatch.setattr(keyring_backend.sys, "platform", "linux")
        calls = {"native": 0}

        def _native():
            calls["native"] += 1
            return True

        monkeypatch.setattr(keyring_backend, "_native_backend_works", _native)

        keyring_backend.ensure_keyring_backend()
        keyring_backend.ensure_keyring_backend()

        # Selection ran only once.
        assert calls["native"] == 1
