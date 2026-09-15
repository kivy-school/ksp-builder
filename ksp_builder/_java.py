"""ksp_builder._java — delegates Java source injection to ksp-java."""
from __future__ import annotations

from ksp_java.backend import (
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
