"""Unit tests for ``mgdio.auth._keyring`` (robust vault writes/deletes).

The macOS stale-item scenario these helpers exist for: the Keychain
binds each item's ACL to the binary that created it, so after a .venv
rebuild ``keyring.set_password``/``delete_password`` fail with
``errSecInvalidOwnerEdit`` (-25244) even though the item is visible.
Recovery is deleting the item via Apple's ``security`` CLI (not subject
to the item ACL) and retrying.

All tests run against an in-memory fake backend -- the real OS vault is
never touched -- and the ``security`` subprocess is always mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import keyring as real_keyring
import pytest

from mgdio.auth import _keyring
from mgdio.exceptions import MgdioKeyringError

SERVICE = "mgdio:test:svc"
USERNAME = "oauth_token"


class _FakeVault:
    """In-memory keyring stand-in with per-entry set/delete refusal.

    ``refuse_set``/``refuse_delete`` model the macOS stale-ACL state:
    the entry is readable but writes/deletes raise. ``unlock()`` models
    the stale item having been removed out-of-band (``security`` CLI).
    """

    errors = real_keyring.errors

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}
        self.refuse_set = False
        self.refuse_delete = False
        self.set_calls = 0

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.set_calls += 1
        if self.refuse_set:
            raise real_keyring.errors.PasswordSetError(
                "Can't store password on keychain: (-25244, 'Unknown Error')"
            )
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if self.refuse_delete:
            raise real_keyring.errors.PasswordDeleteError("(-25244, 'Unknown Error')")
        try:
            del self.store[(service, username)]
        except KeyError as exc:
            raise real_keyring.errors.PasswordDeleteError(str(exc)) from exc

    def unlock(self) -> None:
        self.refuse_set = False
        self.refuse_delete = False


@pytest.fixture
def vault(monkeypatch) -> _FakeVault:
    fake = _FakeVault()
    monkeypatch.setattr(_keyring, "keyring", fake)
    return fake


@pytest.fixture
def security_cli(monkeypatch, vault) -> MagicMock:
    """Mock the ``security`` CLI as if on macOS with the Keychain backend.

    A successful run removes the refusal from the fake vault (and the
    entry itself), mirroring what the real CLI does to a stale item.
    """
    monkeypatch.setattr(_keyring, "_using_macos_keychain", lambda: True)

    def _run(cmd, **kwargs):
        vault.unlock()
        vault.store.pop((cmd[3], cmd[5]), None)
        return MagicMock(returncode=0, stderr="")

    runner = MagicMock(side_effect=_run)
    monkeypatch.setattr(_keyring.subprocess, "run", runner)
    return runner


class TestSetPassword:
    def test_stores_value_on_happy_path(self, vault):
        _keyring.set_password(SERVICE, USERNAME, "tok")
        assert vault.store[(SERVICE, USERNAME)] == "tok"

    def test_recovers_from_stale_macos_item(self, vault, security_cli):
        vault.store[(SERVICE, USERNAME)] = "old-tok"
        vault.refuse_set = True

        _keyring.set_password(SERVICE, USERNAME, "new-tok")

        security_cli.assert_called_once()
        cmd = security_cli.call_args.args[0]
        assert cmd[:2] == ["security", "delete-generic-password"]
        assert SERVICE in cmd and USERNAME in cmd
        assert vault.store[(SERVICE, USERNAME)] == "new-tok"

    def test_raises_with_manual_fix_when_recovery_fails(
        self, vault, security_cli, monkeypatch
    ):
        vault.refuse_set = True
        security_cli.side_effect = None
        security_cli.return_value = MagicMock(returncode=1, stderr="denied")

        with pytest.raises(MgdioKeyringError) as excinfo:
            _keyring.set_password(SERVICE, USERNAME, "tok")

        assert f'security delete-generic-password -s "{SERVICE}"' in str(excinfo.value)

    def test_non_macos_failure_raises_without_running_security(
        self, vault, monkeypatch
    ):
        monkeypatch.setattr(_keyring, "_using_macos_keychain", lambda: False)
        runner = MagicMock()
        monkeypatch.setattr(_keyring.subprocess, "run", runner)
        vault.refuse_set = True

        with pytest.raises(MgdioKeyringError):
            _keyring.set_password(SERVICE, USERNAME, "tok")
        runner.assert_not_called()

    def test_raises_when_retry_after_recovery_still_fails(
        self, vault, security_cli, monkeypatch
    ):
        vault.refuse_set = True
        # Recovery "succeeds" but the vault keeps refusing writes.
        security_cli.side_effect = None
        security_cli.return_value = MagicMock(returncode=0, stderr="")

        with pytest.raises(MgdioKeyringError):
            _keyring.set_password(SERVICE, USERNAME, "tok")
        assert vault.set_calls == 2


class TestDeletePassword:
    def test_deletes_existing_entry(self, vault):
        vault.store[(SERVICE, USERNAME)] = "tok"
        _keyring.delete_password(SERVICE, USERNAME)
        assert (SERVICE, USERNAME) not in vault.store

    def test_silent_when_entry_absent(self, vault):
        _keyring.delete_password(SERVICE, USERNAME)

    def test_recovers_from_stale_macos_item(self, vault, security_cli):
        vault.store[(SERVICE, USERNAME)] = "tok"
        vault.refuse_delete = True

        _keyring.delete_password(SERVICE, USERNAME)

        security_cli.assert_called_once()
        assert (SERVICE, USERNAME) not in vault.store

    def test_raises_when_refused_and_unrecoverable(self, vault, security_cli):
        vault.store[(SERVICE, USERNAME)] = "tok"
        vault.refuse_delete = True
        security_cli.side_effect = None
        security_cli.return_value = MagicMock(returncode=1, stderr="denied")

        with pytest.raises(MgdioKeyringError):
            _keyring.delete_password(SERVICE, USERNAME)


class TestEnsureWritable:
    def test_noop_when_entry_absent(self, vault):
        _keyring.ensure_writable(SERVICE, USERNAME)
        assert vault.set_calls == 0

    def test_rewrites_existing_entry_with_same_value(self, vault):
        vault.store[(SERVICE, USERNAME)] = "tok"
        _keyring.ensure_writable(SERVICE, USERNAME)
        assert vault.store[(SERVICE, USERNAME)] == "tok"
        assert vault.set_calls == 1

    def test_recovers_stale_item_and_preserves_value(self, vault, security_cli):
        vault.store[(SERVICE, USERNAME)] = "tok"
        vault.refuse_set = True

        _keyring.ensure_writable(SERVICE, USERNAME)

        security_cli.assert_called_once()
        assert vault.store[(SERVICE, USERNAME)] == "tok"

    def test_raises_before_flow_when_unrecoverable(self, vault, security_cli):
        vault.store[(SERVICE, USERNAME)] = "tok"
        vault.refuse_set = True
        security_cli.side_effect = None
        security_cli.return_value = MagicMock(returncode=1, stderr="denied")

        with pytest.raises(MgdioKeyringError):
            _keyring.ensure_writable(SERVICE, USERNAME)


class TestForceDeleteMacosItem:
    def test_not_found_exit_counts_as_gone(self, vault, security_cli):
        security_cli.side_effect = None
        security_cli.return_value = MagicMock(returncode=44, stderr="not found")
        assert _keyring._force_delete_macos_item(SERVICE, USERNAME) is True

    def test_false_when_not_on_macos_keychain(self, vault, monkeypatch):
        monkeypatch.setattr(_keyring, "_using_macos_keychain", lambda: False)
        assert _keyring._force_delete_macos_item(SERVICE, USERNAME) is False

    def test_false_when_security_cli_missing(self, vault, monkeypatch):
        monkeypatch.setattr(_keyring, "_using_macos_keychain", lambda: True)
        monkeypatch.setattr(
            _keyring.subprocess, "run", MagicMock(side_effect=OSError("no such file"))
        )
        assert _keyring._force_delete_macos_item(SERVICE, USERNAME) is False
