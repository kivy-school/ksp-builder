# ksp-builder
A PEP 517 build backend for KSProject-based packages that combines Cython
compilation, Kivy KV compilation, Java source injection
([pyjnius-builder](https://github.com/kivy-school/pyjnius-builder) convention),
Swift build support
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
| `py_to_pyx = true` | Also copies each `.py` module to `.dist_src/` as a `.pyx` and compiles it. **Requires `cythonize`** — on its own it does nothing. |

`__init__.py` and `__main__.py` are never converted — the first keeps the
package importable, the second keeps `python -m yourpackage` working, since
runpy needs a code object that a compiled extension cannot provide.  Both are
still shipped, just as `.py`.  Top-level modules (`py-modules`) are left alone
too.  A converted module ships only as its
compiled extension: the original `.py` is dropped from the wheel.  Generated
`.pyx` and C files are written to `.dist_src/` at the project root, which you
can add to `.gitignore`.  Nothing is ever written back into your package: a
build leaves the source tree exactly as it found it.

#### `.kv` files and other assets

Plain setuptools ships only Python modules, so a cythonized Kivy app would build
fine and then fail at runtime with its `.kv` files missing.  Whenever it is
compiling something (`cythonize` or `compile_kv`), `ksp-builder` therefore
ships **every file in your packages** as package data —
`.kv`, images, fonts, JSON, whatever is there — including files in nested data
directories such as `assets/images/`.  No configuration needed.

```
kvapp/__init__.py          ->  kvapp/__init__.py
kvapp/app.py               ->  kvapp/app.cpython-313-darwin.so
kvapp/app.kv               ->  kvapp/app.kv
kvapp/data/images/logo.png ->  kvapp/data/images/logo.png
kvapp/fonts/Roboto.ttf     ->  kvapp/fonts/Roboto.ttf
```

Assets land next to the compiled extension, so `Path(__file__).parent` still
finds them.  Directories containing an `__init__.py` are skipped here and
collected as the packages they are.  (With `compile_kv = true` the `.kv` files
are the exception: they are compiled into their modules instead of shipped —
see below.)

Sources and build output are the one exception — `.py`, `.pyx`, `.pxd`, `.c`,
`.h`, `.o`, `.so`, `.pyd`, `.pyc` and `__pycache__` are never shipped as assets,
since that would hand back the very sources the compilation just removed.  To
ship one of those deliberately (a prebuilt binary, say), name it explicitly in
`[tool.setuptools.package-data]`, which is merged with what is found here.

Set `include_assets = false` to turn the whole behaviour off and go back to
declaring package data yourself.

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
include_assets = false                             # stop auto-shipping assets

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

### Kivy KV compilation — `[tool.ksp-builder]`

```toml
[tool.ksp-builder]
compile_kv = true
```

Turns every `.kv` file in your packages into a Python module using the
[`compilekv`](https://github.com/kivy-school/compilekv) library: the KV rules
become real widget classes, so nothing has to be parsed at startup and the
result can be compiled like any other module.

Each `.kv` is compiled together with the `.py` of the same name beside it, and
the module the two produce replaces that `.py` in the wheel.  A `.kv` with no
`.py` beside it simply becomes a module of its own.  The `.kv` itself is *not*
shipped — it has been compiled into the module, and shipping it too would only
invite a second, conflicting set of rules at runtime.

```
kvapp/app.py + kvapp/app.kv  ->  kvapp/app.py        (the two, merged)
kvapp/theme.kv               ->  kvapp/theme.py      (no .py of its own)
```

Only `.kv` files sitting **directly in a package** are compiled, since a
compiled KV file becomes an importable module and there is no module name for
one in a plain data directory.  A `.kv` under `kvapp/ui/` stays ordinary
package data.

#### All three switches together

`compile_kv` composes with the Cython switches.  With all three on, the module
compiled out of the `.kv` is staged as a `.pyx` and compiled to an extension,
so neither the `.kv` nor the `.py` that fed it reaches the wheel:

```toml
[tool.ksp-builder]
cythonize = true
py_to_pyx = true
compile_kv = true
```

```
kvapp/__init__.py            ->  kvapp/__init__.py
kvapp/__main__.py            ->  kvapp/__main__.py
kvapp/app.py + kvapp/app.kv  ->  kvapp/app.cpython-313-darwin.so
kvapp/theme.kv               ->  kvapp/theme.cpython-313-darwin.so
kvapp/assets/logo.png        ->  kvapp/assets/logo.png
```

A module named by `cythonize_exclude` is still compiled out of its KV file, it
just stays a plain `.py`.  `__init__` and `__main__` are never turned into
extensions here either.

Editable installs (`pip install -e .`) leave `.kv` files alone — the source
tree is what gets imported, so a generated module would never be used and your
`.kv` edits keep taking effect during development.

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

