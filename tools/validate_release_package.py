#!/usr/bin/env python3
"""Validate a TravellingCN release archive without installing it.

This is intentionally independent from the installer.  It checks archive path
safety, the payload manifest, every payload hash, and the two runtime catalogs.
It never extracts or modifies the archive.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath


SHA256_RE = re.compile(r"[0-9a-f]{64}")
PATCH_VERSION_RE = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")
PACKAGE_PREFIX = "TravellingAtNight_ZH-CN_v"
REQUIRED_OUTER = {
    "installer/安装汉化.ps1",
    "installer/卸载汉化.ps1",
    "installer/Resolve-GamePath.ps1",
    "README_安装说明.md",
    "术语表与译名说明.md",
    "术语表与译名说明.txt",
    "一键安装.bat",
    "一键卸载.bat",
    "licenses/BepInEx-MIT.txt",
    "licenses/NotoSansSC-OFL.txt",
    "licenses/THIRD_PARTY_NOTICES.md",
    "licenses/BepInExHarmony-MIT.txt",
    "licenses/HarmonyX-MIT.txt",
    "licenses/Harmony-original-MIT.txt",
    "licenses/MonoMod-MIT.txt",
    "licenses/MonoCecil-MIT.txt",
    "licenses/UnityDoorstop-LGPL-2.1.txt",
    "licenses/UnityDoorstop-v4.5.0-source.zip",
}


def fail(message: str) -> None:
    raise ValueError(message)


def load_json(data: bytes, label: str):
    try:
        return json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"{label} 不是有效的 UTF-8 JSON：{exc}")


def normalise_member(name: str) -> str:
    normalised = name.replace("\\", "/")
    path = PurePosixPath(normalised)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        fail(f"ZIP 包含不安全路径：{name!r}")
    if ":" in path.parts[0]:
        fail(f"ZIP 包含盘符路径：{name!r}")
    return path.as_posix()


def validate_catalog(data: bytes, label: str, expected_count: int | None = None) -> int:
    catalog = load_json(data, label)
    if not isinstance(catalog, dict):
        fail(f"{label} 顶层必须是 JSON 对象。")
    # catalog 在译文精确条目之上还收录渲染形态变体（去首尾空白、折叠 [[链接]]
    # 的派生键，见 merge_and_validate_translations.py），因此条目数只会多于
    # 清单声明的译文条数（worklist 行数）；少于则一定是漏译，必须失败。
    if expected_count is not None and len(catalog) < expected_count:
        fail(f"{label} 条目数为 {len(catalog)}，少于清单声明的 {expected_count}。")
    for key, value in catalog.items():
        if not isinstance(key, str) or SHA256_RE.fullmatch(key) is None:
            fail(f"{label} 含非 SHA-256 键：{key!r}")
        if not isinstance(value, str) or not value:
            fail(f"{label} 含空值或非字符串值：{key}")
        if "\ufffd" in value or "\x00" in value:
            fail(f"{label} 含损坏字符：{key}")
    return len(catalog)


def parse_file_entries(value: object, label: str) -> dict[str, dict[str, object]]:
    if not isinstance(value, list) or not value:
        fail(f"清单 {label} 必须是非空数组。")
    declared: dict[str, dict[str, object]] = {}
    for entry in value:
        if not isinstance(entry, dict):
            fail(f"清单 {label} 含非对象条目。")
        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            fail(f"清单 {label} 含空路径。")
        path = normalise_member(raw_path)
        folded = path.casefold()
        if folded in declared:
            fail(f"清单 {label} 含重复路径（忽略大小写）：{raw_path!r}")
        digest = entry.get("sha256")
        size = entry.get("size")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9A-Fa-f]{64}", digest) is None:
            fail(f"清单 {label} 哈希无效：{raw_path!r}")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            fail(f"清单 {label} 大小无效：{raw_path!r}")
        declared[folded] = {"path": path, "sha256": digest.lower(), "size": size}
    return declared


def validate_declared_file(
    archive: zipfile.ZipFile,
    members: dict[str, zipfile.ZipInfo],
    member_name: str,
    entry: dict[str, object],
) -> bytes:
    data = archive.read(members[member_name])
    if len(data) != entry["size"]:
        fail(f"文件大小不符：{entry['path']}")
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        fail(f"文件哈希不符：{entry['path']}")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="只读校验《夜游漫记》汉化发布 ZIP")
    parser.add_argument("archive", help="TravellingAtNight_ZH-CN_v*.zip")
    parser.add_argument("--expected-version", help="要求 payload-manifest.json 中的补丁版本")
    args = parser.parse_args()

    with zipfile.ZipFile(args.archive, "r") as archive:
        members: dict[str, zipfile.ZipInfo] = {}
        casefolded: dict[str, str] = {}
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = normalise_member(info.filename)
            folded = name.casefold()
            if folded in casefolded:
                fail(f"ZIP 路径重复（忽略大小写）：{casefolded[folded]!r} / {name!r}")
            casefolded[folded] = name
            members[name] = info

        # Read every member once before trusting the central-directory metadata.
        # ZipFile.read() also verifies CRC, but payload validation below does not
        # otherwise open every outer script, notice, or nested source archive.
        bad_member = archive.testzip()
        if bad_member is not None:
            fail(f"ZIP 成员 CRC 校验失败：{bad_member}")

        roots = {PurePosixPath(name).parts[0] for name in members}
        if len(roots) != 1:
            fail(f"ZIP 必须只有一个顶层目录，当前为：{sorted(roots)}")
        root = next(iter(roots))
        manifest_name = f"{root}/payload-manifest.json"
        if manifest_name not in members:
            fail("发布包缺少 payload-manifest.json。")
        manifest = load_json(archive.read(members[manifest_name]), manifest_name)
        if not isinstance(manifest, dict):
            fail("payload-manifest.json 顶层必须是对象。")

        version = manifest.get("patch_version")
        if not isinstance(version, str) or PATCH_VERSION_RE.fullmatch(version) is None:
            fail("清单 patch_version 必须是 x.y.z 格式。")
        if manifest.get("schema_version") != 2:
            fail("清单 schema_version 必须为 2。")
        if args.expected_version is not None and version != args.expected_version:
            fail(f"补丁版本为 {version!r}，预期 {args.expected_version!r}。")

        expected_root = f"{PACKAGE_PREFIX}{version}"
        if root != expected_root:
            fail(f"ZIP 顶层目录为 {root!r}，应为 {expected_root!r}。")
        archive_name = Path(args.archive).name
        expected_archive_name = f"{expected_root}.zip"
        if archive_name != expected_archive_name:
            fail(f"ZIP 文件名为 {archive_name!r}，应为 {expected_archive_name!r}。")

        declared = parse_file_entries(manifest.get("files"), "files")
        declared_outer = parse_file_entries(manifest.get("outer_files"), "outer_files")
        outer_paths = {entry["path"] for entry in declared_outer.values()}
        if outer_paths != REQUIRED_OUTER:
            missing = sorted(REQUIRED_OUTER - outer_paths)
            extra = sorted(outer_paths - REQUIRED_OUTER)
            fail(f"outer_files 与规定的外层成员不一致；缺少={missing}；多出={extra}")

        payload_prefix = f"{root}/payload/"
        expected_payload = {
            f"{payload_prefix}{entry['path']}": entry for entry in declared.values()
        }
        expected_outer = {
            f"{root}/{entry['path']}": entry for entry in declared_outer.values()
        }
        expected_members = {manifest_name, *expected_payload, *expected_outer}
        if set(members) != expected_members:
            missing = sorted(expected_members - set(members))
            extra = sorted(set(members) - expected_members)
            fail(f"ZIP 成员集合与清单不一致；缺少={missing}；多出={extra}")

        for member_name, entry in expected_payload.items():
            validate_declared_file(archive, members, member_name, entry)
        outer_contents = {
            member_name: validate_declared_file(archive, members, member_name, entry)
            for member_name, entry in expected_outer.items()
        }
        for license_name, data in outer_contents.items():
            if "/licenses/" in license_name and len(data) < 100:
                fail(f"许可证或对应源代码文件异常过小：{license_name}")

        plugin_base = f"{root}/payload/BepInEx/plugins/TravellingCN"
        catalog_name = f"{plugin_base}/catalog.zh-CN.json"
        links_name = f"{plugin_base}/link_targets.zh-CN.json"
        plugin_name = f"{plugin_base}/TravellingCN.dll"
        font_name = f"{plugin_base}/font/NotoSansCJKsc-Regular.otf"
        for required in (catalog_name, links_name, plugin_name, font_name):
            if required not in members:
                fail(f"发布包缺少运行时文件：{required}")

        declared_count = manifest.get("translation_count")
        if not isinstance(declared_count, int) or declared_count <= 0:
            fail("清单 translation_count 无效。")
        catalog_count = validate_catalog(archive.read(members[catalog_name]), catalog_name, declared_count)
        link_count = validate_catalog(archive.read(members[links_name]), links_name)

        # 注：v1.x 时代这里禁止 .assets/.ress/.resource 入包（防误打包原游戏资产）；
        # v2.x 烘焙架构的 payload 本身就是改写过译文的游戏资产（level*/sharedassets*/
        # resources.assets），且每个文件都被清单哈希钉死，该检查已不适用。

        print(
            json.dumps(
                {
                    "archive": args.archive,
                    "patch_version": version,
                    "payload_files": len(declared),
                    "translation_count": catalog_count,
                    "link_target_count": link_count,
                    "status": "ok",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
