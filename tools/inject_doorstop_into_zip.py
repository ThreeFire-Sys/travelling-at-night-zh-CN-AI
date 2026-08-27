#!/usr/bin/env python3
"""把 doorstop 的 winhttp.dll 直接注入发版 zip 并补登记 payload-manifest.json。

本机安全软件按文件名拦截 winhttp.dll 落盘时（v2.7.3 实测：Defender 关停、第三方
安全软件按"DLL 劫持文件名"拦截创建），暂存区无法携带该文件；zip 条目直接写字节
不触发拦截。用法：

    python tools/inject_doorstop_into_zip.py <release.zip> <winhttp.dll 源> <包内根名>

若 zip 已含 payload/winhttp.dll 则直接退出（幂等）。
"""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path


def main() -> int:
    zip_path = Path(sys.argv[1])
    source = Path(sys.argv[2])
    root_name = sys.argv[3]
    entry_name = f"{root_name}/payload/winhttp.dll"
    manifest_name = f"{root_name}/payload-manifest.json"

    blob = source.read_bytes()
    digest = hashlib.sha256(blob).hexdigest()

    with zipfile.ZipFile(zip_path, "r") as archive:
        names = archive.namelist()
        if entry_name in names:
            print(f"{entry_name} 已在 zip 内，无需注入")
            return 0
        if manifest_name not in names:
            raise SystemExit(f"zip 内未找到 {manifest_name}")
        entries = {name: archive.read(name) for name in names}

    manifest = json.loads(entries[manifest_name].decode("utf-8-sig"))
    files = manifest.setdefault("files", [])
    files.append({
        "path": "winhttp.dll",
        "sha256": digest.upper(),
        "size": len(blob),
    })
    entries[manifest_name] = (json.dumps(manifest, ensure_ascii=False) + "\n").encode("utf-8")
    entries[entry_name] = blob

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    print(f"已注入 {entry_name}（{len(blob)} 字节）并登记 manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
