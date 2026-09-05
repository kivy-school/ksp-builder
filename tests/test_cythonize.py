import tempfile
import unittest
from pathlib import Path

import setuptools

from ksp_builder._cythonize import (
    STAGING_DIR,
    CythonizeConfig,
    collect_modules,
    cython_build,
    find_packages,
    is_excluded,
    read_cythonize_config,
)


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestReadCythonizeConfig(unittest.TestCase):
    def _config(self, tmp: Path, body: str):
        _write(tmp / "pyproject.toml", body)
        return read_cythonize_config(tmp)

    def test_returns_none_when_no_pyproject(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(read_cythonize_config(Path(tmp)))

    def test_returns_none_when_section_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(self._config(Path(tmp), "[project]\nname = 'x'\n"))

    def test_returns_none_when_both_switches_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = "[tool.ksp-builder]\ncythonize = false\npy_to_pyx = false\n"
            self.assertIsNone(self._config(Path(tmp), body))

    def test_returns_none_when_only_unrelated_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = "[tool.ksp-builder]\nbefore_build = 'x.py'\n"
            self.assertIsNone(self._config(Path(tmp), body))

    def test_reads_both_switches(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = "[tool.ksp-builder]\ncythonize = true\npy_to_pyx = true\n"
            config = self._config(Path(tmp), body)
            self.assertTrue(config.cythonize)
            self.assertTrue(config.py_to_pyx)
            self.assertFalse(config.keep_py)
            self.assertEqual(config.exclude, [])

    def test_py_to_pyx_alone_is_reported_but_not_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(Path(tmp), "[tool.ksp-builder]\npy_to_pyx = true\n")
            self.assertIsNotNone(config)
            self.assertFalse(config.cythonize)
            self.assertTrue(config.py_to_pyx)

    def test_language_level_defaults_and_is_overridable(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(Path(tmp), "[tool.ksp-builder]\ncythonize = true\n")
            self.assertEqual(config.directives["language_level"], "3")

            body = (
                "[tool.ksp-builder]\ncythonize = true\n"
                "[tool.ksp-builder.cythonize_directives]\n"
                'language_level = "3str"\nboundscheck = false\n'
            )
            config = self._config(Path(tmp), body)
            self.assertEqual(config.directives["language_level"], "3str")
            self.assertFalse(config.directives["boundscheck"])

    def test_reads_exclude_and_keep_py(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = (
                "[tool.ksp-builder]\ncythonize = true\npy_to_pyx = true\n"
                'cythonize_exclude = ["main.py", "**/legacy/*.py"]\n'
                "cythonize_keep_py = true\n"
            )
            config = self._config(Path(tmp), body)
            self.assertEqual(config.exclude, ["main.py", "**/legacy/*.py"])
            self.assertTrue(config.keep_py)


class TestIsExcluded(unittest.TestCase):
    def test_bare_name_matches_at_any_depth(self):
        self.assertTrue(is_excluded(Path("src/app/main.py"), ["main.py"]))
        self.assertTrue(is_excluded(Path("main.py"), ["main.py"]))
        self.assertFalse(is_excluded(Path("src/app/core.py"), ["main.py"]))

    def test_path_pattern_matches_whole_path(self):
        self.assertTrue(is_excluded(Path("src/app/legacy/old.py"), ["**/legacy/*.py"]))
        self.assertFalse(is_excluded(Path("src/app/core.py"), ["**/legacy/*.py"]))
        self.assertTrue(is_excluded(Path("src/app/core.py"), ["src/app/core.py"]))

    def test_no_patterns_excludes_nothing(self):
        self.assertFalse(is_excluded(Path("src/app/core.py"), []))


class TestFindPackages(unittest.TestCase):
    def test_explicit_packages_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "pyproject.toml", '[tool.setuptools]\npackages = ["myapp"]\n')
            _write(root / "myapp" / "__init__.py")
            _write(root / "other" / "__init__.py")
            self.assertEqual(find_packages(root), {"myapp": root / "myapp"})

    def test_explicit_packages_honour_package_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "pyproject.toml",
                '[tool.setuptools]\npackages = ["myapp", "myapp.utils"]\n'
                '[tool.setuptools.package-dir]\n"" = "src"\n',
            )
            _write(root / "src" / "myapp" / "__init__.py")
            _write(root / "src" / "myapp" / "utils" / "__init__.py")
            self.assertEqual(
                find_packages(root),
                {
                    "myapp": root / "src" / "myapp",
                    "myapp.utils": root / "src" / "myapp" / "utils",
                },
            )

    def test_find_directive_with_where(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "pyproject.toml",
                '[tool.setuptools.packages.find]\nwhere = ["src"]\n',
            )
            _write(root / "src" / "myapp" / "__init__.py")
            _write(root / "src" / "myapp" / "utils" / "__init__.py")
            self.assertEqual(
                set(find_packages(root)), {"myapp", "myapp.utils"}
            )

    def test_auto_discovery_src_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "pyproject.toml", "[project]\nname = 'x'\n")
            _write(root / "src" / "myapp" / "__init__.py")
            self.assertEqual(find_packages(root), {"myapp": root / "src" / "myapp"})

    def test_auto_discovery_flat_layout_skips_noise(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "pyproject.toml", "[project]\nname = 'x'\n")
            _write(root / "myapp" / "__init__.py")
            _write(root / "tests" / "__init__.py")
            _write(root / "build" / "__init__.py")
            _write(root / STAGING_DIR / "myapp" / "__init__.py")
            _write(root / "notapackage" / "thing.py")
            self.assertEqual(find_packages(root), {"myapp": root / "myapp"})


class TestCollectModules(unittest.TestCase):
    def _project(self, root: Path) -> None:
        _write(root / "pyproject.toml", '[tool.setuptools]\npackages = ["myapp"]\n')
        _write(root / "myapp" / "__init__.py", "__version__ = '1'\n")
        _write(root / "myapp" / "core.py", "def add(a, b): return a + b\n")
        _write(root / "myapp" / "speed.pyx", "def fast(int a): return a\n")

    def test_nothing_collected_when_cythonize_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root)
            config = CythonizeConfig(cythonize=False, py_to_pyx=True)
            self.assertEqual(collect_modules(root, config), [])

    def test_cythonize_alone_takes_only_pyx(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root)
            modules = collect_modules(root, CythonizeConfig(cythonize=True))
            self.assertEqual([m.dotted for m in modules], ["myapp.speed"])
            self.assertFalse(modules[0].converted)
            self.assertFalse((root / STAGING_DIR).exists())

    def test_both_switches_convert_py(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root)
            config = CythonizeConfig(cythonize=True, py_to_pyx=True)
            modules = collect_modules(root, config)
            self.assertEqual(
                sorted(m.dotted for m in modules), ["myapp.core", "myapp.speed"]
            )
            core = next(m for m in modules if m.name == "core")
            self.assertTrue(core.converted)
            self.assertEqual(core.source, Path(STAGING_DIR, "myapp", "core.pyx"))
            self.assertEqual(
                (root / core.source).read_text(), "def add(a, b): return a + b\n"
            )

    def test_init_is_never_converted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root)
            config = CythonizeConfig(cythonize=True, py_to_pyx=True)
            modules = collect_modules(root, config)
            self.assertNotIn("__init__", [m.name for m in modules])

    def test_exclude_keeps_module_as_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root)
            _write(root / "myapp" / "config.py", "SETTING = 1\n")
            config = CythonizeConfig(
                cythonize=True, py_to_pyx=True, exclude=["config.py"]
            )
            modules = collect_modules(root, config)
            self.assertNotIn("config", [m.name for m in modules])

    def test_py_is_skipped_when_a_pyx_of_the_same_name_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root)
            _write(root / "myapp" / "speed.py", "def fast(a): return a\n")
            config = CythonizeConfig(cythonize=True, py_to_pyx=True)
            modules = collect_modules(root, config)
            speed = [m for m in modules if m.name == "speed"]
            self.assertEqual(len(speed), 1)
            self.assertFalse(speed[0].converted)

    def test_allow_py_to_pyx_false_skips_conversion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root)
            config = CythonizeConfig(cythonize=True, py_to_pyx=True)
            modules = collect_modules(root, config, allow_py_to_pyx=False)
            self.assertEqual([m.dotted for m in modules], ["myapp.speed"])

    def test_unchanged_source_is_not_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root)
            config = CythonizeConfig(cythonize=True, py_to_pyx=True)
            collect_modules(root, config)
            staged = root / STAGING_DIR / "myapp" / "core.pyx"
            before = staged.stat().st_mtime_ns
            collect_modules(root, config)
            self.assertEqual(staged.stat().st_mtime_ns, before)

    def test_stale_staged_source_is_pruned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root)
            config = CythonizeConfig(cythonize=True, py_to_pyx=True)
            collect_modules(root, config)
            self.assertTrue((root / STAGING_DIR / "myapp" / "core.pyx").exists())

            (root / "myapp" / "core.py").unlink()
            collect_modules(root, config)
            self.assertFalse((root / STAGING_DIR / "myapp" / "core.pyx").exists())


class TestCythonBuild(unittest.TestCase):
    def test_no_op_without_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = setuptools.setup
            with cython_build(Path(tmp)):
                self.assertIs(setuptools.setup, original)

    def test_no_op_when_py_to_pyx_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "pyproject.toml", "[tool.ksp-builder]\npy_to_pyx = true\n")
            _write(root / "myapp" / "__init__.py")
            _write(root / "myapp" / "core.py", "def add(a, b): return a + b\n")
            original = setuptools.setup
            with cython_build(root):
                self.assertIs(setuptools.setup, original)
            self.assertFalse((root / STAGING_DIR).exists())

    def test_extensions_are_injected_into_setup_and_py_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "pyproject.toml",
                '[tool.setuptools]\npackages = ["myapp"]\n'
                "[tool.ksp-builder]\ncythonize = true\npy_to_pyx = true\n",
            )
            _write(root / "myapp" / "__init__.py")
            _write(root / "myapp" / "core.py", "def add(a, b): return a + b\n")

            recorded = {}

            def fake_setup(**attrs):
                recorded.update(attrs)

            original = setuptools.setup
            setuptools.setup = fake_setup
            try:
                cwd = Path.cwd()
                import os

                os.chdir(root)
                try:
                    with cython_build(root):
                        self.assertIsNot(setuptools.setup, fake_setup)
                        setuptools.setup()
                finally:
                    os.chdir(cwd)
                self.assertIs(setuptools.setup, fake_setup)
            finally:
                setuptools.setup = original

            names = [ext.name for ext in recorded["ext_modules"]]
            self.assertEqual(names, ["myapp.core"])
            self.assertIn("build_py", recorded["cmdclass"])

    def test_keep_py_leaves_build_py_alone(self):
        # A distinct package/module name: Cython caches dependency state by
        # relative source path, and every build here runs in one process.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "pyproject.toml",
                '[tool.setuptools]\npackages = ["keptapp"]\n'
                "[tool.ksp-builder]\ncythonize = true\npy_to_pyx = true\n"
                "cythonize_keep_py = true\n",
            )
            _write(root / "keptapp" / "__init__.py")
            _write(root / "keptapp" / "kept.py", "def add(a, b): return a + b\n")

            recorded = {}
            original = setuptools.setup
            setuptools.setup = lambda **attrs: recorded.update(attrs)
            try:
                import os

                cwd = Path.cwd()
                os.chdir(root)
                try:
                    with cython_build(root):
                        setuptools.setup()
                finally:
                    os.chdir(cwd)
            finally:
                setuptools.setup = original

            self.assertEqual(len(recorded["ext_modules"]), 1)
            self.assertNotIn("cmdclass", recorded)


if __name__ == "__main__":
    unittest.main()
