"""Unit tests for ``mgdio.auth.google._profiles`` (slugs, index, waterfall)."""

from __future__ import annotations

import json

import pytest

from mgdio.auth.google import _profiles as profiles
from mgdio.exceptions import MgdioAuthError
from mgdio.settings import GOOGLE_KEYRING_USERNAME, google_keyring_service


def _seed(fake_keyring, slug: str) -> None:
    """Give ``slug`` a token in the fake keyring and add it to the index."""
    fake_keyring[(google_keyring_service(slug), GOOGLE_KEYRING_USERNAME)] = json.dumps(
        {"token": "x"}
    )
    profiles.add_to_index(slug)


class TestValidateSlug:
    @pytest.mark.parametrize("slug", ["a", "svc", "a-b_c", "mdinunziosvc", "x1"])
    def test_accepts_valid(self, slug):
        assert profiles.validate_slug(slug) == slug

    @pytest.mark.parametrize("slug", ["", "Foo", "a.b", "a b", "a@b", "UPPER"])
    def test_rejects_invalid(self, slug):
        with pytest.raises(MgdioAuthError):
            profiles.validate_slug(slug)


class TestIndex:
    def test_add_read_remove_roundtrip(self, tmp_appdata):
        assert profiles.read_index() == []
        profiles.add_to_index("beta")
        profiles.add_to_index("alpha")
        profiles.add_to_index("alpha")  # idempotent
        assert profiles.read_index() == ["alpha", "beta"]  # sorted, deduped
        profiles.remove_from_index("alpha")
        assert profiles.read_index() == ["beta"]

    def test_corrupt_index_reads_as_empty(self, tmp_appdata):
        from mgdio import settings

        settings.GOOGLE_PROFILE_INDEX_PATH.write_text("{not json", encoding="utf-8")
        assert profiles.read_index() == []

    def test_write_leaves_no_tmp_file(self, tmp_appdata):
        profiles.add_to_index("alpha")
        leftovers = list(tmp_appdata.glob("google/*.tmp"))
        assert leftovers == []


class TestProfileHasToken:
    def test_true_when_token_present(self, tmp_appdata, fake_keyring):
        _seed(fake_keyring, "svc")
        assert profiles.profile_has_token("svc") is True

    def test_false_when_absent(self, tmp_appdata, fake_keyring):
        assert profiles.profile_has_token("svc") is False


class TestLiveProfiles:
    def test_intersects_index_with_tokens(self, tmp_appdata, fake_keyring):
        _seed(fake_keyring, "real")
        profiles.add_to_index("ghost")  # indexed but no token
        assert profiles.live_profiles() == ["real"]


class TestResolveProfile:
    # --- branch 1: explicit ---
    def test_explicit_with_token_wins(self, tmp_appdata, fake_keyring, monkeypatch):
        _seed(fake_keyring, "svc")
        _seed(fake_keyring, "other")
        monkeypatch.setenv("MGDIO_GOOGLE_PROFILE", "other")
        assert profiles.resolve_profile("svc") == "svc"

    def test_explicit_invalid_slug_raises(self, tmp_appdata, fake_keyring):
        with pytest.raises(MgdioAuthError):
            profiles.resolve_profile("Bad Slug")

    def test_explicit_missing_token_raises(self, tmp_appdata, fake_keyring):
        with pytest.raises(MgdioAuthError, match="not found"):
            profiles.resolve_profile("svc")

    # --- branch 2: env var ---
    def test_env_used_when_no_explicit(self, tmp_appdata, fake_keyring, monkeypatch):
        _seed(fake_keyring, "svc")
        _seed(fake_keyring, "other")
        monkeypatch.setenv("MGDIO_GOOGLE_PROFILE", "svc")
        assert profiles.resolve_profile() == "svc"

    def test_env_missing_token_raises_no_fallthrough(
        self, tmp_appdata, fake_keyring, monkeypatch
    ):
        _seed(fake_keyring, "only")  # a sole profile exists...
        monkeypatch.setenv("MGDIO_GOOGLE_PROFILE", "ghost")  # ...but env names another
        with pytest.raises(MgdioAuthError, match="no token"):
            profiles.resolve_profile()

    # --- branch 3: sole profile ---
    def test_sole_profile_auto_selected(self, tmp_appdata, fake_keyring, monkeypatch):
        monkeypatch.delenv("MGDIO_GOOGLE_PROFILE", raising=False)
        _seed(fake_keyring, "only")
        assert profiles.resolve_profile() == "only"

    # --- branch 4: errors ---
    def test_zero_profiles_raises(self, tmp_appdata, fake_keyring, monkeypatch):
        monkeypatch.delenv("MGDIO_GOOGLE_PROFILE", raising=False)
        with pytest.raises(MgdioAuthError, match="no Google profiles"):
            profiles.resolve_profile()

    def test_multiple_profiles_no_selection_raises(
        self, tmp_appdata, fake_keyring, monkeypatch
    ):
        monkeypatch.delenv("MGDIO_GOOGLE_PROFILE", raising=False)
        _seed(fake_keyring, "alpha")
        _seed(fake_keyring, "beta")
        with pytest.raises(MgdioAuthError, match="multiple Google profiles"):
            profiles.resolve_profile()

    def test_precedence_explicit_over_env_over_sole(
        self, tmp_appdata, fake_keyring, monkeypatch
    ):
        _seed(fake_keyring, "a")
        _seed(fake_keyring, "b")
        _seed(fake_keyring, "c")
        monkeypatch.setenv("MGDIO_GOOGLE_PROFILE", "b")
        # explicit beats env
        assert profiles.resolve_profile("a") == "a"
        # env beats (would-be) sole selection (there are 3 anyway)
        assert profiles.resolve_profile() == "b"


class TestDetectLegacyToken:
    def test_true_when_legacy_present(self, tmp_appdata, fake_keyring):
        from mgdio.settings import LEGACY_GOOGLE_KEYRING_SERVICE

        fake_keyring[(LEGACY_GOOGLE_KEYRING_SERVICE, GOOGLE_KEYRING_USERNAME)] = "x"
        assert profiles.detect_legacy_token() is True

    def test_false_when_absent(self, tmp_appdata, fake_keyring):
        assert profiles.detect_legacy_token() is False
