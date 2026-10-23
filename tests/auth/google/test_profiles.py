"""Unit tests for ``mgdio.auth.google._profiles`` (slugs, listing, waterfall)."""

from __future__ import annotations

import json

import pytest

from mgdio.auth.google import _profiles as profiles
from mgdio.exceptions import MgdioAuthError
from mgdio.settings import google_vault_key


def _seed(fake_vault, slug: str) -> None:
    """Give ``slug`` a token in the fake vault."""
    fake_vault.set(google_vault_key(slug), json.dumps({"token": "x"}))


class TestValidateSlug:
    @pytest.mark.parametrize("slug", ["a", "svc", "a-b_c", "mdinunziosvc", "x1"])
    def test_accepts_valid(self, slug):
        assert profiles.validate_slug(slug) == slug

    @pytest.mark.parametrize("slug", ["", "Foo", "a.b", "a b", "a@b", "UPPER"])
    def test_rejects_invalid(self, slug):
        with pytest.raises(MgdioAuthError):
            profiles.validate_slug(slug)


class TestProfileHasToken:
    def test_true_when_token_present(self, fake_vault):
        _seed(fake_vault, "svc")
        assert profiles.profile_has_token("svc") is True

    def test_false_when_absent(self, fake_vault):
        assert profiles.profile_has_token("svc") is False


class TestLiveProfiles:
    def test_lists_vault_keys_under_prefix_sorted(self, fake_vault):
        _seed(fake_vault, "beta")
        _seed(fake_vault, "alpha")
        assert profiles.live_profiles() == ["alpha", "beta"]

    def test_ignores_foreign_and_nested_keys(self, fake_vault):
        _seed(fake_vault, "real")
        fake_vault.set("mgdio/google/real/extra", "nested")  # not a profile
        fake_vault.set("mgdio/googleish/x", "other prefix")
        fake_vault.set("other/google/y", "other app")
        assert profiles.live_profiles() == ["real"]

    def test_empty_vault(self, fake_vault):
        assert profiles.live_profiles() == []


class TestResolveProfile:
    # --- branch 1: explicit ---
    def test_explicit_with_token_wins(self, fake_vault, monkeypatch):
        _seed(fake_vault, "svc")
        _seed(fake_vault, "other")
        monkeypatch.setenv("MGDIO_GOOGLE_PROFILE", "other")
        assert profiles.resolve_profile("svc") == "svc"

    def test_explicit_invalid_slug_raises(self, fake_vault):
        with pytest.raises(MgdioAuthError):
            profiles.resolve_profile("Bad Slug")

    def test_explicit_missing_token_raises(self, fake_vault):
        with pytest.raises(MgdioAuthError, match="not found"):
            profiles.resolve_profile("svc")

    # --- branch 2: env var ---
    def test_env_used_when_no_explicit(self, fake_vault, monkeypatch):
        _seed(fake_vault, "svc")
        _seed(fake_vault, "other")
        monkeypatch.setenv("MGDIO_GOOGLE_PROFILE", "svc")
        assert profiles.resolve_profile() == "svc"

    def test_env_missing_token_raises_no_fallthrough(self, fake_vault, monkeypatch):
        _seed(fake_vault, "only")  # a sole profile exists...
        monkeypatch.setenv("MGDIO_GOOGLE_PROFILE", "ghost")  # ...but env names another
        with pytest.raises(MgdioAuthError, match="no token"):
            profiles.resolve_profile()

    # --- branch 3: sole profile ---
    def test_sole_profile_auto_selected(self, fake_vault, monkeypatch):
        monkeypatch.delenv("MGDIO_GOOGLE_PROFILE", raising=False)
        _seed(fake_vault, "only")
        assert profiles.resolve_profile() == "only"

    # --- branch 4: errors ---
    def test_zero_profiles_raises(self, fake_vault, monkeypatch):
        monkeypatch.delenv("MGDIO_GOOGLE_PROFILE", raising=False)
        with pytest.raises(MgdioAuthError, match="no Google profiles"):
            profiles.resolve_profile()

    def test_multiple_profiles_no_selection_raises(self, fake_vault, monkeypatch):
        monkeypatch.delenv("MGDIO_GOOGLE_PROFILE", raising=False)
        _seed(fake_vault, "alpha")
        _seed(fake_vault, "beta")
        with pytest.raises(MgdioAuthError, match="multiple Google profiles"):
            profiles.resolve_profile()

    def test_precedence_explicit_over_env_over_sole(self, fake_vault, monkeypatch):
        _seed(fake_vault, "a")
        _seed(fake_vault, "b")
        _seed(fake_vault, "c")
        monkeypatch.setenv("MGDIO_GOOGLE_PROFILE", "b")
        # explicit beats env
        assert profiles.resolve_profile("a") == "a"
        # env beats (would-be) sole selection (there are 3 anyway)
        assert profiles.resolve_profile() == "b"
