"""ksp_builder._gradle — generates and injects .gradle/<package_name>.json into wheels/sdists."""
from __future__ import annotations

import base64
import csv
import hashlib
import json
import tarfile
import tempfile
import zipfile
from io import BytesIO, StringIO
from pathlib import Path

from ._kivy_school import AndroidConfig

GRADLE_ARCHIVE_PREFIX = ".gradle"


def generate_gradle_json(config: AndroidConfig) -> bytes:
    """Serialise AndroidConfig to JSON bytes."""
    data = {
        "package_name": config.package_name,
        "gradle_dependencies": config.gradle_dependencies,
        "permissions": config.permissions,
        "meta_data": config.meta_data,
    }
    return json.dumps(data, indent=2).encode("utf-8")


def _get_pypi_hash(data: bytes) -> str:
    """Calculates the urlsafe base64 sha256 hash required by PEP 376 / PEP 427."""
    digest = hashlib.sha256(data).digest()
    return "sha256=" + base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def inject_gradle_config_to_wheel(wheel_path: Path, config: AndroidConfig) -> None:
    """Safely append .gradle/<package_name>.json to a wheel and update the RECORD manifest."""
    content = generate_gradle_json(config)
    archive_name = f"{GRADLE_ARCHIVE_PREFIX}/{config.package_name}.json"

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_wheel_path = Path(tmpdir) / "rewritten.whl"

        with zipfile.ZipFile(wheel_path, "r") as old_wheel:
            record_path = next((name for name in old_wheel.namelist() if name.endswith(".dist-info/RECORD")), None)
            if not record_path:
                raise FileNotFoundError("Could not find RECORD file in the generated wheel.")

            record_data = old_wheel.read(record_path).decode("utf-8")

            with zipfile.ZipFile(temp_wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as new_wheel:
                for item in old_wheel.infolist():
                    if item.filename != record_path:
                        new_wheel.writestr(item, old_wheel.read(item.filename))

                record_io = StringIO()
                csv_writer = csv.writer(record_io, lineterminator="\n")

                csv_reader = csv.reader(StringIO(record_data))
                for row in csv_reader:
                    csv_writer.writerow(row)

                new_wheel.writestr(archive_name, content)

                file_hash = _get_pypi_hash(content)
                file_size = len(content)
                csv_writer.writerow([archive_name, file_hash, file_size])

                new_wheel.writestr(record_path, record_io.getvalue().encode("utf-8"))

        temp_wheel_path.replace(wheel_path)


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
