#!/usr/bin/env python3
"""Align predecessor English fields with official Simplified-Chinese fields.

Files are paired by relative path, objects by case-insensitive ``id`` and fields
by case-insensitive key.  The output supports exact full-source reuse and gives
open-set terminology review primary evidence even when a phrase was never in the
project glossary.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def object_id(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    for key, child in value.items():
        if key.casefold() == "id" and isinstance(child, str):
            return child
    return None


def align(
    en: Any,
    zh: Any,
    *,
    game: str,
    file: str,
    path: str = "$",
    nearest_id: str | None = None,
    output: list[dict],
) -> None:
    current_id = object_id(en) or nearest_id
    if isinstance(en, str) and isinstance(zh, str):
        if len(en.strip()) >= 2 and len(zh.strip()) >= 1:
            output.append(
                {
                    "source_en": en,
                    "target_zh": zh,
                    "game": game,
                    "file": file,
                    "id": current_id,
                    "field_path": path,
                }
            )
        return
    if isinstance(en, dict) and isinstance(zh, dict):
        en_keys = {str(key).casefold(): key for key in en}
        zh_keys = {str(key).casefold(): key for key in zh}
        for folded in sorted(en_keys.keys() & zh_keys.keys()):
            en_key = en_keys[folded]
            zh_key = zh_keys[folded]
            align(
                en[en_key],
                zh[zh_key],
                game=game,
                file=file,
                path=f"{path}.{en_key}",
                nearest_id=current_id,
                output=output,
            )
        return
    if isinstance(en, list) and isinstance(zh, list):
        en_by_id = {object_id(item): item for item in en if object_id(item)}
        zh_by_id = {object_id(item): item for item in zh if object_id(item)}
        shared_ids = sorted(en_by_id.keys() & zh_by_id.keys())
        if shared_ids:
            for item_id in shared_ids:
                align(
                    en_by_id[item_id],
                    zh_by_id[item_id],
                    game=game,
                    file=file,
                    path=f"{path}[id={item_id}]",
                    nearest_id=item_id,
                    output=output,
                )
        elif len(en) == len(zh):
            for index, (en_item, zh_item) in enumerate(zip(en, zh)):
                align(
                    en_item,
                    zh_item,
                    game=game,
                    file=file,
                    path=f"{path}[{index}]",
                    nearest_id=current_id,
                    output=output,
                )


def collect_game(core_root: Path, loc_root: Path, game: str) -> list[dict]:
    output: list[dict] = []
    if not core_root.exists() or not loc_root.exists():
        return output
    for zh_path in sorted(loc_root.rglob("*.json")):
        relative = zh_path.relative_to(loc_root)
        en_path = core_root / relative
        if not en_path.exists():
            continue
        en = load_json(en_path)
        zh = load_json(zh_path)
        if en is None or zh is None:
            continue
        align(en, zh, game=game, file=relative.as_posix(), output=output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--boh-root",
        type=Path,
        default=Path(r"D:\Steam\steamapps\common\Book of Hours\bh_Data\StreamingAssets\bhcontent"),
    )
    parser.add_argument(
        "--cs-root",
        type=Path,
        default=Path(r"D:\Steam\steamapps\common\Cultist Simulator\cultistsimulator_Data\StreamingAssets\content"),
    )
    parser.add_argument(
        "--translations", type=Path, default=ROOT / "translations_k97"
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        default=ROOT / "build/reviews/potential_term_candidates.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "build/reviews/predecessor_official_string_map.json",
    )
    args = parser.parse_args()

    pairs = collect_game(args.boh_root / "core", args.boh_root / "loc_zh-hans", "BOOK OF HOURS")
    pairs.extend(
        collect_game(
            args.cs_root / "core", args.cs_root / "loc_zh-hans", "Cultist Simulator"
        )
    )
    by_source: dict[str, list[dict]] = defaultdict(list)
    for pair in pairs:
        by_source[pair["source_en"]].append(pair)

    current_rows = []
    for path in sorted(args.translations.glob("chunk_*.jsonl")):
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            if raw:
                current_rows.append(json.loads(raw))
    exact_matches = []
    for row in current_rows:
        hits = by_source.get(row["source"], [])
        if not hits:
            continue
        targets = sorted({hit["target_zh"] for hit in hits})
        exact_matches.append(
            {
                "id": row["id"],
                "source": row["source"],
                "current_translation": row["translation"],
                "official_targets": targets,
                "current_matches_official": row["translation"] in targets,
                "evidence": hits,
            }
        )

    candidate_exact_matches = []
    candidate_context_matches = []
    if args.candidates.exists():
        candidate_rows = json.loads(args.candidates.read_text(encoding="utf-8-sig")).get(
            "candidates", []
        )
        for candidate in candidate_rows:
            value = candidate["candidate"]
            hits = by_source.get(value, [])
            if not hits:
                continue
            candidate_exact_matches.append(
                {
                    "candidate": value,
                    "official_targets": sorted({hit["target_zh"] for hit in hits}),
                    "evidence": hits,
                }
            )
        strong_signals = {"provisional_note", "double_bracket_link", "lore_context"}
        for candidate in candidate_rows:
            if not (strong_signals & set(candidate.get("signals", []))):
                continue
            value = candidate["candidate"]
            if len(value) < 4:
                continue
            folded = value.casefold()
            hits = [pair for pair in pairs if folded in pair["source_en"].casefold()]
            if hits:
                candidate_context_matches.append(
                    {
                        "candidate": value,
                        "match_count": len(hits),
                        "evidence": hits[:5],
                    }
                )

    result = {
        "aligned_fields": len(pairs),
        "unique_english_fields": len(by_source),
        "current_exact_matches": len(exact_matches),
        "current_exact_mismatches": sum(
            not row["current_matches_official"] for row in exact_matches
        ),
        "candidate_exact_official_matches": len(candidate_exact_matches),
        "candidate_context_official_matches": len(candidate_context_matches),
        "exact_matches": exact_matches,
        "candidate_exact_matches": candidate_exact_matches,
        "candidate_context_matches": candidate_context_matches,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if key
                not in {"exact_matches", "candidate_exact_matches", "candidate_context_matches"}
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
