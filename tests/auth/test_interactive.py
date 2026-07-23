"""Unit tests for ``mgdio.auth._interactive`` (non-interactive guard)."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from mgdio.auth import _interactive
from mgdio.exceptions import MgdioInteractionRequiredError


def _set_tty(monkeypatch, value: bool) -> None:
    monkeypatch.setattr(sys, "stdin", MagicMock(isatty=lambda: value))


class TestInteractiveAllowed:
    @pytest.mark.parametrize("value", ["1", "true", "TRUE", " yes "])
    def test_env_forbids_even_with_tty(self, monkeypatch, value):
        monkeypatch.setenv("MGDIO_NONINTERACTIVE", value)
        _set_tty(monkeypatch, True)
        assert _interactive.interactive_allowed() is False

    @pytest.mark.parametrize("value", ["0", "false", "No"])
    def test_env_allows_even_without_tty(self, monkeypatch, value):
        monkeypatch.setenv("MGDIO_NONINTERACTIVE", value)
        _set_tty(monkeypatch, False)
        assert _interactive.interactive_allowed() is True

    def test_unset_env_falls_back_to_tty_heuristic(self, monkeypatch):
        monkeypatch.delenv("MGDIO_NONINTERACTIVE", raising=False)
        _set_tty(monkeypatch, True)
        assert _interactive.interactive_allowed() is True
        _set_tty(monkeypatch, False)
        assert _interactive.interactive_allowed() is False

    def test_unrecognized_env_value_falls_back_to_tty_heuristic(self, monkeypatch):
        monkeypatch.setenv("MGDIO_NONINTERACTIVE", "banana")
        _set_tty(monkeypatch, False)
        assert _interactive.interactive_allowed() is False

    def test_broken_stdin_means_not_allowed(self, monkeypatch):
        monkeypatch.delenv("MGDIO_NONINTERACTIVE", raising=False)
        monkeypatch.setattr(sys, "stdin", None)
        assert _interactive.interactive_allowed() is False


class TestRequireInteractive:
    def test_noop_when_allowed(self, monkeypatch):
        monkeypatch.setenv("MGDIO_NONINTERACTIVE", "0")
        _interactive.require_interactive("Whoop", "mgdio auth whoop", "no token")

    def test_raises_with_actionable_message_when_forbidden(self, monkeypatch):
        monkeypatch.setenv("MGDIO_NONINTERACTIVE", "1")
        with pytest.raises(MgdioInteractionRequiredError) as excinfo:
            _interactive.require_interactive(
                "Whoop", "mgdio auth whoop", "token refresh was rejected"
            )
        message = str(excinfo.value)
        assert "Whoop" in message
        assert "token refresh was rejected" in message
        assert "mgdio auth whoop" in message
