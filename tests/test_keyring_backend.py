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

    def test_probe_roundtrips_and_cleans_up(self, monkeypatch):
        store = {}
        fake = types.SimpleNamespace(
            get_keyring=lambda: types.SimpleNamespace(),
            set_password=lambda s, u, p: store.__setitem__((s, u), p),
            get_password=lambda s, u: store.get((s, u)),
            delete_password=lambda s, u: store.pop((s, u), None),
        )
        monkeypatch.setattr(keyring_backend, "keyring", fake)

        assert keyring_backend._native_backend_works() is True
        # Probe key cleaned up.
        assert store == {}

    def test_probe_false_for_fail_backend(self, monkeypatch):
        class FailKeyring:
            pass

        FailKeyring.__module__ = "keyring.backends.fail"
        fake = types.SimpleNamespace(get_keyring=lambda: FailKeyring())
        monkeypatch.setattr(keyring_backend, "keyring", fake)

        assert keyring_backend._native_backend_works() is False

    def test_probe_false_when_set_raises(self, monkeypatch):
        def boom(*_a, **_k):
            raise RuntimeError("no secret service")

        fake = types.SimpleNamespace(
            get_keyring=lambda: types.SimpleNamespace(),
            set_password=boom,
            get_password=lambda s, u: None,
            delete_password=lambda s, u: None,
        )
        monkeypatch.setattr(keyring_backend, "keyring", fake)

        assert keyring_backend._native_backend_works() is False


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
        assert type(backend).__name__ == "PlaintextKeyring"
        # Stored under our locked-down dir.
        assert str(tmp_path) in backend.file_path

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

    def test_warns_about_plaintext(self, monkeypatch, tmp_path, caplog):
        monkeypatch.setattr(keyring_backend.sys, "platform", "linux")
        monkeypatch.setattr(keyring_backend, "_native_backend_works", lambda: False)
        monkeypatch.setattr(keyring_backend, "_fallback_dir", lambda: tmp_path)
        _patch_keyring(monkeypatch, set_keyring=lambda b: None)

        with caplog.at_level("WARNING"):
            keyring_backend.ensure_keyring_backend()

        assert any("UNENCRYPTED" in r.message for r in caplog.records)


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
