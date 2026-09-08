import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from ksp_builder._pre_post_build import (
    BuildScripts,
    read_build_scripts,
    run_after_build,
    run_before_build,
)


class TestReadBuildScripts(unittest.TestCase):
    def _write_pyproject(self, tmp: Path, content: str) -> None:
        (tmp / "pyproject.toml").write_text(content, encoding="utf-8")

    def test_returns_none_when_no_pyproject(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(read_build_scripts(Path(tmp)))

    def test_returns_none_when_section_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_pyproject(Path(tmp), "[project]\nname = 'x'\n")
            self.assertIsNone(read_build_scripts(Path(tmp)))

    def test_returns_none_when_section_has_neither_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_pyproject(
                Path(tmp), "[tool.ksp-builder]\ncythonize = true\n"
            )
            self.assertIsNone(read_build_scripts(Path(tmp)))

    def test_reads_both_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_pyproject(
                root,
                "[tool.ksp-builder]\n"
                'before_build = "scripts/before.py"\n'
                'after_build = "scripts/after.py"\n',
            )
            scripts = read_build_scripts(root)
            self.assertIsNotNone(scripts)
            self.assertEqual(scripts.before_build, root / "scripts" / "before.py")
            self.assertEqual(scripts.after_build, root / "scripts" / "after.py")

    def test_only_before_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_pyproject(
                root, "[tool.ksp-builder]\nbefore_build = \"before.py\"\n"
            )
            scripts = read_build_scripts(root)
            self.assertEqual(scripts.before_build, root / "before.py")
            self.assertIsNone(scripts.after_build)

    def test_absolute_path_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            absolute = Path(tmp) / "elsewhere" / "after.py"
            self._write_pyproject(
                root, f"[tool.ksp-builder]\nafter_build = '{absolute}'\n"
            )
            self.assertEqual(read_build_scripts(root).after_build, absolute)


class TestRunBuildScripts(unittest.TestCase):
    def _project(self, tmp: Path, *, before: str | None = None, after: str | None = None) -> None:
        lines = ["[tool.ksp-builder]"]
        if before is not None:
            lines.append(f'before_build = "{before}"')
        if after is not None:
            lines.append(f'after_build = "{after}"')
        (tmp / "pyproject.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_no_config_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_before_build(Path(tmp), "wheel")
            run_after_build(Path(tmp), "wheel", Path(tmp) / "x.whl")

    def test_before_build_script_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root, before="before.py")
            (root / "before.py").write_text(
                "import os, pathlib\n"
                "pathlib.Path('ran.txt').write_text(os.environ['KSP_BUILD_TARGET'])\n",
                encoding="utf-8",
            )
            run_before_build(root, "wheel")
            self.assertEqual((root / "ran.txt").read_text(), "wheel")

    def test_after_build_script_receives_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "dist" / "pkg-1.0-py3-none-any.whl"
            self._project(root, after="after.py")
            (root / "after.py").write_text(
                "import os, pathlib, sys\n"
                "pathlib.Path('ran.txt').write_text(\n"
                "    sys.argv[1] + '\\n' + os.environ['KSP_BUILD_ARTIFACT']\n"
                ")\n",
                encoding="utf-8",
            )
            run_after_build(root, "sdist", artifact)
            self.assertEqual(
                (root / "ran.txt").read_text(), f"{artifact}\n{artifact}"
            )

    def test_before_build_does_not_run_after_hook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root, after="after.py")
            (root / "after.py").write_text("raise SystemExit(1)\n", encoding="utf-8")
            run_before_build(root, "wheel")  # only after_build is configured

    def test_missing_script_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root, before="nope.py")
            with self.assertRaises(FileNotFoundError):
                run_before_build(root, "wheel")

    def test_failing_script_fails_the_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root, before="before.py")
            (root / "before.py").write_text("raise SystemExit(3)\n", encoding="utf-8")
            with self.assertRaises(subprocess.CalledProcessError):
                run_before_build(root, "wheel")

    @unittest.skipIf(os.name == "nt", "POSIX executable bit")
    def test_non_python_script_runs_directly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root, before="before.sh")
            script = root / "before.sh"
            script.write_text("#!/bin/sh\nprintf %s \"$KSP_BUILD_TARGET\" > ran.txt\n", encoding="utf-8")
            script.chmod(0o755)
            run_before_build(root, "wheel")
            self.assertEqual((root / "ran.txt").read_text(), "wheel")

    @unittest.skipIf(os.name == "nt", "POSIX executable bit")
    def test_extensionless_script_runs_directly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root, after="hooks/after")
            script = root / "hooks" / "after"
            script.parent.mkdir()
            script.write_text('#!/bin/sh\nprintf %s "$1" > ran.txt\n', encoding="utf-8")
            script.chmod(0o755)
            artifact = root / "dist" / "pkg-1.0.tar.gz"
            run_after_build(root, "sdist", artifact)
            self.assertEqual((root / "ran.txt").read_text(), str(artifact))

    @unittest.skipIf(os.name == "nt", "POSIX executable bit")
    def test_non_executable_non_python_script_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root, before="before.sh")
            script = root / "before.sh"
            script.write_text("#!/bin/sh\ntrue\n", encoding="utf-8")
            script.chmod(0o644)
            with self.assertRaises(PermissionError):
                run_before_build(root, "wheel")

    def test_python_script_needs_no_executable_bit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root, before="before.py")
            script = root / "before.py"
            script.write_text("open('ran.txt', 'w').close()\n", encoding="utf-8")
            script.chmod(0o644)
            run_before_build(root, "wheel")
            self.assertTrue((root / "ran.txt").exists())


if __name__ == "__main__":
    unittest.main()
