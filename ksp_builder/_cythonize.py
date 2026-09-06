"""ksp_builder._cythonize — compiles package sources with Cython.

Port of the ``cythonized_app`` setup.py concept to the PEP 517 backend, where
there is no ``setup.py`` to declare ``ext_modules`` in.  Configured under
``[tool.ksp-builder]``::

    [tool.ksp-builder]
    cythonize = true
    py_to_pyx = true

``cythonize`` compiles the ``.pyx`` sources already in your packages.
``py_to_pyx`` additionally copies each ``.py`` module to the staging directory
as a ``.pyx`` and compiles that too — it does nothing on its own, both keys
must be on for ``.py`` modules to be converted.

Package layout still comes from ``[tool.setuptools]`` (``packages`` and
``package-dir``, or setuptools' own src/flat auto-discovery); this module only
adds the Cython switches.  ``__init__.py`` and ``__main__.py`` are never
converted, so packages stay importable and ``python -m <package>`` keeps
working, and top-level modules (``py-modules``) are left alone.

The extensions collected here are handed to setuptools by
:mod:`ksp_builder._build`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Collection

from ._packages import (
    NEVER_CONVERTED,
    STAGING_DIR,
    find_packages,
    is_excluded,
    read_section,
    stage_file,
)

__all__ = [
    "DEFAULT_DIRECTIVES",
    "CythonizeConfig",
    "CyModule",
    "read_cythonize_config",
    "collect_modules",
    "build_extensions",
]

#: Applied before any user-supplied ``cythonize_directives``.
DEFAULT_DIRECTIVES: dict[str, Any] = {"language_level": "3"}


@dataclass
class CythonizeConfig:
    """The Cython-related keys of ``[tool.ksp-builder]``."""

    cythonize: bool = False
    py_to_pyx: bool = False
    exclude: list[str] = field(default_factory=list)
    keep_py: bool = False
    directives: dict[str, Any] = field(default_factory=dict)


@dataclass
class CyModule:
    """One module to compile into an extension."""

    package: str  # dotted package name, e.g. "myapp.utils"
    name: str  # module name without extension, e.g. "helpers"
    source: Path  # the .pyx to hand to Cython, relative to the project root
    origin: Path  # the file it came from, relative to the project root
    converted: bool  # True when the .pyx was generated into the staging dir

    @property
    def dotted(self) -> str:
        return f"{self.package}.{self.name}" if self.package else self.name


def read_cythonize_config(project_root: Path) -> CythonizeConfig | None:
    """Read the Cython keys from ``[tool.ksp-builder]``.

    Returns None if pyproject.toml is absent or neither switch is requested.
    """
    section = read_section(project_root)

    cythonize = bool(section.get("cythonize", False))
    py_to_pyx = bool(section.get("py_to_pyx", False))
    if not cythonize and not py_to_pyx:
        return None

    directives = dict(DEFAULT_DIRECTIVES)
    directives.update(section.get("cythonize_directives", {}))

    return CythonizeConfig(
        cythonize=cythonize,
        py_to_pyx=py_to_pyx,
        exclude=list(section.get("cythonize_exclude", [])),
        keep_py=bool(section.get("cythonize_keep_py", False)),
        directives=directives,
    )


# ---------------------------------------------------------------------------
# Source collection
# ---------------------------------------------------------------------------

def collect_modules(
    project_root: Path,
    config: CythonizeConfig,
    *,
    allow_py_to_pyx: bool = True,
    skip: Collection[tuple[str, str]] = (),
) -> list[CyModule]:
    """List the modules to compile, staging ``.py`` sources as ``.pyx``.

    ``.pyx`` files already in the tree are compiled whenever ``cythonize`` is
    on.  ``.py`` modules are converted only when ``py_to_pyx`` is *also* on and
    the caller allows it.  ``skip`` names ``(package, module)`` pairs another
    step already produced — a module compiled out of a ``.kv`` file supersedes
    the ``.py`` that went into it.
    """
    if not config.cythonize:
        return []

    convert_py = config.py_to_pyx and allow_py_to_pyx
    skipped = set(skip)
    modules: list[CyModule] = []

    for package, directory in sorted(find_packages(project_root).items()):
        pyx_names = {p.stem for p in directory.glob("*.pyx")}

        for source in sorted(directory.glob("*.pyx")):
            if (package, source.stem) in skipped:
                continue
            modules.append(
                CyModule(
                    package=package,
                    name=source.stem,
                    source=source.relative_to(project_root),
                    origin=source.relative_to(project_root),
                    converted=False,
                )
            )

        if not convert_py:
            continue

        for source in sorted(directory.glob("*.py")):
            if source.stem in NEVER_CONVERTED or source.stem in pyx_names:
                continue
            if (package, source.stem) in skipped:
                continue
            relative = source.relative_to(project_root)
            if is_excluded(relative, config.exclude):
                continue
            staged = Path(STAGING_DIR, *package.split("."), f"{source.stem}.pyx")
            stage_file(project_root / staged, source.read_bytes())
            modules.append(
                CyModule(
                    package=package,
                    name=source.stem,
                    source=staged,
                    origin=relative,
                    converted=True,
                )
            )

    return modules


# ---------------------------------------------------------------------------
# Handing the sources to Cython
# ---------------------------------------------------------------------------

def build_extensions(modules: list[CyModule], config: CythonizeConfig) -> list:
    """Run ``cythonize()`` over the collected modules."""
    try:
        from Cython.Build import cythonize as run_cythonize
    except ImportError as exc:  # pragma: no cover - cython is a hard dependency
        raise RuntimeError(
            "ksp-builder: cythonize is enabled but Cython is not installed."
        ) from exc
    from setuptools import Extension

    def extensions(group: list[CyModule]) -> list:
        return [Extension(m.dotted, [m.source.as_posix()]) for m in group]

    def compile(group: list[CyModule], build_dir: str | None) -> list:
        if not group:
            return []
        return run_cythonize(
            extensions(group),
            build_dir=build_dir,
            compiler_directives=config.directives,
        )

    # Cython writes the generated C to ``build_dir / <path of the source>``.
    # Staged sources already live under the staging directory, so giving them a
    # build_dir would repeat it (.dist_src/.dist_src/pkg/mod.c); their C belongs
    # next to the .pyx it came from.  In-tree .pyx do need redirecting, or the
    # .c lands in the package directory and gets shipped in the wheel.
    staged = [m for m in modules if m.converted]
    in_tree = [m for m in modules if not m.converted]
    return compile(staged, None) + compile(in_tree, STAGING_DIR)
