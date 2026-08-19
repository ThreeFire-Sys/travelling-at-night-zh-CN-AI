#!/usr/bin/env python3
"""Verify a baked asset directory: every catalog site must read back its
reviewed translation, and linkable labels must keep their English original in
alternativeLabels.  Exits non-zero on any violation."""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
from bake_translations import (  # noqa: E402
    MONOBEHAVIOUR_HEADER_SIZE,
    navigate,
    read_raw_with_offset,
    serialized_files,
    find_data_dir,
)

UNITY_VERSION = "6000.4.0f1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("game_root", type=Path)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("baked_dir", type=Path)
    parser.add_argument("--site-overrides", type=Path, default=None,
                        help="site_overrides.csv（与烘焙同款位点级覆盖；缺省读工作区 glossary/）")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    game_root = args.game_root.resolve()
    baked_dir = args.baked_dir.resolve()
    data_dir = find_data_dir(game_root)

    sites: dict[tuple[str, int, str], str] = {}
    object_scripts: dict[tuple[str, int], str] = {}
    label_sites: list[tuple[str, int, str, str]] = []
    with args.catalog.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            entry = json.loads(line)
            translation = (entry.get("translation") or "").strip()
            if not translation:
                continue
            for context in entry.get("contexts") or []:
                site = (context["asset_file"], context["path_id"], context["field_path"])
                sites[site] = translation
                object_scripts.setdefault(
                    (context["asset_file"], context["path_id"]), context.get("script", ""))
                if context["field_path"].endswith(("label", "Label")):
                    label_sites.append((*site, context.get("source", entry["source"])))

    # 与烘焙一致的位点级覆盖：这些位点的期望值是覆盖译文而非条目默认译文。
    workspace = args.catalog.resolve().parents[2]
    site_overrides_path = args.site_overrides or workspace / "glossary" / "site_overrides.csv"
    if site_overrides_path.exists():
        import csv
        with site_overrides_path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                target = (row.get("translation") or "").strip()
                if target:
                    sites[(row["asset_file"], int(row["path_id"]), row["field_path"])] = target

    load_paths = []
    for path in serialized_files(data_dir):
        baked = baked_dir / path.name
        load_paths.append(str(baked) if baked.exists() else str(path))
    env = UnityPy.load(*load_paths)
    generator = TypeTreeGenerator(UNITY_VERSION)
    generator.load_local_game(str(game_root))
    env.typetree_generator = generator

    file_by_name: dict[str, object] = {}
    for key, serialized in env.files.items():
        file_by_name[Path(str(key)).name] = serialized

    by_object: dict[tuple[str, int], list[tuple[str, str]]] = collections.defaultdict(list)
    for (asset_file, path_id, field_path), translation in sites.items():
        by_object[(asset_file, path_id)].append((field_path, translation))

    failures: list[str] = []
    checked = 0
    alt_checked = 0

    # 与烘焙一致的路由：TypeTreeGenerator 对这四类布局建模有误且不抛异常，
    # 按目录登记的脚本类名直接走原始布局读取。
    RAW_CLASSES = ("Footnote", "Aspect", "RelationshipQuality", "MusicTrackLibrary")

    def read_object(obj, asset_file, path_id):
        script_class = object_scripts.get((asset_file, path_id), "")
        short_class = script_class.split(",", 1)[0].rsplit(".", 1)[-1]
        if short_class in RAW_CLASSES:
            tree, _, _ = read_raw_with_offset(obj)
            return tree
        try:
            return obj.read_typetree()
        except Exception:
            tree, _, _ = read_raw_with_offset(obj)
            return tree

    for (asset_file, path_id), fields in sorted(by_object.items()):
        serialized = file_by_name.get(asset_file)
        obj = serialized.objects.get(path_id) if serialized is not None else None
        if obj is None:
            failures.append(f"{asset_file}:{path_id} object missing")
            continue
        try:
            tree = read_object(obj, asset_file, path_id)
        except Exception as exc:
            failures.append(f"{asset_file}:{path_id} unreadable: {exc}")
            continue
        for field_path, translation in fields:
            try:
                current = navigate(tree, field_path)
            except (KeyError, IndexError, ValueError) as exc:
                failures.append(f"{asset_file}:{path_id}:{field_path} navigate: {exc}")
                continue
            checked += 1
            if current != translation:
                failures.append(
                    f"{asset_file}:{path_id}:{field_path} reads "
                    f"{str(current)[:50]!r}, expected {translation[:50]!r}")
    # alternativeLabels 校验：label 位点的英文原值必须出现在同对象的列表里。
    for asset_file, path_id, field_path, english in label_sites:
        serialized = file_by_name.get(asset_file)
        obj = serialized.objects.get(path_id) if serialized is not None else None
        if obj is None:
            continue
        try:
            tree = read_object(obj, asset_file, path_id)
        except Exception:
            continue
        alternatives = tree.get("alternativeLabels") or tree.get("_alternativeLabels")
        # Footnote/Aspect/RelationshipQuality/MusicTrackLibrary：typetree 模型把
        # 别名列读成字符串导致烘焙推送静默失效，而强行原始布局写回会让 Unity
        # 判定文件损坏（v2.2.15 崩溃事故）——这四类的英文别名改由插件运行时
        # 注入（InjectAlternativeLabels），此处跳过校验。
        script_class = object_scripts.get((asset_file, path_id), "")
        if script_class.split(",", 1)[0].rsplit(".", 1)[-1] in RAW_CLASSES:
            continue
        if isinstance(alternatives, list):
            current = None
            try:
                current = navigate(tree, field_path)
            except (KeyError, IndexError, ValueError):
                pass
            if isinstance(current, str) and current != english and english not in alternatives:
                failures.append(
                    f"{asset_file}:{path_id}:{field_path} label baked but English "
                    f"{english[:40]!r} missing from alternativeLabels")

    print(json.dumps({
        "sites": len(sites),
        "checked": checked,
        "label_sites": len(label_sites),
        "failures": len(failures),
    }, ensure_ascii=False, indent=2))
    for failure in failures[:20]:
        print("  " + failure)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
