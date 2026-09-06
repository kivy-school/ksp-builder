"""ksp_builder._packages — a project's packages, their assets, and staging.

Shared ground for the Cython and KV compilation steps: both need to know which
directories are packages, which files inside them are shippable assets, and
where generated sources go.

Nothing here ever writes into the package tree.  Generated sources — ``.pyx``
staged from ``.py``, modules compiled out of ``.kv`` — are written under
:data:`STAGING_DIR` at the project root, so a build leaves ``src/`` exactly as
it found it.
"""
from __future__ import annotations

import tomllib
from pathlib import Path, PurePosixPath
from typing import Any

__all__ = [
    "STAGING_DIR",
    "NEVER_CONVERTED",
    "NON_ASSET_SUFFIXES",
    "read_section",
    "find_packages",
    "is_excluded",
    "find_package_assets",
    "stage_file",
    "prune_staging",
]

#: Directory (relative to the project root) holding every generated source.
STAGING_DIR = ".dist_src"

#: Modules that are always left as ``.py``.  Compiling ``__init__`` costs the
#: package its normal import behaviour, and an extension has no code object for
#: runpy to execute, which is what ``python -m <package>`` needs from
#: ``__main__``.  Both are still shipped, just uncompiled.
NEVER_CONVERTED = frozenset({"__init__", "__main__"})

#: Never shipped as package data: the sources of this compilation and its
#: byproducts, plus the extension files build_ext already owns.  A wheel whose
#: point is to hide its sources must not carry them back as "assets".
NON_ASSET_SUFFIXES = frozenset({
    ".py", ".pyc", ".pyo", ".pyx", ".pxd", ".pxi",
    ".c", ".cpp", ".cc", ".h", ".hpp", ".o", ".obj",
    ".so", ".pyd", ".dylib",
})


def read_section(project_root: Path) -> dict[str, Any]:
    """The ``[tool.ksp-builder]`` table, or an empty dict."""
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return {}
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    section = data.get("tool", {}).get("ksp-builder", {})
    return section if isinstance(section, dict) else {}


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


# ---------------------------------------------------------------------------
# Package assets (.kv, images, fonts, ...)
# ---------------------------------------------------------------------------

def find_package_assets(src_dir: Path) -> list[str]:
    """Every shippable non-source file inside a package directory.

    Recurses into plain data directories but not into nested packages — those
    are collected separately as packages in their own right.
    """
    if not src_dir.is_dir():
        return []

    assets: list[str] = []

    def walk(directory: Path) -> None:
        for child in sorted(directory.iterdir()):
            if child.name.startswith(".") or child.name.endswith(".egg-info"):
                continue
            if child.is_dir():
                if child.name == "__pycache__":
                    continue
                if (child / "__init__.py").exists():
                    continue
                walk(child)
            elif child.suffix.lower() not in NON_ASSET_SUFFIXES:
                assets.append(str(child))

    walk(src_dir)
    return assets


# ---------------------------------------------------------------------------
# The staging directory
# ---------------------------------------------------------------------------

def stage_file(target: Path, content: bytes) -> None:
    """Write ``content`` to ``target`` only when it actually changed.

    Rewriting an unchanged file would make Cython recompile it every build.
    """
    if target.exists() and target.read_bytes() == content:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def prune_staging(project_root: Path, keep: set[Path]) -> None:
    """Drop staged sources, and their generated C, that this build did not make.

    Whatever is left behind by a renamed or deleted source would otherwise be
    compiled into the next wheel.
    """
    staging = project_root / STAGING_DIR
    if not staging.is_dir():
        return

    for stale in sorted(staging.rglob("*")):
        if not stale.is_file() or stale.suffix not in {".py", ".pyx"}:
            continue
        if stale in keep:
            continue
        stale.unlink()
        stale.with_suffix(".c").unlink(missing_ok=True)

    # Directories emptied by the loop above are noise in the project root.
    for directory in sorted(staging.rglob("*"), reverse=True):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
