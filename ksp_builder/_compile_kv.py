"""ksp_builder._compile_kv — compiles Kivy ``.kv`` files into Python modules.

Configured under ``[tool.ksp-builder]``::

    [tool.ksp-builder]
    compile_kv = true

Every ``.kv`` sitting in a package directory is handed to the ``compilekv``
library together with the ``.py`` of the same name beside it, and the module
the two produce is written to the staging directory.  That generated module is
what ships: it carries the hand-written code *and* the widget classes the KV
rules describe, so the ``.kv`` itself is no longer needed at runtime and is
left out of the wheel.

With ``cythonize`` and ``py_to_pyx`` also on, the generated module is staged as
a ``.pyx`` and compiled to an extension instead of shipping as source.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ._packages import (
    NEVER_CONVERTED,
    STAGING_DIR,
    find_packages,
    is_excluded,
    stage_file,
)

__all__ = [
    "KvModule",
    "read_compile_kv",
    "find_kv_sources",
    "compile_kv_modules",
]


@dataclass
class KvModule:
    """One module compiled out of a ``.kv`` file."""

    package: str  # dotted package name, e.g. "myapp.screens"
    name: str  # module name without extension, e.g. "home"
    source: Path  # the generated module, relative to the project root
    kv: Path  # the .kv it was compiled from, relative to the project root
    py: Path | None  # the hand-written .py merged into it, if there was one
    as_pyx: bool  # True when the module was staged for Cython

    @property
    def dotted(self) -> str:
        return f"{self.package}.{self.name}" if self.package else self.name


def read_compile_kv(project_root: Path) -> bool:
    """Whether ``[tool.ksp-builder] compile_kv`` is on."""
    from ._packages import read_section

    return bool(read_section(project_root).get("compile_kv", False))


def _compilekv():
    """The ``compilekv`` library, with a build-time error if it is missing."""
    try:
        import compilekv
    except ImportError as exc:  # pragma: no cover - compilekv is a dependency
        raise RuntimeError(
            "ksp-builder: compile_kv is enabled but compilekv is not installed."
        ) from exc
    return compilekv


def find_kv_sources(project_root: Path) -> list[tuple[str, Path]]:
    """The ``(package, kv path)`` pairs this project can compile.

    Only ``.kv`` files directly inside a package are collected — a compiled KV
    file becomes an importable module, and there is no module name for one
    sitting in a plain data directory.  Those stay ordinary package data.
    """
    find_kv_files = _compilekv().find_kv_files

    sources: list[tuple[str, Path]] = []
    for package, directory in sorted(find_packages(project_root).items()):
        for kv_path in find_kv_files(directory, recursive=False):
            sources.append((package, kv_path))
    return sources


def compile_kv_modules(
    project_root: Path,
    *,
    as_pyx: bool = False,
    exclude: Sequence[str] = (),
) -> list[KvModule]:
    """Compile every package ``.kv`` into the staging directory.

    ``as_pyx`` stages the result for Cython instead of shipping it as source.
    ``exclude`` is ``cythonize_exclude``: a module it names is still compiled
    out of its KV file, it just stays a plain ``.py``.
    """
    sources = find_kv_sources(project_root)
    if not sources:
        return []

    compilekv = _compilekv()
    KvCompileError = compilekv.KvCompileError
    source_path_for = compilekv.source_path_for

    compiler = compilekv.default_compiler()
    patterns = list(exclude)
    modules: list[KvModule] = []

    for package, kv_path in sources:
        relative_kv = kv_path.relative_to(project_root)
        py_path = source_path_for(kv_path)
        has_py = py_path.is_file()
        py_source = py_path.read_text(encoding="utf-8") if has_py else ""

        try:
            generated = compiler.compile_source(
                kv_path.read_text(encoding="utf-8"), py_source
            )
        except KvCompileError as exc:
            raise RuntimeError(f"ksp-builder: cannot compile {relative_kv}: {exc}") from exc

        relative_py = py_path.relative_to(project_root) if has_py else None
        staged_as_pyx = as_pyx and _compilable(kv_path.stem, relative_kv, relative_py, patterns)
        suffix = ".pyx" if staged_as_pyx else ".py"
        staged = Path(STAGING_DIR, *package.split("."), f"{kv_path.stem}{suffix}")
        stage_file(project_root / staged, generated.encode("utf-8"))

        modules.append(
            KvModule(
                package=package,
                name=kv_path.stem,
                source=staged,
                kv=relative_kv,
                py=relative_py,
                as_pyx=staged_as_pyx,
            )
        )

    return modules


def _compilable(
    stem: str,
    relative_kv: Path,
    relative_py: Path | None,
    patterns: list[str],
) -> bool:
    """Whether the module built from this KV file may become an extension."""
    if stem in NEVER_CONVERTED:
        return False
    if is_excluded(relative_kv, patterns):
        return False
    return relative_py is None or not is_excluded(relative_py, patterns)
