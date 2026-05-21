import unittest

from setuptools import build_meta as setuptools_build_meta

import ksp_builder


class TestKspBuilderBackend(unittest.TestCase):
    def test_required_pep517_hooks_delegate_to_setuptools(self):
        self.assertIs(ksp_builder.build_wheel, setuptools_build_meta.build_wheel)
        self.assertIs(ksp_builder.build_sdist, setuptools_build_meta.build_sdist)
        self.assertIs(
            ksp_builder.get_requires_for_build_wheel,
            setuptools_build_meta.get_requires_for_build_wheel,
        )
        self.assertIs(
            ksp_builder.get_requires_for_build_sdist,
            setuptools_build_meta.get_requires_for_build_sdist,
        )
        self.assertIs(
            ksp_builder.prepare_metadata_for_build_wheel,
            setuptools_build_meta.prepare_metadata_for_build_wheel,
        )

    def test_optional_pep660_hooks_follow_setuptools_availability(self):
        for hook in (
            "build_editable",
            "get_requires_for_build_editable",
            "prepare_metadata_for_build_editable",
        ):
            self.assertIs(getattr(ksp_builder, hook), getattr(setuptools_build_meta, hook, None))

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
