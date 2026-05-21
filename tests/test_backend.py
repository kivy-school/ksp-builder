import unittest

from setuptools import build_meta as setuptools_build_meta

import ksp_builder


class TestKspBuilderBackend(unittest.TestCase):
    def test_required_pep517_hooks_are_callable(self):
        for hook in (
            "build_wheel",
            "build_sdist",
            "get_requires_for_build_wheel",
            "get_requires_for_build_sdist",
            "prepare_metadata_for_build_wheel",
        ):
            self.assertTrue(
                callable(getattr(ksp_builder, hook)),
                f"{hook} should be callable",
            )

    def test_passthrough_hooks_delegate_to_setuptools(self):
        # These hooks have no extra logic in ksp_builder and should still
        # point directly at setuptools.
        for hook in (
            "get_requires_for_build_wheel",
            "get_requires_for_build_sdist",
            "prepare_metadata_for_build_wheel",
        ):
            self.assertIs(
                getattr(ksp_builder, hook),
                getattr(setuptools_build_meta, hook),
                f"{hook} should delegate unchanged to setuptools",
            )

    def test_build_wheel_is_ksp_implementation(self):
        # build_wheel is overridden to add Java, Swift and gradle injection steps.
        self.assertIsNot(ksp_builder.build_wheel, setuptools_build_meta.build_wheel)
        self.assertTrue(callable(ksp_builder.build_wheel))

    def test_build_sdist_is_ksp_implementation(self):
        self.assertIsNot(ksp_builder.build_sdist, setuptools_build_meta.build_sdist)
        self.assertTrue(callable(ksp_builder.build_sdist))

    def test_optional_pep660_hooks_follow_setuptools_availability(self):
        for hook in (
            "get_requires_for_build_editable",
            "prepare_metadata_for_build_editable",
        ):
            # These are pass-throughs, so they should match setuptools exactly.
            self.assertIs(
                getattr(ksp_builder, hook, None),
                getattr(setuptools_build_meta, hook, None),
                f"{hook} should delegate unchanged to setuptools when available",
            )

    def test_build_editable_available_when_setuptools_supports_it(self):
        if getattr(setuptools_build_meta, "build_editable", None) is None:
            self.assertNotIn("build_editable", ksp_builder.__all__)
        else:
            self.assertIn("build_editable", ksp_builder.__all__)
            self.assertTrue(callable(ksp_builder.build_editable))
            # build_editable is overridden (adds injection steps).
            self.assertIsNot(
                ksp_builder.build_editable,
                setuptools_build_meta.build_editable,
            )

    def test_all_exports_only_available_hooks(self):
        self.assertIn("build_wheel", ksp_builder.__all__)
        for hook in (
            "build_editable",
            "get_requires_for_build_editable",
            "prepare_metadata_for_build_editable",
        ):
            if getattr(setuptools_build_meta, hook, None) is None:
                self.assertNotIn(hook, ksp_builder.__all__)
            else:
                self.assertIn(hook, ksp_builder.__all__)


if __name__ == "__main__":
    unittest.main()

