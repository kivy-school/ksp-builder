from setuptools import build_meta as _setuptools_backend

__all__ = [
    "build_wheel",
    "build_sdist",
    "get_requires_for_build_wheel",
    "get_requires_for_build_sdist",
    "prepare_metadata_for_build_wheel",
    "build_editable",
    "get_requires_for_build_editable",
    "prepare_metadata_for_build_editable",
]

build_wheel = _setuptools_backend.build_wheel
build_sdist = _setuptools_backend.build_sdist
get_requires_for_build_wheel = _setuptools_backend.get_requires_for_build_wheel
get_requires_for_build_sdist = _setuptools_backend.get_requires_for_build_sdist
prepare_metadata_for_build_wheel = _setuptools_backend.prepare_metadata_for_build_wheel

build_editable = getattr(_setuptools_backend, "build_editable", None)
get_requires_for_build_editable = getattr(
    _setuptools_backend, "get_requires_for_build_editable", None
)
prepare_metadata_for_build_editable = getattr(
    _setuptools_backend, "prepare_metadata_for_build_editable", None
)
