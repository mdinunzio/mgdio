"""Tests for the mkdocs griffe extension in ``scripts/griffe_sphinx_roles.py``."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

pytest.importorskip("griffe")

REPO_ROOT = Path(__file__).resolve().parents[1]
EXTENSION_PATH = REPO_ROOT / "scripts" / "griffe_sphinx_roles.py"


@pytest.fixture(scope="module")
def ext() -> ModuleType:
    """Load the extension module from its file path (it is not a package)."""
    spec = importlib.util.spec_from_file_location("griffe_sphinx_roles", EXTENSION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resolved_role_becomes_autoref_link(ext: ModuleType) -> None:
    out = ext.convert_sphinx_roles(
        "See :func:`get_credentials`.", lambda name: f"mgdio.auth.google.{name}"
    )
    assert out == "See [`get_credentials`][mgdio.auth.google.get_credentials]."


def test_unresolved_role_becomes_inline_code(ext: ModuleType) -> None:
    out = ext.convert_sphinx_roles("uses :mod:`keyring` here", lambda name: None)
    assert out == "uses `keyring` here"


def test_tilde_prefix_shortens_display_name(ext: ModuleType) -> None:
    out = ext.convert_sphinx_roles(
        ":data:`~mgdio.settings.GOOGLE_SCOPES`", lambda name: name
    )
    assert out == "[`GOOGLE_SCOPES`][mgdio.settings.GOOGLE_SCOPES]"


def test_multiple_roles_and_role_kinds(ext: ModuleType) -> None:
    text = ":class:`MgdioAPIError` vs :exc:`MgdioAuthError`"
    out = ext.convert_sphinx_roles(text, lambda name: f"mgdio.exceptions.{name}")
    assert out == (
        "[`MgdioAPIError`][mgdio.exceptions.MgdioAPIError] vs "
        "[`MgdioAuthError`][mgdio.exceptions.MgdioAuthError]"
    )


def test_plain_text_and_rst_literals_untouched(ext: ModuleType) -> None:
    text = "Stored under ``mgdio:ynab``; see `keyring` docs. Not a role: func:`x`"
    assert ext.convert_sphinx_roles(text, lambda name: name) == text


def test_extension_rewrites_real_package_docstrings(ext: ModuleType) -> None:
    """Load mgdio through griffe with the extension and inspect the result."""
    import griffe

    pkg = griffe.load(
        "mgdio",
        search_paths=[REPO_ROOT],
        extensions=griffe.load_extensions(ext.SphinxRolesExtension()),
    )

    # Public cross-package reference becomes a link.
    google_doc = pkg["auth.google"].docstring.value
    assert ":data:" not in google_doc and ":func:" not in google_doc
    assert (
        "[`mgdio.settings.GOOGLE_SCOPES`][mgdio.settings.GOOGLE_SCOPES]" in google_doc
    )

    # Third-party target degrades to inline code, not a dangling link.
    backend_doc = pkg["keyring_backend"].docstring.value
    assert "`keyring`" in backend_doc and "[`keyring`]" not in backend_doc

    # Private submodule target degrades to inline code.
    headless_doc = pkg["auth.google._headless_flow"].docstring.value
    assert ":mod:" not in headless_doc
    assert "[`mgdio.auth.google._setup_server`]" not in headless_doc

    # A function in a private module that a public module re-exports links
    # to its canonical path (mkdocstrings registers that anchor).
    auth_doc = pkg["auth.google.auth"].docstring.value
    assert "][mgdio.auth.google._profiles.resolve_profile]" in auth_doc

    # A private-module helper that nothing re-exports stays plain code.
    catch_doc = pkg["auth.whoop._setup_server.run_catch_server"].docstring.value
    assert "`run_headless_flow`" in catch_doc
    assert "[`run_headless_flow`]" not in catch_doc
