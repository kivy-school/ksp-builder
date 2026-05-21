import tempfile
import unittest
import zipfile
from pathlib import Path

from ksp_builder._java import (
    JAVA_ARCHIVE_PREFIX,
    add_java_sources_to_wheel,
    get_java_source_dirs,
)


class TestGetJavaSourceDirs(unittest.TestCase):
    def test_returns_empty_when_no_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "pyproject.toml").write_text(
                "[project]\nname = 'x'\n", encoding="utf-8"
            )
            dirs = get_java_source_dirs(project_root=Path(tmp))
        self.assertEqual(dirs, [])

    def test_reads_java_paths_from_pyproject(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            java_dir = root / "java"
            java_dir.mkdir()
            (root / "pyproject.toml").write_text(
                '[tool.pyjnius]\njava-paths = ["java"]\n', encoding="utf-8"
            )
            dirs = get_java_source_dirs(project_root=root)
        self.assertEqual(dirs, [java_dir.resolve()])

    def test_raises_on_missing_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text(
                '[tool.pyjnius]\njava-paths = ["nonexistent"]\n', encoding="utf-8"
            )
            with self.assertRaises(FileNotFoundError):
                get_java_source_dirs(project_root=root)


class TestAddJavaSourcesToWheel(unittest.TestCase):
    def _make_wheel(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("pkg/__init__.py", "")

    def test_injects_java_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            java_dir = root / "java"
            java_dir.mkdir()
            (java_dir / "MyClass.java").write_text(
                "public class MyClass {}", encoding="utf-8"
            )

            wheel_path = root / "pkg-0.1-py3-none-any.whl"
            self._make_wheel(wheel_path)

            add_java_sources_to_wheel(wheel_path, [java_dir])

            with zipfile.ZipFile(wheel_path) as zf:
                names = zf.namelist()
                self.assertIn(f"{JAVA_ARCHIVE_PREFIX}/MyClass.java", names)

    def test_noop_when_no_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            wheel_path = Path(tmp) / "pkg-0.1-py3-none-any.whl"
            self._make_wheel(wheel_path)
            before = zipfile.ZipFile(wheel_path).namelist()
            add_java_sources_to_wheel(wheel_path, [])
            after = zipfile.ZipFile(wheel_path).namelist()
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
