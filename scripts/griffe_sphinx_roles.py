"""Griffe extension: turn Sphinx cross-reference roles into mkdocs links.

mgdio's docstrings are Google-style but cross-reference other objects
with Sphinx roles such as ``:func:`get_credentials``` or
``:mod:`mgdio.settings```. mkdocstrings renders docstrings as Markdown,
where those roles would appear as literal text. This extension rewrites
every role before rendering:

* If the target resolves to a documented ``mgdio`` object, the role
  becomes an autorefs link: ``[`name`][full.dotted.path]``.
* Otherwise (stdlib, third-party, or private module) it becomes plain
  inline code: ```` `name` ````.

It is wired in through ``mkdocs.yml`` (``handlers.python.options.extensions``).
"""

from __future__ import annotations

import re
from typing import Any, Callable, Iterator

import griffe

ROLE_RE = re.compile(
    r":(?:mod|func|class|data|meth|attr|exc|const|obj):`([^`<>]+)`",
)

Resolver = Callable[[str], str | None]


def convert_sphinx_roles(text: str, resolve: Resolver) -> str:
    """Rewrite Sphinx cross-reference roles in ``text`` as Markdown.

    Args:
        text: Docstring text that may contain ``:role:`target``` markup.
        resolve: Callback mapping a target name to the full dotted path of
            a documented object, or ``None`` when no page exists for it.

    Returns:
        ``text`` with each role replaced by ``[`name`][path]`` when the
        target resolves and by ```` `name` ```` otherwise.
    """

    def _substitute(match: re.Match[str]) -> str:
        target = match.group(1)
        # Sphinx's "~" prefix means "display only the last path component".
        name = target.lstrip("~")
        display = name.rsplit(".", 1)[-1] if target.startswith("~") else name
        path = resolve(name)
        if path is None:
            return f"`{display}`"
        return f"[`{display}`][{path}]"

    return ROLE_RE.sub(_substitute, text)


def _is_private_path(path: str) -> bool:
    """Return True if any component of a dotted path is underscore-prefixed."""
    return any(part.startswith("_") for part in path.split("."))


def _exported_targets(pkg: griffe.Module) -> set[str]:
    """Return the target paths of objects re-exported by public modules.

    An object defined in a private module (``mgdio.auth.google._profiles``)
    still gets rendered when a public module imports it and lists it in
    ``__all__``: mkdocstrings documents the alias and registers the
    canonical path as an anchor. Anything else in a private module has no
    anchor and must not be linked.
    """
    exported: set[str] = set()
    for module in _walk(pkg):
        if not module.is_module or _is_private_path(module.path):
            continue
        if module.exports is None:
            continue
        names = {str(export) for export in module.exports}
        for name, member in module.members.items():
            if member.is_alias and name in names:
                exported.add(member.target_path)
    return exported


def resolve_in_package(
    obj: griffe.Object, name: str, pkg: griffe.Module, exported: set[str]
) -> str | None:
    """Resolve ``name`` from ``obj``'s scope to a documented path in ``pkg``.

    Args:
        obj: The object whose docstring mentions ``name``.
        name: The role target, e.g. ``"resolve_profile"`` or
            ``"mgdio.settings.GOOGLE_SCOPES"``.
        pkg: The top-level package being documented.
        exported: Canonical paths re-exported by public modules, from
            :func:`_exported_targets`.

    Returns:
        The dotted path to link to, or ``None`` if the target is outside
        the package, is a private module, or is a private member that no
        public module re-exports.
    """
    try:
        path = obj.resolve(name)
    except griffe.NameResolutionError:
        path = name

    prefix = f"{pkg.name}."
    if path != pkg.name and not path.startswith(prefix):
        return None

    try:
        target = pkg if path == pkg.name else pkg[path[len(prefix) :]]
    except KeyError:
        return None

    if target.is_alias:
        try:
            target = target.final_target
        except griffe.AliasResolutionError:
            return None

    final_path = target.path
    if target.is_module:
        return None if _is_private_path(final_path) else final_path
    if final_path.rsplit(".", 1)[-1].startswith("_"):
        return None
    if _is_private_path(final_path) and final_path not in exported:
        return None
    return final_path


def _walk(obj: griffe.Object) -> Iterator[griffe.Object]:
    """Yield ``obj`` and every non-alias descendant."""
    yield obj
    for member in obj.members.values():
        if not member.is_alias:
            yield from _walk(member)  # type: ignore[arg-type]


class SphinxRolesExtension(griffe.Extension):
    """Rewrite Sphinx roles in every docstring once a package is loaded."""

    def on_package(self, *, pkg: griffe.Module, **kwargs: Any) -> None:
        """Rewrite roles across the whole package tree.

        Args:
            pkg: The fully loaded top-level package.
            **kwargs: Other hook arguments (unused).
        """
        exported = _exported_targets(pkg)
        for obj in _walk(pkg):
            if obj.docstring is None:
                continue
            obj.docstring.value = convert_sphinx_roles(
                obj.docstring.value,
                lambda name, _obj=obj: resolve_in_package(_obj, name, pkg, exported),
            )
