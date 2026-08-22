#!/usr/bin/env python3
"""Regression tests for the independent release ZIP validator."""

from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools" / "validate_release_package.py"
VERSION = "1.2.5"
PACKAGE_ROOT = f"TravellingAtNight_ZH-CN_v{VERSION}"


OUTER_FILES = {
    "installer/安装汉化.ps1": b"Write-Host install\n",
    "installer/卸载汉化.ps1": b"Write-Host uninstall\n",
    "installer/Resolve-GamePath.ps1": b"function Resolve-TravellingGamePath {}\n",
    "一键安装.bat": b"@echo off\r\n",
    "一键卸载.bat": b"@echo off\r\n",
    "README_安装说明.md": b"# install instructions\n",
    "术语表与译名说明.md": b"# terminology notes\n",
    "术语表与译名说明.txt": b"terminology notes txt\n",
    "licenses/BepInEx-MIT.txt": b"B" * 128,
    "licenses/NotoSansSC-OFL.txt": b"N" * 128,
    "licenses/THIRD_PARTY_NOTICES.md": b"T" * 128,
    "licenses/BepInExHarmony-MIT.txt": b"H" * 128,
    "licenses/HarmonyX-MIT.txt": b"X" * 128,
    "licenses/Harmony-original-MIT.txt": b"O" * 128,
    "licenses/MonoMod-MIT.txt": b"M" * 128,
    "licenses/MonoCecil-MIT.txt": b"C" * 128,
    "licenses/UnityDoorstop-LGPL-2.1.txt": b"L" * 128,
    "licenses/UnityDoorstop-v4.5.0-source.zip": b"S" * 128,
}


def json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def make_archive(
    directory: Path,
    *,
    filename_version: str = VERSION,
    root_version: str = VERSION,
    manifest_version: str = VERSION,
) -> Path:
    archive_path = directory / f"TravellingAtNight_ZH-CN_v{filename_version}.zip"
    package_root = f"TravellingAtNight_ZH-CN_v{root_version}"
    catalog = {"0" * 64: "译文"}
    links = {"1" * 64: "链接"}
    payload = {
        "BepInEx/plugins/TravellingCN/catalog.zh-CN.json": json_bytes(catalog),
        "BepInEx/plugins/TravellingCN/link_targets.zh-CN.json": json_bytes(links),
        "BepInEx/plugins/TravellingCN/TravellingCN.dll": b"test plugin",
        "BepInEx/plugins/TravellingCN/font/NotoSansCJKsc-Regular.otf": b"test font",
    }
    manifest = {
        "schema_version": 2,
        "patch_version": manifest_version,
        "translation_count": len(catalog),
        "files": [
            {
                "path": path.replace("/", "\\"),
                "sha256": hashlib.sha256(data).hexdigest().upper(),
                "size": len(data),
            }
            for path, data in payload.items()
        ],
        "outer_files": [
            {
                "path": path.replace("/", "\\"),
                "sha256": hashlib.sha256(data).hexdigest().upper(),
                "size": len(data),
            }
            for path, data in OUTER_FILES.items()
        ],
    }

    # Stored entries make the corruption test deterministic and inexpensive.
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(f"{package_root}/payload-manifest.json", json_bytes(manifest))
        for path, data in OUTER_FILES.items():
            archive.writestr(f"{package_root}/{path}", data)
        for path, data in payload.items():
            archive.writestr(f"{package_root}/payload/{path}", data)
    return archive_path


def rewrite_archive(
    archive_path: Path,
    *,
    replace: dict[str, bytes] | None = None,
    remove: set[str] | None = None,
    add: dict[str, bytes] | None = None,
) -> None:
    replace = replace or {}
    remove = remove or set()
    add = add or {}
    with zipfile.ZipFile(archive_path, "r") as archive:
        members = {info.filename: archive.read(info) for info in archive.infolist() if not info.is_dir()}
    for name in remove:
        members.pop(name)
    members.update(replace)
    members.update(add)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)


def corrupt_member(archive_path: Path, member_name: str) -> None:
    with zipfile.ZipFile(archive_path, "r") as archive:
        info = archive.getinfo(member_name)
        header_offset = info.header_offset
    with archive_path.open("r+b") as stream:
        stream.seek(header_offset + 26)
        filename_length, extra_length = struct.unpack("<HH", stream.read(4))
        data_offset = header_offset + 30 + filename_length + extra_length
        stream.seek(data_offset)
        first_byte = stream.read(1)
        stream.seek(data_offset)
        stream.write(bytes([first_byte[0] ^ 0x01]))


def run_validator(archive_path: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-B", str(VALIDATOR), str(archive_path), "--expected-version", VERSION],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
    )


class ReleaseValidatorTests(unittest.TestCase):
    def test_valid_archive_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = run_validator(make_archive(Path(temporary_directory)))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"status": "ok"', result.stdout)

    def test_rejects_top_level_version_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = run_validator(make_archive(Path(temporary_directory), root_version="1.2.0"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("ZIP 顶层目录", result.stderr)

    def test_rejects_archive_filename_version_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = run_validator(make_archive(Path(temporary_directory), filename_version="1.2.0"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("ZIP 文件名", result.stderr)

    def test_rejects_corrupt_outer_member_crc(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive_path = make_archive(Path(temporary_directory))
            member_name = f"{PACKAGE_ROOT}/installer/安装汉化.ps1"
            corrupt_member(archive_path, member_name)
            result = run_validator(archive_path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("CRC", result.stderr)

    def test_rejects_tampered_outer_files(self) -> None:
        targets = (
            "installer/安装汉化.ps1",
            "installer/卸载汉化.ps1",
            "README_安装说明.md",
            "licenses/BepInEx-MIT.txt",
        )
        for target in targets:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temporary_directory:
                archive_path = make_archive(Path(temporary_directory))
                member_name = f"{PACKAGE_ROOT}/{target}"
                rewrite_archive(archive_path, replace={member_name: OUTER_FILES[target] + b"tampered"})
                result = run_validator(archive_path)
            self.assertEqual(result.returncode, 1)
            self.assertIn("文件", result.stderr)

    def test_rejects_undeclared_added_member(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive_path = make_archive(Path(temporary_directory))
            rewrite_archive(archive_path, add={f"{PACKAGE_ROOT}/surprise.txt": b"surprise"})
            result = run_validator(archive_path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("ZIP 成员集合", result.stderr)

    def test_rejects_removed_declared_member(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive_path = make_archive(Path(temporary_directory))
            rewrite_archive(archive_path, remove={f"{PACKAGE_ROOT}/installer/卸载汉化.ps1"})
            result = run_validator(archive_path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("ZIP 成员集合", result.stderr)

    def test_rejects_case_insensitive_duplicate_member(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive_path = make_archive(Path(temporary_directory))
            rewrite_archive(
                archive_path,
                add={f"{PACKAGE_ROOT}/LICENSES/BepInEx-MIT.txt": b"duplicate"},
            )
            result = run_validator(archive_path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("忽略大小写", result.stderr)


if __name__ == "__main__":
    unittest.main()
