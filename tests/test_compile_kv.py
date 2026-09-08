import os
import tempfile
import unittest
from pathlib import Path

import setuptools

from ksp_builder._build import ksp_build
from ksp_builder._compile_kv import compile_kv_modules, find_kv_sources, read_compile_kv
from ksp_builder._packages import STAGING_DIR

KV = '<Root@BoxLayout>:\n    orientation: "vertical"\n'
PY_SOURCE = "from kivy.uix.boxlayout import BoxLayout\n\nGREETING = 'hi'\n"


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _project(root: Path, extra: str = "") -> Path:
    """A one-package project whose ``main.py`` has a ``main.kv`` beside it."""
    _write(
        root / "pyproject.toml",
        '[tool.setuptools]\npackages = ["kvapp"]\n[tool.ksp-builder]\n' + extra,
    )
    package = root / "kvapp"
    _write(package / "__init__.py")
    _write(package / "main.py", PY_SOURCE)
    _write(package / "main.kv", KV)
    return package


class TestReadCompileKv(unittest.TestCase):
    def test_absent_pyproject_is_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(read_compile_kv(Path(tmp)))

    def test_reads_the_switch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "pyproject.toml", "[tool.ksp-builder]\ncompile_kv = true\n")
            self.assertTrue(read_compile_kv(root))
            _write(root / "pyproject.toml", "[tool.ksp-builder]\ncompile_kv = false\n")
            self.assertFalse(read_compile_kv(root))


class TestFindKvSources(unittest.TestCase):
    def test_only_kv_files_inside_a_package_are_collected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = _project(root)
            # A .kv in a plain data directory has no module name to take.
            _write(package / "ui" / "theme.kv", KV)

            found = [
                (name, path.relative_to(root).as_posix())
                for name, path in find_kv_sources(root)
            ]
            self.assertEqual(found, [("kvapp", "kvapp/main.kv")])

    def test_nested_packages_are_collected_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "pyproject.toml", "[tool.ksp-builder]\ncompile_kv = true\n")
            _write(root / "kvapp" / "__init__.py")
            _write(root / "kvapp" / "screens" / "__init__.py")
            _write(root / "kvapp" / "screens" / "home.kv", KV)

            found = [
                (name, path.relative_to(root).as_posix())
                for name, path in find_kv_sources(root)
            ]
            self.assertEqual(found, [("kvapp.screens", "kvapp/screens/home.kv")])


class TestCompileKvModules(unittest.TestCase):
    def test_generated_module_merges_the_py_beside_the_kv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _project(root)

            modules = compile_kv_modules(root)
            self.assertEqual([m.dotted for m in modules], ["kvapp.main"])

            module = modules[0]
            self.assertFalse(module.as_pyx)
            self.assertEqual(module.source, Path(STAGING_DIR, "kvapp", "main.py"))
            self.assertEqual(module.py, Path("kvapp", "main.py"))

            generated = (root / module.source).read_text(encoding="utf-8")
            # compilekv reprints the source it was given, quotes normalised.
            self.assertIn("GREETING", generated)  # the hand-written half
            self.assertIn("class Root(BoxLayout)", generated)  # the KV half

    def test_kv_without_a_py_becomes_a_module_of_its_own(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = _project(root)
            (package / "main.py").unlink()

            modules = compile_kv_modules(root)
            self.assertEqual([m.dotted for m in modules], ["kvapp.main"])
            self.assertIsNone(modules[0].py)
            self.assertIn(
                "class Root", (root / modules[0].source).read_text(encoding="utf-8")
            )

    def test_as_pyx_stages_the_module_for_cython(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _project(root)

            modules = compile_kv_modules(root, as_pyx=True)
            self.assertTrue(modules[0].as_pyx)
            self.assertEqual(modules[0].source, Path(STAGING_DIR, "kvapp", "main.pyx"))
            self.assertTrue((root / STAGING_DIR / "kvapp" / "main.pyx").exists())

    def test_excluded_module_is_compiled_but_stays_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _project(root)

            modules = compile_kv_modules(root, as_pyx=True, exclude=["main.py"])
            self.assertFalse(modules[0].as_pyx)
            self.assertEqual(modules[0].source, Path(STAGING_DIR, "kvapp", "main.py"))

    def test_init_kv_is_never_staged_as_pyx(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = _project(root)
            (package / "main.kv").unlink()
            _write(package / "__init__.kv", KV)

            modules = compile_kv_modules(root, as_pyx=True)
            self.assertEqual([m.dotted for m in modules], ["kvapp.__init__"])
            self.assertFalse(modules[0].as_pyx)

    def test_source_tree_is_never_written_to(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = _project(root)
            before = {
                path.relative_to(root): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in package.rglob("*")
                if path.is_file()
            }

            compile_kv_modules(root, as_pyx=True)

            after = {
                path.relative_to(root): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in package.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)

    def test_unchanged_source_is_not_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _project(root)

            staged = root / compile_kv_modules(root)[0].source
            before = staged.stat().st_mtime_ns
            compile_kv_modules(root)
            self.assertEqual(staged.stat().st_mtime_ns, before)


class TestKspBuildWithKv(unittest.TestCase):
    def _run(self, root: Path, **kwargs) -> dict:
        recorded: dict = {}
        original = setuptools.setup
        setuptools.setup = lambda **attrs: recorded.update(attrs)
        cwd = Path.cwd()
        os.chdir(root)
        try:
            with ksp_build(root, **kwargs):
                setuptools.setup()
        finally:
            os.chdir(cwd)
            setuptools.setup = original
        return recorded

    def test_generated_module_replaces_the_py_and_the_kv_is_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _project(root, "compile_kv = true\n")

            recorded = self._run(root)
            build_py = recorded["cmdclass"]["build_py"]

            self.assertEqual(recorded["ext_modules"], [])
            self.assertEqual(build_py.ksp_excluded, set())
            self.assertEqual(
                build_py.ksp_replacements,
                {("kvapp", "main"): str(root / STAGING_DIR / "kvapp" / "main.py")},
            )
            self.assertEqual(
                build_py.ksp_dropped_data,
                {os.path.abspath(root / "kvapp" / "main.kv")},
            )

    def test_all_three_switches_compile_the_kv_into_an_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # A package name of its own: Cython caches dependency state by
            # relative source path, and every build here runs in one process.
            _write(
                root / "pyproject.toml",
                '[tool.setuptools]\npackages = ["kvfull"]\n[tool.ksp-builder]\n'
                "cythonize = true\npy_to_pyx = true\ncompile_kv = true\n",
            )
            _write(root / "kvfull" / "__init__.py")
            _write(root / "kvfull" / "screen.py", PY_SOURCE)
            _write(root / "kvfull" / "screen.kv", KV)

            recorded = self._run(root)
            build_py = recorded["cmdclass"]["build_py"]

            # Compiled once, from the generated module — not twice, once from
            # the .kv and again from the .py that fed it.
            self.assertEqual([e.name for e in recorded["ext_modules"]], ["kvfull.screen"])
            self.assertEqual(build_py.ksp_excluded, {("kvfull", "screen")})
            self.assertEqual(build_py.ksp_replacements, {})
            self.assertEqual(
                build_py.ksp_dropped_data,
                {os.path.abspath(root / "kvfull" / "screen.kv")},
            )
            self.assertFalse((root / STAGING_DIR / "kvfull" / "screen.py").exists())

    def test_editable_build_leaves_kv_files_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _project(root, "compile_kv = true\n")

            original = setuptools.setup
            with ksp_build(root, editable=True):
                self.assertIs(setuptools.setup, original)
            self.assertFalse((root / STAGING_DIR).exists())

    def test_include_assets_can_be_turned_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _project(root, "compile_kv = true\ninclude_assets = false\n")
            self.assertFalse(
                self._run(root)["cmdclass"]["build_py"].ksp_include_assets
            )

    def test_stale_generated_module_is_pruned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = _project(root, "compile_kv = true\n")
            self._run(root)
            staged = root / STAGING_DIR / "kvapp" / "main.py"
            self.assertTrue(staged.exists())

            (package / "main.kv").unlink()
            self._run(root)
            self.assertFalse(staged.exists())


if __name__ == "__main__":
    unittest.main()
