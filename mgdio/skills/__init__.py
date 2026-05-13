"""Bundled Claude Code skills shipped inside the wheel.

Each subdirectory is a Claude Code skill (an `SKILL.md` plus optional
supporting files). They are copied into the user's `.claude/skills/`
directory by ``mgdio skills deploy`` (per-project) or ``mgdio skills
deploy --global`` (cross-project).

Access on-disk paths via :func:`iter_skill_dirs` -- which uses
``importlib.resources`` so it works for editable installs, wheels, and
zipapp uniformly.
"""

from __future__ import annotations

from contextlib import contextmanager
from importlib.resources import as_file, files
from pathlib import Path
from typing import Iterator


@contextmanager
def iter_skill_dirs() -> Iterator[list[Path]]:
    """Yield real on-disk paths to each bundled skill directory.

    The yielded list is sorted by directory name for deterministic
    iteration. Paths are valid only for the duration of the context
    manager: when mgdio is installed from a wheel, ``importlib.resources``
    may extract the directory tree into a temp location, which gets
    cleaned up on exit.

    Yields:
        A list of :class:`pathlib.Path` objects, one per skill directory
        that contains a ``SKILL.md`` file.
    """
    root = files(__name__)
    with as_file(root) as root_path:
        skills = sorted(
            p
            for p in Path(root_path).iterdir()
            if p.is_dir() and (p / "SKILL.md").exists()
        )
        yield skills
