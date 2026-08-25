#!/usr/bin/env python3
"""Require in-game News to preserve every current English version section."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import UnityPy


ROOT = Path(__file__).resolve().parents[1]
HEADING_RE = re.compile(r"(?m)^##\s+(\d{4}\.\d+\.[a-z]\.\d+).*?$")
BULLET_RE = re.compile(r"^\s*[-*=]\s+\S", re.M)
VERSION_RE = re.compile(r"^\d{4}\.\d+\.[a-z]\.\d+$", re.I)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--catalog",
        type=Path,
        default=ROOT / "build/merged_k97/review_catalog.jsonl",
    )
    parser.add_argument("--baked-asset", type=Path, default=None)
    return parser.parse_args()


def section_list(text: str) -> list[tuple[str, str]]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    matches = list(HEADING_RE.finditer(normalized))
    return [
        (
            match.group(1),
            normalized[
                match.start() : matches[index + 1].start()
                if index + 1 < len(matches)
                else len(normalized)
            ].strip(),
        )
        for index, match in enumerate(matches)
    ]


def game_parsed_versions(text: str) -> tuple[list[str], list[str]]:
    """Mirror PatchNotesParser.IsHeader/SplitHeader from the game."""
    versions: list[str] = []
    errors: list[str] = []
    for line_number, line in enumerate(
        text.replace("\r\n", "\n").replace("\r", "\n").split("\n"), start=1
    ):
        if not line.startswith("## "):
            continue
        header = line[len("## ") :].strip()
        em_index = header.find(" — ")
        hyphen_index = header.find(" - ")
        indexes = [index for index in (em_index, hyphen_index) if index >= 0]
        split_index = min(indexes) if indexes else -1
        version = header[:split_index].strip() if split_index >= 0 else header.strip()
        if VERSION_RE.fullmatch(version):
            versions.append(version)
        else:
            errors.append(f"line {line_number}: invalid game header {header!r}")
    return versions, errors


def main() -> int:
    args = parse_args()
    rows = [
        json.loads(line)
        for line in args.catalog.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    hits = [
        row
        for row in rows
        if any(context.get("game_object") == "patch-notes" for context in row.get("contexts", []))
    ]
    errors: list[str] = []
    invalid_fixture_versions, invalid_fixture_errors = game_parsed_versions(
        "## 2026.8.k.98 ——“不合法的旧中文标题”"
    )
    if invalid_fixture_versions or not invalid_fixture_errors:
        errors.append("parser mirror no longer rejects the old no-space double-em-dash heading")
    valid_fixture_versions, valid_fixture_errors = game_parsed_versions(
        "## 2026.8.k.98 — “合法的中文标题”"
    )
    if valid_fixture_versions != ["2026.8.k.98"] or valid_fixture_errors:
        errors.append("parser mirror rejects the supported spaced single-em-dash heading")
    if len(hits) != 1:
        errors.append(f"expected one patch-notes row, found {len(hits)}")
    else:
        row = hits[0]
        source = section_list(row.get("source", ""))
        target = section_list(row.get("translation", ""))
        source_versions = [version for version, _ in source]
        target_versions = [version for version, _ in target]
        if target_versions != source_versions:
            errors.append(
                f"News version drift: source={source_versions!r} target={target_versions!r}"
            )
        if len(target_versions) != len(set(target_versions)):
            errors.append("duplicate translated News version headings")
        source_game_versions, source_game_errors = game_parsed_versions(row.get("source", ""))
        target_game_versions, target_game_errors = game_parsed_versions(row.get("translation", ""))
        errors.extend(f"source {error}" for error in source_game_errors)
        errors.extend(f"translation {error}" for error in target_game_errors)
        if target_game_versions != source_game_versions:
            errors.append(
                "game parser version drift: "
                f"source={source_game_versions!r} target={target_game_versions!r}"
            )
        for (source_version, source_body), (target_version, target_body) in zip(source, target):
            if source_version != target_version:
                continue
            source_bullets = len(BULLET_RE.findall(source_body))
            target_bullets = len(BULLET_RE.findall(target_body))
            if source_bullets != target_bullets:
                errors.append(
                    f"{source_version}: source bullets={source_bullets}, target={target_bullets}"
                )
            if not re.search(r"[\u3400-\u9fff]", target_body):
                errors.append(f"{source_version}: translated section has no CJK text")
        # 最新章节必须以解析器支持的「## 版本 — “中文标题”」开头（版本号随源文动态取，
        # 不再写死 k.98——l.8 迁移时旧断言把最新章节钉死在历史上）。
        if source_versions and not row.get("translation", "").startswith(
            f"## {source_versions[0]} — “"
        ):
            errors.append(f"latest {source_versions[0]} Chinese News heading is missing")
        if args.baked_asset is not None:
            context = next(
                context
                for context in row["contexts"]
                if context.get("game_object") == "patch-notes"
            )
            if not args.baked_asset.is_file():
                errors.append(f"baked News asset missing: {args.baked_asset}")
            else:
                environment = UnityPy.load(str(args.baked_asset))
                objects = [
                    obj for obj in environment.objects if obj.path_id == context["path_id"]
                ]
                if len(objects) != 1:
                    errors.append(
                        f"baked patch-notes object count at path {context['path_id']}: {len(objects)}"
                    )
                else:
                    actual = objects[0].read_typetree().get(context["field_path"])
                    if actual != row["translation"]:
                        errors.append("baked patch-notes TextAsset does not equal reviewed translation")
                    elif game_parsed_versions(actual)[0] != source_game_versions:
                        errors.append("game parser rejects one or more baked News headings")

    print(
        json.dumps(
            {
                "catalog": str(args.catalog),
                "news_rows": len(hits),
                "sections": len(section_list(hits[0]["source"])) if len(hits) == 1 else 0,
                "baked_checked": args.baked_asset is not None,
                "errors": errors,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
