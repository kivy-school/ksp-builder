# ksp-builder
A PEP 517 build backend implementation developed for KSProject-based packages.

For now, `ksp_builder` delegates all build hooks to `setuptools.build_meta`.

Use it in a consumer project via:

```toml
[build-system]
requires = ["ksp-builder"]
build-backend = "ksp_builder"
```
