"""ksp_builder._gradle — generates and injects .gradle/<package_name>.json into wheels/sdists."""
from __future__ import annotations

import json
import tarfile
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

from ._kivy_school import AndroidConfig

GRADLE_ARCHIVE_PREFIX = ".gradle"


def generate_gradle_json(config: AndroidConfig) -> bytes:
    """Serialise AndroidConfig to JSON bytes."""
    data = {
        "package_name": config.package_name,
        "gradle_dependencies": config.gradle_dependencies,
        "permissions": config.permissions,
    }
    return json.dumps(data, indent=2).encode("utf-8")


def inject_gradle_config_to_wheel(wheel_path: Path, config: AndroidConfig) -> None:
    """Append .gradle/<package_name>.json to an existing wheel zip."""
    content = generate_gradle_json(config)
    archive_name = f"{GRADLE_ARCHIVE_PREFIX}/{config.package_name}.json"
    with zipfile.ZipFile(wheel_path, "a", compression=zipfile.ZIP_DEFLATED) as wheel:
        wheel.writestr(archive_name, content)


def inject_gradle_config_to_sdist(sdist_path: Path, config: AndroidConfig) -> None:
    """Rewrite a .tar.gz sdist to include .gradle/<package_name>.json."""
    content = generate_gradle_json(config)
    archive_name = f"{GRADLE_ARCHIVE_PREFIX}/{config.package_name}.json"

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir) / "rewritten.tar.gz"
        with tarfile.open(sdist_path, "r:gz") as src_tar:
            members = src_tar.getmembers()
            root_prefix = members[0].name.split("/", 1)[0] if members else ""

            with tarfile.open(temp_path, "w:gz") as new_tar:
                for member in members:
                    if member.isfile():
                        extracted = src_tar.extractfile(member)
                        if extracted is None:
                            continue
                        with extracted:
                            new_tar.addfile(member, extracted)
                    else:
                        new_tar.addfile(member)

                tar_info = tarfile.TarInfo(
                    name=f"{root_prefix}/{archive_name}" if root_prefix else archive_name
                )
                tar_info.size = len(content)
                new_tar.addfile(tar_info, BytesIO(content))

        temp_path.replace(sdist_path)
