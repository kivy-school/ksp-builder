"""ksp_builder._kivy_school — reads [tool.kivy-school] config from pyproject.toml."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AndroidConfig:
    """Android-specific configuration from [tool.kivy-school.android]."""

    package_name: str
    gradle_dependencies: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)


def read_android_config(project_root: Path) -> AndroidConfig | None:
    """Read [tool.kivy-school.android] from pyproject.toml.

    Returns None if the section is absent or has no package_name.
    """
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return None

    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    android_data = data.get("tool", {}).get("kivy-school", {}).get("android", {})

    package_name = android_data.get("package_name")
    if not package_name:
        return None

    return AndroidConfig(
        package_name=package_name,
        gradle_dependencies=list(android_data.get("gradle_dependencies", [])),
        permissions=list(android_data.get("permissions", [])),
    )
