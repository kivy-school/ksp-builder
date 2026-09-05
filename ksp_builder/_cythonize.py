"""ksp_builder._cythonize — compiles package sources with Cython.

Port of the ``cythonized_app`` setup.py concept to the PEP 517 backend, where
there is no ``setup.py`` to declare ``ext_modules`` in.  Configured under
``[tool.ksp-builder]``::

    [tool.ksp-builder]
    cythonize = true
    py_to_pyx = true

``cythonize`` compiles the ``.pyx`` sources already in your packages.
``py_to_pyx`` additionally copies each ``.py`` module to ``.cy_src/`` as a
``.pyx`` and compiles that too — it does nothing on its own, both keys must be
on for ``.py`` modules to be converted.

Package layout still comes from ``[tool.setuptools]`` (``packages`` and
``package-dir``, or setuptools' own src/flat auto-discovery); this module only
adds the Cython switches.  ``__init__.py`` is never converted, so packages stay
importable, and top-level modules (``py-modules``) are left alone.
"""
from __future__ import annotations

import contextlib
import tomllib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

__all__ = [
    "STAGING_DIR",
    "CythonizeConfig",
    "CyModule",
    "read_cythonize_config",
    "find_packages",
    "collect_modules",
    "cython_build",
]

#: Directory (relative to the project root) holding the generated .pyx sources.
STAGING_DIR = ".cy_src"

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
    converted: bool  # True when a .py was staged as .pyx

    @property
    def dotted(self) -> str:
        return f"{self.package}.{self.name}" if self.package else self.name


def read_cythonize_config(project_root: Path) -> CythonizeConfig | None:
    """Read the Cython keys from ``[tool.ksp-builder]``.

    Returns None if pyproject.toml is absent or neither switch is requested.
    """
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return None

    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    section = data.get("tool", {}).get("ksp-builder", {})

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
# Package discovery — driven by [tool.setuptools], not by our own keys
# ---------------------------------------------------------------------------

_DISCOVERY_SKIP = {
    "build", "dist", "docs", "doc", "tests", "test", "examples", "venv",
    "__pycache__", STAGING_DIR,
}


def find_packages(project_root: Path) -> dict[str, Path]:
    """Map every dotted package name to its directory.

    Honours ``[tool.setuptools] packages`` / ``package-dir``; falls back to the
    same src-layout / flat-layout discovery setuptools performs itself.
    """
    pyproject = project_root / "pyproject.toml"
    data: dict[str, Any] = {}
    if pyproject.exists():
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    setuptools_cfg = data.get("tool", {}).get("setuptools", {})
    package_dir = dict(setuptools_cfg.get("package-dir", {}))
    packages = setuptools_cfg.get("packages")

    if isinstance(packages, list):
        found = {name: _package_path(project_root, package_dir, name) for name in packages}
        return {name: path for name, path in found.items() if path.is_dir()}

    # `packages = { find = { where = [...] } }`, or nothing at all.
    where: list[str] = []
    if isinstance(packages, dict):
        find = packages.get("find", {})
        where = list(find.get("where", []))
    if not where:
        if package_dir.get(""):
            where = [package_dir[""]]
        elif (project_root / "src").is_dir():
            where = ["src"]
        else:
            where = ["."]

    discovered: dict[str, Path] = {}
    for entry in where:
        discovered.update(_discover(project_root / entry))
    return discovered


def _package_path(project_root: Path, package_dir: dict[str, str], dotted: str) -> Path:
    """Resolve a dotted package name to a directory, per setuptools' rules."""
    parts = dotted.split(".")
    for split in range(len(parts), 0, -1):
        prefix = ".".join(parts[:split])
        if prefix in package_dir:
            base = project_root / package_dir[prefix]
            return base.joinpath(*parts[split:])
    root = package_dir.get("", "")
    return project_root.joinpath(root, *parts)


def _discover(where: Path) -> dict[str, Path]:
    """Find packages (directories with an ``__init__.py``) under ``where``."""
    if not where.is_dir():
        return {}

    found: dict[str, Path] = {}

    def walk(directory: Path, prefix: str) -> None:
        for child in sorted(directory.iterdir()):
            if not child.is_dir() or child.name in _DISCOVERY_SKIP:
                continue
            if child.name.startswith("."):
                continue
            if not (child / "__init__.py").exists():
                continue
            dotted = f"{prefix}.{child.name}" if prefix else child.name
            found[dotted] = child
            walk(child, dotted)

    walk(where, "")
    return found


# ---------------------------------------------------------------------------
# Source collection
# ---------------------------------------------------------------------------

def collect_modules(
    project_root: Path,
    config: CythonizeConfig,
    *,
    allow_py_to_pyx: bool = True,
) -> list[CyModule]:
    """List the modules to compile, staging ``.py`` sources as ``.pyx``.

    ``.pyx`` files already in the tree are compiled whenever ``cythonize`` is
    on.  ``.py`` modules are converted only when ``py_to_pyx`` is *also* on and
    the caller allows it.
    """
    if not config.cythonize:
        return []

    convert_py = config.py_to_pyx and allow_py_to_pyx
    modules: list[CyModule] = []

    for package, directory in sorted(find_packages(project_root).items()):
        pyx_names = {p.stem for p in directory.glob("*.pyx")}

        for source in sorted(directory.glob("*.pyx")):
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
            # __init__ stays pure Python so the package keeps working.
            if source.stem == "__init__" or source.stem in pyx_names:
                continue
            relative = source.relative_to(project_root)
            if is_excluded(relative, config.exclude):
                continue
            staged = Path(STAGING_DIR, *package.split("."), f"{source.stem}.pyx")
            _stage(source, project_root / staged)
            modules.append(
                CyModule(
                    package=package,
                    name=source.stem,
                    source=staged,
                    origin=relative,
                    converted=True,
                )
            )

    _prune_staging(project_root, modules)
    return modules


def is_excluded(relative_path: Path, patterns: list[str]) -> bool:
    """Match a project-relative path against the ``cythonize_exclude`` globs.

    A pattern without a ``/`` matches the file name at any depth (gitignore
    style); otherwise it is matched against the whole relative path.
    """
    posix = PurePosixPath(relative_path.as_posix())
    for pattern in patterns:
        if "/" not in pattern:
            if PurePosixPath(posix.name).full_match(pattern):
                return True
        elif posix.full_match(pattern):
            return True
    return False


def _stage(source: Path, target: Path) -> None:
    """Copy ``source`` to ``target`` only when the content actually changed.

    Rewriting an unchanged file would make Cython recompile it every build.
    """
    content = source.read_bytes()
    if target.exists() and target.read_bytes() == content:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def _prune_staging(project_root: Path, modules: list[CyModule]) -> None:
    """Drop staged sources whose original ``.py`` module is gone.

    Generated C under the staging directory is disposable — an orphaned .c is
    never referenced by an Extension, so it is left for Cython to overwrite.
    """
    staging = project_root / STAGING_DIR
    if not staging.is_dir():
        return
    keep = {project_root / m.source for m in modules if m.converted}
    for stale in staging.rglob("*.pyx"):
        if stale not in keep:
            stale.unlink()


# ---------------------------------------------------------------------------
# Hooking the extensions into the setuptools build
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def cython_build(project_root: Path, *, allow_py_to_pyx: bool = True) -> Iterator[None]:
    """Add the cythonized extensions to the setuptools build inside this block.

    ``setuptools.build_meta`` runs ``from setuptools import setup; setup()``
    when a project has no setup.py, so ``ext_modules`` is injected by wrapping
    ``setuptools.setup`` for the duration of the build.  A no-op when Cython
    compilation is not configured.
    """
    config = read_cythonize_config(project_root)
    if config is None:
        yield
        return

    if not config.cythonize:
        if config.py_to_pyx:
            print(
                "ksp-builder: py_to_pyx is set but cythonize is not — "
                "nothing will be compiled.",
                flush=True,
            )
        yield
        return

    modules = collect_modules(project_root, config, allow_py_to_pyx=allow_py_to_pyx)
    if not modules:
        yield
        return

    for module in modules:
        print(f"ksp-builder: cythonize {module.origin} -> {module.dotted}", flush=True)

    ext_modules = _build_extensions(modules, config)
    excluded: set[tuple[str, str]] = set()
    if not config.keep_py:
        excluded = {(m.package, m.name) for m in modules if m.converted}

    with _patched_setup(ext_modules, excluded):
        yield


def _build_extensions(modules: list[CyModule], config: CythonizeConfig) -> list:
    try:
        from Cython.Build import cythonize as run_cythonize
    except ImportError as exc:  # pragma: no cover - cython is a hard dependency
        raise RuntimeError(
            "ksp-builder: cythonize is enabled but Cython is not installed."
        ) from exc
    from setuptools import Extension

    extensions = [
        Extension(module.dotted, [module.source.as_posix()]) for module in modules
    ]
    # build_dir keeps the generated .c out of the package directories, so it
    # cannot be picked up as package data and shipped in the wheel.
    return run_cythonize(
        extensions,
        build_dir=STAGING_DIR,
        compiler_directives=config.directives,
    )


@contextlib.contextmanager
def _patched_setup(ext_modules: list, excluded: set[tuple[str, str]]) -> Iterator[None]:
    import setuptools

    original = setuptools.setup

    def setup(**attrs):
        attrs["ext_modules"] = list(attrs.get("ext_modules") or []) + list(ext_modules)
        if excluded:
            cmdclass = dict(attrs.get("cmdclass") or {})
            cmdclass.setdefault("build_py", _build_py_without(excluded))
            attrs["cmdclass"] = cmdclass
        return original(**attrs)

    setuptools.setup = setup
    try:
        yield
    finally:
        setuptools.setup = original


def _build_py_without(excluded: set[tuple[str, str]]):
    """A ``build_py`` that leaves the converted ``.py`` modules out of the wheel."""
    from setuptools.command.build_py import build_py as _build_py

    class build_py(_build_py):
        def find_package_modules(self, package, package_dir):
            return [
                entry
                for entry in super().find_package_modules(package, package_dir)
                if (entry[0], entry[1]) not in excluded
            ]

    return build_py
