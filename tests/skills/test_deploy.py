"""Tests for ``mgdio skills list`` and ``mgdio skills deploy``."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from mgdio import cli as cli_module
from mgdio.skills import iter_skill_dirs

EXPECTED_SKILLS = {
    "mgdio-gmail",
    "mgdio-sheets",
    "mgdio-calendar",
    "mgdio-ynab",
}


class TestIterSkillDirs:
    def test_yields_all_four_bundled_skills(self):
        with iter_skill_dirs() as skill_dirs:
            names = {p.name for p in skill_dirs}
        assert names == EXPECTED_SKILLS

    def test_every_yielded_path_contains_a_skill_md(self):
        with iter_skill_dirs() as skill_dirs:
            for path in skill_dirs:
                skill_md = path / "SKILL.md"
                assert skill_md.exists()
                assert skill_md.stat().st_size > 100


class TestSkillsList:
    def test_lists_all_four_skill_names(self):
        result = CliRunner().invoke(cli_module.cli, ["skills", "list"])
        assert result.exit_code == 0, result.output
        for name in EXPECTED_SKILLS:
            assert name in result.output

    def test_includes_description_text(self):
        result = CliRunner().invoke(cli_module.cli, ["skills", "list"])
        # The first line of each description is rendered indented under the name.
        assert "Read and send Gmail" in result.output
        assert "Google Sheets" in result.output
        assert "Google Calendar" in result.output
        assert "YNAB" in result.output


class TestSkillsDeployLocal:
    def test_writes_to_cwd_dot_claude_skills(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(cli_module.cli, ["skills", "deploy"])

        assert result.exit_code == 0, result.output
        target = tmp_path / ".claude" / "skills"
        assert target.is_dir()
        for name in EXPECTED_SKILLS:
            skill_dir = target / name
            assert skill_dir.is_dir()
            skill_md = skill_dir / "SKILL.md"
            assert skill_md.exists()
            content = skill_md.read_text(encoding="utf-8")
            assert content.startswith("---")
            assert "description:" in content

    def test_creates_target_root_if_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert not (tmp_path / ".claude").exists()

        result = CliRunner().invoke(cli_module.cli, ["skills", "deploy"])

        assert result.exit_code == 0, result.output
        assert (tmp_path / ".claude" / "skills").is_dir()

    def test_skips_existing_skill_without_force(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        existing = tmp_path / ".claude" / "skills" / "mgdio-gmail"
        existing.mkdir(parents=True)
        (existing / "SKILL.md").write_text("STUB CONTENT", encoding="utf-8")

        result = CliRunner().invoke(cli_module.cli, ["skills", "deploy"])

        assert result.exit_code == 0, result.output
        assert "skip" in result.output
        # Stub preserved.
        assert (existing / "SKILL.md").read_text(encoding="utf-8") == "STUB CONTENT"
        # Other three still deployed.
        for name in EXPECTED_SKILLS - {"mgdio-gmail"}:
            assert (tmp_path / ".claude" / "skills" / name / "SKILL.md").exists()

    def test_force_overwrites_existing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        existing = tmp_path / ".claude" / "skills" / "mgdio-gmail"
        existing.mkdir(parents=True)
        (existing / "SKILL.md").write_text("STUB", encoding="utf-8")

        result = CliRunner().invoke(cli_module.cli, ["skills", "deploy", "--force"])

        assert result.exit_code == 0, result.output
        content = (existing / "SKILL.md").read_text(encoding="utf-8")
        # Real skill starts with frontmatter, not "STUB".
        assert content.startswith("---")
        assert "STUB" not in content

    def test_output_summary_counts(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(cli_module.cli, ["skills", "deploy"])
        assert "4 deployed" in result.output
        assert "0 skipped" in result.output


class TestSkillsDeployGlobal:
    def test_writes_to_home_dot_claude_skills(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        # Also chdir somewhere unrelated so we'd notice if --global was ignored.
        unrelated = tmp_path / "unrelated"
        unrelated.mkdir()
        monkeypatch.chdir(unrelated)

        result = CliRunner().invoke(cli_module.cli, ["skills", "deploy", "--global"])

        assert result.exit_code == 0, result.output
        target = tmp_path / ".claude" / "skills"
        assert target.is_dir()
        for name in EXPECTED_SKILLS:
            assert (target / name / "SKILL.md").exists()
        # Confirm --global did NOT also write to the cwd.
        assert not (unrelated / ".claude").exists()
