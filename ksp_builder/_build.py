"""ksp_builder._build — hooks the generated sources into the setuptools build.

``setuptools.build_meta`` runs ``from setuptools import setup; setup()`` when a
project has no setup.py, so there is no place to declare ``ext_modules`` or a
``cmdclass``.  :func:`ksp_build` wraps ``setuptools.setup`` for the duration of
the build and passes them in there.

It is also the one place that sees both compilation steps at once, which is
what the three-switch combination needs::

    [tool.ksp-builder]
    cythonize = true
    py_to_pyx = true
    compile_kv = true

With all three on, a ``.kv`` is compiled into a module, staged as a ``.pyx``
and compiled to an extension; the ``.py`` that fed it is not shipped, and
neither is the ``.kv``.
"""
from __future__ import annotations

import contextlib
import os
import warnings
from pathlib import Path
from typing import Iterator

from ._compile_kv import KvModule, compile_kv_modules, read_compile_kv
from ._cythonize import CyModule, build_extensions, collect_modules, read_cythonize_config
from ._packages import find_package_assets, prune_staging, read_section

__all__ = ["ksp_build"]


@contextlib.contextmanager
def ksp_build(project_root: Path, *, editable: bool = False) -> Iterator[None]:
    """Compile what ``[tool.ksp-builder]`` asks for, for this block's build.

    A no-op when neither Cython nor KV compilation is configured.  An editable
    install exposes the source tree itself, so nothing generated would ever be
    imported: ``.py`` modules are left alone there and ``.kv`` files stay as
    they are, and only hand-written ``.pyx`` sources are still compiled.
    """
    section = read_section(project_root)
    config = read_cythonize_config(project_root)
    compile_kv = read_compile_kv(project_root) and not editable

    if config is None and not compile_kv:
        yield
        return

    if config is not None and config.py_to_pyx and not config.cythonize:
        print(
            "ksp-builder: py_to_pyx is set but cythonize is not — "
            "nothing will be compiled.",
            flush=True,
        )

    convert_py = (
        config is not None and config.cythonize and config.py_to_pyx and not editable
    )

    kv_modules: list[KvModule] = []
    if compile_kv:
        kv_modules = compile_kv_modules(
            project_root,
            as_pyx=convert_py,
            exclude=config.exclude if config is not None else (),
        )
        for module in kv_modules:
            print(f"ksp-builder: compile_kv {module.kv} -> {module.dotted}", flush=True)

    cy_modules: list[CyModule] = []
    if config is not None:
        cy_modules = collect_modules(
            project_root,
            config,
            allow_py_to_pyx=not editable,
            skip={(m.package, m.name) for m in kv_modules},
        )
    cy_modules += [
        CyModule(
            package=module.package,
            name=module.name,
            source=module.source,
            origin=module.kv,
            converted=True,
        )
        for module in kv_modules
        if module.as_pyx
    ]

    prune_staging(
        project_root,
        {project_root / m.source for m in cy_modules if m.converted}
        | {project_root / m.source for m in kv_modules},
    )

    if not cy_modules and not kv_modules:
        yield
        return

    for module in cy_modules:
        print(f"ksp-builder: cythonize {module.origin} -> {module.dotted}", flush=True)

    ext_modules = build_extensions(cy_modules, config) if cy_modules else []

    keep_py = config is not None and config.keep_py
    excluded: set[tuple[str, str]] = set()
    if not keep_py:
        excluded = {(m.package, m.name) for m in cy_modules if m.converted}

    # A KV module that was not staged for Cython ships as source, generated
    # from the .kv plus the .py beside it — so it replaces that .py, and adds a
    # module of its own when there was no .py to begin with.
    replacements = {
        (m.package, m.name): str(project_root / m.source)
        for m in kv_modules
        if not m.as_pyx
    }
    # The .kv has been compiled into the module; shipping it too would only
    # invite a second, conflicting set of rules at runtime.
    compiled_kv = {os.path.abspath(project_root / m.kv) for m in kv_modules}

    with _patched_setup(
        ext_modules,
        excluded=excluded,
        replacements=replacements,
        dropped_data=compiled_kv,
        include_assets=bool(section.get("include_assets", True)),
    ):
        yield


@contextlib.contextmanager
def _patched_setup(
    ext_modules: list,
    *,
    excluded: set[tuple[str, str]],
    replacements: dict[tuple[str, str], str],
    dropped_data: set[str],
    include_assets: bool,
) -> Iterator[None]:
    import setuptools

    original = setuptools.setup

    def setup(**attrs):
        attrs["ext_modules"] = list(attrs.get("ext_modules") or []) + list(ext_modules)
        cmdclass = dict(attrs.get("cmdclass") or {})
        cmdclass.setdefault(
            "build_py",
            _make_build_py(excluded, replacements, dropped_data, include_assets),
        )
        attrs["cmdclass"] = cmdclass
        return original(**attrs)

    setuptools.setup = setup
    try:
        with _quiet_data_directory_warning(include_assets):
            yield
    finally:
        setuptools.setup = original


@contextlib.contextmanager
def _quiet_data_directory_warning(active: bool) -> Iterator[None]:
    """Silence setuptools' "Package would be ignored" notice for asset dirs.

    Shipping ``images/`` or ``fonts/`` as package data is the whole point here,
    but the files reach egg-info's manifest, where setuptools sees importable
    directories missing from ``packages`` and emits ~30 lines of advice for
    each one.  Only that one warning is filtered, and only during our build.
    """
    category = None
    if active:
        from setuptools.command import build_py as _build_py_module

        abuse = getattr(_build_py_module, "_IncludePackageDataAbuse", None)
        category = getattr(abuse, "_Warning", None)

    if category is None:
        yield
        return

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=category)
        yield


def _make_build_py(
    excluded: set[tuple[str, str]],
    replacements: dict[tuple[str, str], str],
    dropped_data: set[str],
    include_assets: bool,
):
    """A ``build_py`` that ships what this build generated, not what it read."""
    from setuptools.command.build_py import build_py as _build_py

    class build_py(_build_py):
        ksp_excluded = excluded
        ksp_replacements = replacements
        ksp_dropped_data = dropped_data
        ksp_include_assets = include_assets

        def find_package_modules(self, package, package_dir):
            found = [
                entry
                for entry in super().find_package_modules(package, package_dir)
                if (entry[0], entry[1]) not in excluded
            ]
            generated = {
                name: path
                for (owner, name), path in replacements.items()
                if owner == package
            }
            if not generated:
                return found

            modules = [
                (pkg, name, generated.get(name, source)) for pkg, name, source in found
            ]
            present = {name for _, name, _ in found}
            modules += [
                (package, name, path)
                for name, path in sorted(generated.items())
                if name not in present
            ]
            return modules

        def find_data_files(self, package, src_dir):
            files = list(super().find_data_files(package, src_dir))
            if include_assets and src_dir:
                # exclude_data_files applies the project's exclude-package-data,
                # which super() has already applied to its own half of the list.
                found = self.exclude_data_files(
                    package, src_dir, find_package_assets(Path(src_dir))
                )
                seen = set(files)
                for path in found:
                    if path not in seen:
                        seen.add(path)
                        files.append(path)
            if dropped_data:
                files = [
                    path for path in files if os.path.abspath(path) not in dropped_data
                ]
            return files

    return build_py
