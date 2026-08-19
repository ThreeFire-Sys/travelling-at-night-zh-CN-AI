#!/usr/bin/env python3
"""Verify catalog and runtime coverage for dynamically supplied UI labels."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_translations(path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for chunk in sorted(path.glob("chunk_*.jsonl")):
        for line in chunk.read_text(encoding="utf-8-sig").splitlines():
            row = json.loads(line)
            rows[row["id"]] = row
    return rows


def is_dynamic_label_context(context: dict) -> bool:
    title = str(context.get("field_title", "")).casefold()
    path = str(context.get("field_path", "")).casefold()
    return (
        title == "display name"
        or path.endswith("._label")
        or path.endswith("._displayname")
        or path.endswith(".displayname")
        or path.endswith(".label")
    )


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--worklist", type=Path, default=ROOT / "build" / "worklist_current" / "worklist.jsonl"
    )
    parser.add_argument(
        "--translations", type=Path, default=ROOT / "build" / "translations_j46_candidate"
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=ROOT / "build" / "merged_j46_reviewed" / "catalog.zh-CN.json",
    )
    parser.add_argument(
        "--plugin", type=Path, default=ROOT / "src" / "TravellingCN" / "Plugin.cs"
    )
    args = parser.parse_args()

    translations = load_translations(args.translations)
    catalog = json.loads(args.catalog.read_text(encoding="utf-8-sig"))
    plugin = args.plugin.read_text(encoding="utf-8-sig")
    errors: list[str] = []
    label_rows = 0
    actor_display_rows = 0

    for line_number, line in enumerate(
        args.worklist.read_text(encoding="utf-8-sig").splitlines(), 1
    ):
        row = json.loads(line)
        contexts = [context for context in row.get("contexts", []) if is_dynamic_label_context(context)]
        if not contexts:
            continue
        label_rows += 1
        if any(
            context.get("field_title") == "Display Name"
            and str(context.get("field_path", "")).startswith("actors.")
            for context in contexts
        ):
            actor_display_rows += 1
        translated = translations.get(row["id"])
        if translated is None or not translated.get("translation"):
            errors.append(f"line {line_number} {row['id']}: missing dynamic-label translation")
            continue
        expected = translated["translation"]
        actual = catalog.get(digest(row["source"]))
        if actual != expected:
            errors.append(
                f"line {line_number} {row['id']}: runtime catalog mismatch "
                f"({actual!r} != {expected!r})"
            )

    patch_contract = re.search(
        r"class CharacterInfoDisplayNamePatch.*?"
        r"if\s*\(DialogueBufferBuildDepth\s*==\s*0\s*&&\s*"
        r"ChineseEnabled\s*&&\s*TryLookupTranslation\(__result,\s*out var translated\)\)",
        plugin,
        re.DOTALL,
    )
    if patch_contract is None:
        errors.append("CharacterInfo display-name patch is absent or source-specific")
    if 'string.Equals(__result, "Me"' in plugin:
        errors.append("CharacterInfo display-name patch is still hard-coded to Me")

    result = {
        "dynamic_label_rows": label_rows,
        "actor_display_name_rows": actor_display_rows,
        "error_count": len(errors),
        "errors": errors[:50],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
