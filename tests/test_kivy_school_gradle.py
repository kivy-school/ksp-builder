import json
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from ksp_builder._kivy_school import AndroidConfig, read_android_config
from ksp_builder._gradle import (
    GRADLE_ARCHIVE_PREFIX,
    generate_gradle_json,
    inject_gradle_config_to_sdist,
    inject_gradle_config_to_wheel,
)


class TestReadAndroidConfig(unittest.TestCase):
    def _write_pyproject(self, tmp: Path, content: str) -> None:
        (tmp / "pyproject.toml").write_text(content, encoding="utf-8")

    def test_returns_none_when_no_pyproject(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(read_android_config(Path(tmp)))

    def test_returns_none_when_section_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_pyproject(Path(tmp), "[project]\nname = 'x'\n")
            self.assertIsNone(read_android_config(Path(tmp)))

    def test_returns_none_when_package_name_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_pyproject(
                Path(tmp),
                "[tool.kivy-school.android]\npermissions = []\n",
            )
            self.assertIsNone(read_android_config(Path(tmp)))

    def test_falls_back_to_project_name(self):
        content = """
[project]
name = "pyonesignal"

[tool.kivy-school.android]
gradle_dependencies = ["com.onesignal:OneSignal:[5.6.1, 5.9.99]"]
permissions = ["POST_NOTIFICATIONS", "INTERNET"]
"""
        with tempfile.TemporaryDirectory() as tmp:
            self._write_pyproject(Path(tmp), content)
            config = read_android_config(Path(tmp))

        self.assertIsNotNone(config)
        self.assertEqual(config.package_name, "pyonesignal")
        self.assertEqual(
            config.gradle_dependencies,
            ["com.onesignal:OneSignal:[5.6.1, 5.9.99]"],
        )
        self.assertEqual(config.permissions, ["POST_NOTIFICATIONS", "INTERNET"])

    def test_reads_full_config(self):
        content = """
[tool.kivy-school]
app_name = "MyApp"

[tool.kivy-school.android]
package_name = "org.example.myapp"
gradle_dependencies = ["com.google.firebase:firebase-analytics:21.0.0"]
permissions = ["INTERNET", "CAMERA"]
"""
        with tempfile.TemporaryDirectory() as tmp:
            self._write_pyproject(Path(tmp), content)
            config = read_android_config(Path(tmp))

        self.assertIsNotNone(config)
        self.assertEqual(config.package_name, "org.example.myapp")
        self.assertEqual(
            config.gradle_dependencies,
            ["com.google.firebase:firebase-analytics:21.0.0"],
        )
        self.assertEqual(config.permissions, ["INTERNET", "CAMERA"])

    def test_reads_config_with_empty_lists(self):
        content = """
[tool.kivy-school.android]
package_name = "org.example.empty"
"""
        with tempfile.TemporaryDirectory() as tmp:
            self._write_pyproject(Path(tmp), content)
            config = read_android_config(Path(tmp))

        self.assertIsNotNone(config)
        self.assertEqual(config.package_name, "org.example.empty")
        self.assertEqual(config.gradle_dependencies, [])
        self.assertEqual(config.permissions, [])


class TestGenerateGradleJson(unittest.TestCase):
    def test_json_structure(self):
        config = AndroidConfig(
            package_name="org.example.myapp",
            gradle_dependencies=["com.example:lib:1.0"],
            permissions=["INTERNET"],
        )
        raw = generate_gradle_json(config)
        data = json.loads(raw)
        self.assertEqual(data["package_name"], "org.example.myapp")
        self.assertEqual(data["gradle_dependencies"], ["com.example:lib:1.0"])
        self.assertEqual(data["permissions"], ["INTERNET"])

    def test_json_is_valid_utf8(self):
        config = AndroidConfig(package_name="org.example.app")
        raw = generate_gradle_json(config)
        self.assertIsInstance(raw, bytes)
        raw.decode("utf-8")  # must not raise


class TestInjectGradleConfigToWheel(unittest.TestCase):
    def _make_empty_wheel(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("dummy/__init__.py", "")

    def test_injects_gradle_json(self):
        config = AndroidConfig(
            package_name="org.example.myapp",
            gradle_dependencies=["com.example:lib:1.0"],
            permissions=["INTERNET"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            wheel_path = Path(tmp) / "test-0.1-py3-none-any.whl"
            self._make_empty_wheel(wheel_path)

            inject_gradle_config_to_wheel(wheel_path, config)

            with zipfile.ZipFile(wheel_path) as zf:
                names = zf.namelist()
                expected = f"{GRADLE_ARCHIVE_PREFIX}/org.example.myapp.json"
                self.assertIn(expected, names)
                data = json.loads(zf.read(expected))
                self.assertEqual(data["package_name"], "org.example.myapp")
                self.assertEqual(data["gradle_dependencies"], ["com.example:lib:1.0"])
                self.assertEqual(data["permissions"], ["INTERNET"])


class TestInjectGradleConfigToSdist(unittest.TestCase):
    def _make_sdist(self, path: Path) -> None:
        with tarfile.open(path, "w:gz") as tf:
            content = b"[project]\nname = 'x'\n"
            info = tarfile.TarInfo(name="mypackage-0.1/pyproject.toml")
            info.size = len(content)
            import io
            tf.addfile(info, io.BytesIO(content))

    def test_injects_gradle_json(self):
        config = AndroidConfig(
            package_name="org.example.myapp",
            permissions=["WAKE_LOCK"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            sdist_path = Path(tmp) / "mypackage-0.1.tar.gz"
            self._make_sdist(sdist_path)

            inject_gradle_config_to_sdist(sdist_path, config)

            with tarfile.open(sdist_path, "r:gz") as tf:
                names = [m.name for m in tf.getmembers()]
                expected = f"mypackage-0.1/{GRADLE_ARCHIVE_PREFIX}/org.example.myapp.json"
                self.assertIn(expected, names)
                f = tf.extractfile(expected)
                data = json.loads(f.read())
                self.assertEqual(data["permissions"], ["WAKE_LOCK"])

    def test_preserves_existing_members(self):
        config = AndroidConfig(package_name="org.example.app")
        with tempfile.TemporaryDirectory() as tmp:
            sdist_path = Path(tmp) / "pkg-0.1.tar.gz"
            self._make_sdist(sdist_path)

            inject_gradle_config_to_sdist(sdist_path, config)

            with tarfile.open(sdist_path, "r:gz") as tf:
                names = [m.name for m in tf.getmembers()]
                self.assertIn("mypackage-0.1/pyproject.toml", names)


if __name__ == "__main__":
    unittest.main()
