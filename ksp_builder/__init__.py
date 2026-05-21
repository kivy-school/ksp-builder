"""ksp_builder — PEP 517 build backend for KSProject-based packages.

Wraps setuptools and combines functionality from pyjnius-builder and
pyswiftkit-builder into a single backend.  Three optional injection steps
run after the base setuptools wheel/sdist is produced:

1. **Java sources** — if ``[tool.pyjnius]`` is present, Java files from the
   configured ``java-paths`` are injected under ``.java/`` (same convention
   as pyjnius-builder).

2. **Swift artifacts** — if ``[tool.pyswiftkit]`` is present *and*
   ``pyswiftkit_builder`` is installed, ``swift build`` is executed and the
   compiled ``.so`` / ``.dylib`` files are injected into the wheel.

3. **Android gradle config** — if ``[tool.kivy-school.android]`` is present,
   a ``.gradle/<package_name>.json`` file containing ``gradle_dependencies``
   and ``permissions`` is injected into the wheel/sdist.  ``ksproject`` can
   then discover and merge these JSON files from all installed packages to
   assemble the final Gradle build configuration.
"""
from __future__ import annotations

from pathlib import Path

from setuptools import build_meta as _setuptools_backend

__all__ = [
    "build_wheel",
    "build_sdist",
    "get_requires_for_build_wheel",
    "get_requires_for_build_sdist",
    "prepare_metadata_for_build_wheel",
]

# Pass-through hooks that need no extra logic.
get_requires_for_build_wheel = _setuptools_backend.get_requires_for_build_wheel
get_requires_for_build_sdist = _setuptools_backend.get_requires_for_build_sdist
prepare_metadata_for_build_wheel = _setuptools_backend.prepare_metadata_for_build_wheel

_st_build_editable = getattr(_setuptools_backend, "build_editable", None)
_st_get_requires_for_build_editable = getattr(
    _setuptools_backend, "get_requires_for_build_editable", None
)
_st_prepare_metadata_for_build_editable = getattr(
    _setuptools_backend, "prepare_metadata_for_build_editable", None
)

if _st_get_requires_for_build_editable is not None:
    get_requires_for_build_editable = _st_get_requires_for_build_editable
    __all__.append("get_requires_for_build_editable")

if _st_prepare_metadata_for_build_editable is not None:
    prepare_metadata_for_build_editable = _st_prepare_metadata_for_build_editable
    __all__.append("prepare_metadata_for_build_editable")


# ---------------------------------------------------------------------------
# Build hooks
# ---------------------------------------------------------------------------

def build_wheel(
    wheel_directory: str,
    config_settings: dict | None = None,
    metadata_directory: str | None = None,
) -> str:
    project_dir = Path.cwd()

    # Swift build must happen before setuptools assembles the wheel so that
    # the compiled .so/.dylib files can be picked up as package data.
    swift_config = _load_swift_config(project_dir)
    if swift_config is not None:
        _run_swift_build(project_dir, swift_config)
        _force_platform_wheel()

    wheel_name = _setuptools_backend.build_wheel(
        wheel_directory, config_settings, metadata_directory
    )
    wheel_path = Path(wheel_directory) / wheel_name

    if swift_config is not None:
        _inject_swift_artifacts(wheel_path, swift_config, project_dir)

    from ._java import get_java_source_dirs, add_java_sources_to_wheel
    java_dirs = get_java_source_dirs(
        config_settings=config_settings, project_root=project_dir
    )
    add_java_sources_to_wheel(wheel_path, java_dirs)

    from ._kivy_school import read_android_config
    from ._gradle import inject_gradle_config_to_wheel
    android_config = read_android_config(project_dir)
    if android_config is not None:
        inject_gradle_config_to_wheel(wheel_path, android_config)

    return wheel_name


def build_sdist(sdist_directory: str, config_settings: dict | None = None) -> str:
    project_dir = Path.cwd()

    sdist_name = _setuptools_backend.build_sdist(sdist_directory, config_settings)
    sdist_path = Path(sdist_directory) / sdist_name

    from ._java import get_java_source_dirs, add_java_sources_to_sdist
    java_dirs = get_java_source_dirs(
        config_settings=config_settings, project_root=project_dir
    )
    add_java_sources_to_sdist(sdist_path, java_dirs)

    from ._kivy_school import read_android_config
    from ._gradle import inject_gradle_config_to_sdist
    android_config = read_android_config(project_dir)
    if android_config is not None:
        inject_gradle_config_to_sdist(sdist_path, android_config)

    return sdist_name


if _st_build_editable is not None:
    def build_editable(
        wheel_directory: str,
        config_settings: dict | None = None,
        metadata_directory: str | None = None,
    ) -> str:
        project_dir = Path.cwd()

        swift_config = _load_swift_config(project_dir)
        if swift_config is not None:
            _run_swift_build(project_dir, swift_config)
            _force_platform_wheel()

        wheel_name = _st_build_editable(
            wheel_directory, config_settings, metadata_directory
        )
        wheel_path = Path(wheel_directory) / wheel_name

        if swift_config is not None:
            _inject_swift_artifacts(wheel_path, swift_config, project_dir)

        from ._java import get_java_source_dirs, add_java_sources_to_wheel
        java_dirs = get_java_source_dirs(
            config_settings=config_settings, project_root=project_dir
        )
        add_java_sources_to_wheel(wheel_path, java_dirs)

        from ._kivy_school import read_android_config
        from ._gradle import inject_gradle_config_to_wheel
        android_config = read_android_config(project_dir)
        if android_config is not None:
            inject_gradle_config_to_wheel(wheel_path, android_config)

        return wheel_name

    __all__.append("build_editable")


# ---------------------------------------------------------------------------
# Swift helpers (pyswiftkit_builder is an optional runtime dependency)
# ---------------------------------------------------------------------------

def _load_swift_config(project_dir: Path):
    """Return a PSKConfig if [tool.pyswiftkit] is configured, else None."""
    try:
        from pyswiftkit_builder._config import read_config  # type: ignore[import-untyped]
        return read_config(project_dir)
    except ImportError:
        return None
    except (FileNotFoundError, KeyError, ValueError):
        return None


def _run_swift_build(project_dir: Path, config) -> None:
    from pyswiftkit_builder._swift_build import build_swift  # type: ignore[import-untyped]
    build_swift(project_dir, config)


def _inject_swift_artifacts(wheel_path: Path, config, project_dir: Path) -> None:
    from pyswiftkit_builder._swift_build import inject_artifacts  # type: ignore[import-untyped]
    inject_artifacts(wheel_path, config, project_dir)


def _force_platform_wheel() -> None:
    """Tell setuptools this is a binary wheel (has native extensions)."""
    import setuptools
    setuptools.Distribution.has_ext_modules = lambda self: True  # type: ignore[method-assign]
