#!/usr/bin/env python3
"""Ensure exact player-facing labels agree with the curated glossary."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# The exact source is a motto reused as a package title at this one site; the
# title legitimately adds Chinese book-title marks while the base term does not.
SITE_VARIANTS = {
    "TAN-8673046C8126": "《荣誉与人道》",
}

LEGACY_BY_SOURCE = {
    "Appetite": ("欲求",),
    "Bisclavret": ("比斯克拉夫雷",),
    "Challenging": ("富有挑战",),
    "Chilly": ("寒冷",),
    "Honour": ("荣誉",),
    "Kerisham": ("凯里沙姆",),
    "Leathy": ("革质",),
    "Light": ("轻薄",),
    "Louche": ("放荡",),
    "Mandate": ("敕令",),
    "Numa": ("努马",),
    "Obscure": ("晦涩",),
    "Polchinelle's Misfortune": ("波尔希内尔之厄",),
    "Practicality": ("务实",),
    "Quicken": ("催活",),
    "Roost": ("栖巢",),
    "Roulotte": ("罗洛特",),
    "Salve": ("药膏",),
    "Season": ("季节",),
    "scrine": ("龛壳",),
    "scrineway": ("龛路",),
    "Top Up": ("补满",),
    "Unveil": ("揭幕",),
    "Warm": ("温暖",),
    "Weariness Collapse": ("疲惫崩溃", "疲惫倒下"),
    "Zachary": ("扎卡里",),
    "retenebration": ("复晦礼",),
}

LEGACY_EXEMPTIONS = {
    # This patch-note TextAsset also uses ordinary “揭幕” for revealing a
    # painting, independently of its later reference to the Unveil aspect.
    ("TAN-028DAD9F67D6", "Unveil", "揭幕"),
    ("TAN-560B3D164FC3", "Unveil", "揭幕"),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--translations", type=Path, default=ROOT / "translations_k97")
    parser.add_argument("--glossary", type=Path, default=ROOT / "glossary/glossary.csv")
    args = parser.parse_args()

    with args.glossary.open("r", encoding="utf-8-sig", newline="") as handle:
        glossary = {row["source_en"]: row for row in csv.DictReader(handle)}

    rows = []
    for path in sorted(args.translations.glob("chunk_*.jsonl")):
        rows.extend(
            json.loads(line)
            for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line
        )

    errors = []
    checked = 0
    for row in rows:
        term = glossary.get(row["source"])
        if term is None:
            continue
        checked += 1
        expected = SITE_VARIANTS.get(row["id"], term["target_zh"])
        if row["translation"] != expected:
            errors.append(
                f"{row['id']} {row['source']!r}: expected {expected!r}, "
                f"got {row['translation']!r}"
            )
        stale = re.search(r"暂译|待.{0,8}(?:统校|统一)|需与.{0,8}统一", row.get("notes", ""))
        if stale:
            errors.append(
                f"{row['id']} {row['source']!r}: exact verified label retains stale note "
                f"{stale.group(0)!r}"
            )

    for row in rows:
        for source_term, legacy_targets in LEGACY_BY_SOURCE.items():
            pattern = rf"(?<![A-Za-z]){re.escape(source_term)}(?![A-Za-z])"
            if re.search(pattern, row["source"]) is None:
                continue
            for legacy in legacy_targets:
                if (row["id"], source_term, legacy) in LEGACY_EXEMPTIONS:
                    continue
                if legacy in row["translation"]:
                    errors.append(
                        f"{row['id']} {source_term!r}: translation retains legacy form {legacy!r}"
                    )

    print(
        json.dumps(
            {"rows": len(rows), "exact_glossary_labels_checked": checked, "errors": errors},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
