"""Lint-style tests on the bundled SKILL.md files themselves.

Catches drift if someone edits a skill body and accidentally breaks the
frontmatter or omits the safety contract.
"""

from __future__ import annotations

import re

import pytest

from mgdio.skills import iter_skill_dirs

# Claude Code listing budget per docs: description + when_to_use cap at 1536 chars.
DESCRIPTION_BUDGET = 1536

# Phrase every write-capable skill must include in its body so Claude treats
# write operations as requiring user confirmation.
SAFETY_PHRASE = "MUST be confirmed with the user"


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract simple key/value pairs from a SKILL.md's YAML frontmatter.

    Not a real YAML parser -- skills here only use scalar string fields,
    so a tolerant regex is fine and avoids adding a yaml dep just for tests.
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return {}
    body = match.group(1)
    fields: dict[str, str] = {}
    # Match `key: value`, where value can span multiple indented lines.
    for m in re.finditer(
        r"^([a-zA-Z_-]+):\s*(.+?)(?=\n[a-zA-Z_-]+:|\Z)",
        body,
        re.DOTALL | re.MULTILINE,
    ):
        key = m.group(1).strip()
        value = " ".join(m.group(2).split())
        fields[key] = value
    return fields


def _collect_skills() -> list[tuple[str, str, dict[str, str]]]:
    """Return (skill_name, body_text, frontmatter_dict) for every bundled skill."""
    out: list[tuple[str, str, dict[str, str]]] = []
    with iter_skill_dirs() as skill_dirs:
        for path in skill_dirs:
            text = (path / "SKILL.md").read_text(encoding="utf-8")
            out.append((path.name, text, _parse_frontmatter(text)))
    return out


@pytest.fixture(scope="module")
def skills() -> list[tuple[str, str, dict[str, str]]]:
    return _collect_skills()


class TestFrontmatter:
    def test_every_skill_has_frontmatter(self, skills):
        for name, _text, front in skills:
            assert front, f"{name}: SKILL.md is missing or malformed frontmatter"

    def test_every_skill_has_name_field(self, skills):
        for name, _text, front in skills:
            assert "name" in front, f"{name}: no 'name:' in frontmatter"
            assert front["name"], f"{name}: 'name:' is empty"

    def test_every_skill_has_description_field(self, skills):
        for name, _text, front in skills:
            assert "description" in front, f"{name}: no 'description:'"
            assert front["description"], f"{name}: 'description:' is empty"

    def test_frontmatter_name_matches_directory(self, skills):
        for name, _text, front in skills:
            assert front["name"] == name, (
                f"{name}: frontmatter 'name: {front['name']}' doesn't match "
                f"directory name '{name}'"
            )

    def test_description_under_budget(self, skills):
        for name, _text, front in skills:
            assert len(front["description"]) <= DESCRIPTION_BUDGET, (
                f"{name}: description is "
                f"{len(front['description'])} chars (budget {DESCRIPTION_BUDGET})"
            )


class TestSafetyContract:
    def test_every_skill_states_safety_contract(self, skills):
        for name, text, _front in skills:
            assert SAFETY_PHRASE in text, (
                f"{name}: SKILL.md does not contain the safety-contract "
                f"phrase {SAFETY_PHRASE!r}. Every skill that exposes write "
                f"operations must instruct Claude to confirm with the user."
            )


class TestBundledSkillNames:
    def test_exactly_four_bundled_skills(self, skills):
        names = {name for name, _, _ in skills}
        assert names == {
            "mgdio-gmail",
            "mgdio-sheets",
            "mgdio-calendar",
            "mgdio-ynab",
        }
