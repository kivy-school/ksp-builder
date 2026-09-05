# ksp-builder
A PEP 517 build backend for KSProject-based packages that combines Java source
injection ([pyjnius-builder](https://github.com/kivy-school/pyjnius-builder)
convention), Swift build support
([pyswiftkit-builder](https://github.com/Py-Swift/pyswiftkit-builder)), and
Android Gradle configuration injection into a single backend.

**Requires Python ≥ 3.13** (uses `tomllib` from the standard library and aligns
with the minimum version requirements of pyswiftkit-builder and pyjnius-builder).

## Usage

```toml
[build-system]
requires = ["ksp-builder"]
build-backend = "ksp_builder"
```

## Configuration

### Build scripts — `[tool.ksp-builder]`

Run your own scripts around the build.  `before_build` runs before the artifact
is assembled, `after_build` runs once it exists on disk.  Both keys are optional
and paths are relative to the project root.

```toml
[tool.ksp-builder]
before_build = "scripts/before_build.py"
after_build = "scripts/sign_wheel.sh"
```

The scripts do not have to be Python.  A `.py` path is run with the interpreter
running the build; any other path is executed directly, so it needs its
executable bit set (`chmod +x`) and a shebang naming its interpreter:

```sh
#!/usr/bin/env bash
set -e
codesign --sign "$SIGNING_IDENTITY" "$KSP_BUILD_ARTIFACT"
```

Scripts run with the project root as their working directory.  `after_build`
receives the artifact path as its first argument.  Both are given the
environment variables `KSP_BUILD_PROJECT_ROOT`, `KSP_BUILD_TARGET`
(`wheel`, `sdist` or `editable`), and — for `after_build` —
`KSP_BUILD_ARTIFACT`.  A script that exits non-zero fails the build.

### Cython compilation — `[tool.ksp-builder]`

Compiles your package sources into extension modules, replacing the
`cythonized_app` `setup.py` (there is no `setup.py` with a PEP 517 backend, so
`ksp-builder` injects the `ext_modules` itself).

```toml
[tool.ksp-builder]
cythonize = true
py_to_pyx = true
```

The two switches are separate on purpose:

| Setting | Effect |
| --- | --- |
| `cythonize = true` | Compiles the `.pyx` sources already in your packages. `.py` modules are untouched. |
| `py_to_pyx = true` | Also copies each `.py` module to `.cy_src/` as a `.pyx` and compiles it. **Requires `cythonize`** — on its own it does nothing. |

`__init__.py` is never converted, so packages stay importable, and top-level
modules (`py-modules`) are left alone.  A converted module ships only as its
compiled extension: the original `.py` is dropped from the wheel.  Generated
`.pyx` and C files are written to `.cy_src/` at the project root, which you can
add to `.gitignore`.

Package layout still comes from `[tool.setuptools]` — `packages`, `package-dir`
and `packages.find` are read as-is (with the same src/flat auto-discovery
setuptools does), so nothing is duplicated in this section.  The remaining keys
only tune the Cython step:

```toml
[tool.ksp-builder]
cythonize = true
py_to_pyx = true
cythonize_exclude = ["main.py", "**/legacy/*.py"]  # keep these as .py
cythonize_keep_py = true                           # ship the .py sources too

[tool.ksp-builder.cythonize_directives]
language_level = "3"   # the default
boundscheck = false
```

A pattern in `cythonize_exclude` without a `/` matches that file name at any
depth; a pattern with one is matched against the whole project-relative path.

Editable installs (`pip install -e .`) compile real `.pyx` sources but never
convert `.py`, so your edits keep taking effect during development.  Sdists are
never cythonized — compilation happens when a wheel is built from the sdist.
Note that setuptools does not add `.pyx` files to an sdist on its own, so if you
ship hand-written Cython sources, include them (`MANIFEST.in` with
`recursive-include <pkg> *.pyx *.pxd`) or a wheel built from the sdist will have
nothing to compile.

### Android Gradle config — `[tool.kivy-school.android]`

When present, `ksp-builder` generates a `.gradle/<package_name>.json` file and
injects it into the built wheel and sdist.  `ksproject` can then discover and
merge these JSON files from all installed packages to assemble the final Gradle
build configuration (permissions, gradle dependencies, etc.).

```toml
[tool.kivy-school]
app_name = "MyApp"

[tool.kivy-school.android]
package_name = "org.example.myapp"
gradle_dependencies = [
    "com.google.firebase:firebase-analytics:21.0.0",
]
permissions = [
    "INTERNET",
    "CAMERA",
]
[tool.kivy-school.android.meta_data]
"com.google.android.gms.ads.APPLICATION_ID" = "ca-app-pub-3940256099942544~3347511713"

```

### Java sources — `[tool.pyjnius]`

Java source files are injected into the wheel and sdist under `.java/`, following
the [pyjnius-builder](https://github.com/kivy-school/pyjnius-builder) convention.

```toml
[tool.pyjnius]
java-paths = ["java/"]
```

### Swift packages — `[tool.pyswiftkit]`

If `pyswiftkit-builder` is installed and `[tool.pyswiftkit]` is configured,
`swift build` runs automatically before the wheel is assembled and the compiled
artifacts are injected into the wheel.

```toml
[tool.pyswiftkit]
products = ["mymodule"]
```

