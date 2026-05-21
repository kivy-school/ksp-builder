"""ksp_builder._java — delegates Java source injection to pyjnius-builder."""
from __future__ import annotations

from pyjnius_builder.backend import (
    JAVA_ARCHIVE_PREFIX,
    add_java_sources_to_sdist,
    add_java_sources_to_wheel,
    get_java_source_dirs,
)

__all__ = [
    "JAVA_ARCHIVE_PREFIX",
    "add_java_sources_to_sdist",
    "add_java_sources_to_wheel",
    "get_java_source_dirs",
]
