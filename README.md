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

