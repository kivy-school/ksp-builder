"""ksp_builder._pre_post_build — runs user scripts around the build.

Reads ``[tool.ksp-builder]`` from ``pyproject.toml``::

    [tool.ksp-builder]
    before_build = "path/to/before_build_script.py"
    after_build = "path/to/after_build.sh"

``before_build`` runs before the backend assembles the artifact, ``after_build``
runs once the artifact exists on disk.  Either key may be omitted.  A script
that exits non-zero fails the build.

The script is *not* restricted to Python.  A ``.py`` path is run with the
interpreter running the build (``sys.executable``); anything else is executed
directly, so it needs its executable bit set and a shebang naming its
interpreter — shell, Bash, Node, a compiled binary, whatever the project uses.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "BuildScripts",
    "read_build_scripts",
    "run_before_build",
    "run_after_build",
]


@dataclass
class BuildScripts:
    """Script paths from ``[tool.ksp-builder]``, resolved against the project root."""

    before_build: Path | None = None
    after_build: Path | None = None


def read_build_scripts(project_root: Path) -> BuildScripts | None:
    """Read ``before_build`` / ``after_build`` from pyproject.toml.

    Returns None if pyproject.toml is absent or declares neither key.
    """
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return None

    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    section = data.get("tool", {}).get("ksp-builder", {})

    before = section.get("before_build")
    after = section.get("after_build")
    if not before and not after:
        return None

    return BuildScripts(
        before_build=_resolve(project_root, before),
        after_build=_resolve(project_root, after),
    )


def _resolve(project_root: Path, value: str | None) -> Path | None:
    """Turn a configured script path into an absolute path."""
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return path


def run_before_build(project_root: Path, target: str) -> None:
    """Run the configured ``before_build`` script, if any."""
    scripts = read_build_scripts(project_root)
    if scripts is None or scripts.before_build is None:
        return
    _run_script(scripts.before_build, project_root, target, artifact_path=None)


def run_after_build(project_root: Path, target: str, artifact_path: Path) -> None:
    """Run the configured ``after_build`` script, if any.

    The artifact path is passed to the script as its first argument and as the
    ``KSP_BUILD_ARTIFACT`` environment variable.
    """
    scripts = read_build_scripts(project_root)
    if scripts is None or scripts.after_build is None:
        return
    _run_script(scripts.after_build, project_root, target, artifact_path=artifact_path)


def _run_script(
    script: Path,
    project_root: Path,
    target: str,
    artifact_path: Path | None,
) -> None:
    if not script.exists():
        raise FileNotFoundError(f"ksp-builder: build script not found: {script}")

    # .py runs under the interpreter driving the build; anything else is run
    # directly and supplies its own interpreter via a shebang.
    if script.suffix == ".py":
        command = [sys.executable, str(script)]
    else:
        if not os.access(script, os.X_OK):
            raise PermissionError(
                f"ksp-builder: build script is not executable: {script}\n"
                "Non-.py scripts are run directly — mark it executable "
                "(chmod +x) and give it a shebang, or point the key at a "
                ".py file instead."
            )
        command = [str(script)]
    if artifact_path is not None:
        command.append(str(artifact_path))

    env = dict(os.environ)
    env["KSP_BUILD_PROJECT_ROOT"] = str(project_root)
    env["KSP_BUILD_TARGET"] = target
    if artifact_path is not None:
        env["KSP_BUILD_ARTIFACT"] = str(artifact_path)

    print(f"ksp-builder: running {script} ({target})", flush=True)
    subprocess.run(command, cwd=str(project_root), env=env, check=True)
