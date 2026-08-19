#!/usr/bin/env python3
"""Prove complete glossary/provenance coverage of j.46 mechanism families."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from sync_j46_mechanism_glossary import CORE_TERMS, EXCLUSIONS, FAMILY_SPECS, base_script, load_translations


EXPECTED_INCLUDED = {
    "ExperienceQuality": 9,
    "Travelling.Opportunities.Venue": 8,
    "Travelling.PCQualities.Aspect": 49,
    "Travelling.PCQualities.Career": 4,
    "Travelling.PCQualities.ConditionQuality": 27,
    "Travelling.PCQualities.Passion": 11,
    "Travelling.PCQualities.Sign": 9,
    "Travelling.PCQualities.Skill": 16,
    "Travelling.PCQualities.SkillCheckDifficulty": 11,
    "Travelling.PCQualities.SkillCheckResultQuality": 2,
}

CANONICAL_LABELS = {
    "Fascination": "入迷",
    "Wounded Place": "受创之地",
    "Ephemeral": "易逝",
    "Louche": "放荡",
    "Raffish": "不羁",
    "Necessity": "必然",
    "Fresh": "清爽",
    "Perspiring": "微微冒汗",
    "Dripping": "汗流浃背",
    "Pursuit": "追捕",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worklist", type=Path, default=Path("build/worklist_k6/worklist.jsonl"))
    parser.add_argument("--translations", type=Path, default=Path("translations_k6"))
    parser.add_argument("--glossary", type=Path, default=Path("glossary/glossary.csv"))
    parser.add_argument("--provenance-dir", type=Path, default=Path("glossary/provenance"))
    parser.add_argument("--report", type=Path, default=Path("build/reviews/mechanism_glossary_coverage_j46.json"))
    args = parser.parse_args()

    translations = load_translations(args.translations)
    with args.glossary.open("r", encoding="utf-8-sig", newline="") as handle:
        glossary = {row["source_en"]: row for row in csv.DictReader(handle)}

    term_origins: dict[str, list[str]] = defaultdict(list)
    for origin in ("predecessor", "travelling_new", "real_world", "editorial"):
        path = args.provenance_dir / f"{origin}.jsonl"
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            if not raw.strip():
                continue
            record = json.loads(raw)
            for term in [record["canonical"], *record.get("aliases", [])]:
                term_origins[term].append(origin)

    included = []
    excluded = []
    errors = []
    for raw in args.worklist.read_text(encoding="utf-8-sig").splitlines():
        if not raw:
            continue
        row = json.loads(raw)
        for context in row.get("contexts", []):
            script = base_script(context.get("script", ""))
            if script not in FAMILY_SPECS or context.get("field_path") != "_label":
                continue
            key = (script, row["source"])
            item = {"family": script, "id": row["id"], "source": row["source"], "translation": translations[row["id"]]}
            if key in EXCLUSIONS:
                item["reason"] = EXCLUSIONS[key]
                excluded.append(item)
            else:
                included.append(item)
            break

    family_counts = Counter(item["family"] for item in included)
    for family, expected in EXPECTED_INCLUDED.items():
        if family_counts[family] != expected:
            errors.append(f"{family}: expected {expected} included labels, found {family_counts[family]}")
    if len(excluded) != len(EXCLUSIONS):
        errors.append(f"expected {len(EXCLUSIONS)} exclusions, found {len(excluded)}")

    for item in included:
        source = item["source"]
        if source not in glossary:
            errors.append(f"missing glossary label: {item['family']}::{source}")
        elif glossary[source]["target_zh"] != item["translation"]:
            errors.append(f"translation/glossary mismatch: {source}: {item['translation']} != {glossary[source]['target_zh']}")
        if len(term_origins[source]) != 1:
            errors.append(f"label provenance count {len(term_origins[source])}: {source}")
        else:
            item["origin"] = term_origins[source][0]

    included_by_source = {item["source"]: item for item in included}
    for source, expected_target in CANONICAL_LABELS.items():
        if source == "Fascination":
            actual = glossary.get(source, {}).get("target_zh")
        else:
            actual = included_by_source.get(source, {}).get("translation")
        if actual != expected_target:
            errors.append(f"reviewed canonical label mismatch: {source}: {actual!r} != {expected_target!r}")

    core_checked = []
    for canonical, (target, _category, alias) in CORE_TERMS.items():
        for term in [canonical, *([alias] if alias else [])]:
            if term not in glossary or glossary[term]["target_zh"] != target:
                errors.append(f"core term missing/mismatched: {term} -> {target}")
            if len(term_origins[term]) != 1:
                errors.append(f"core provenance count {len(term_origins[term])}: {term}")
            core_checked.append(term)
    for term, target in {"Dread": "恐惧", "Fascination": "入迷", "Influence": "影响", "Memory": "记忆", "Memories": "记忆", "Trace": "痕迹", "Traces": "痕迹", "Physician": "医师"}.items():
        if term not in glossary or glossary[term]["target_zh"] != target:
            errors.append(f"predecessor core term missing/mismatched: {term} -> {target}")
        if term_origins[term] != ["predecessor"]:
            errors.append(f"predecessor classification mismatch: {term}: {term_origins[term]}")
        core_checked.append(term)

    report = {
        "scope": "player-facing parallel mechanism taxonomies; excludes item/recipe/person/place label collections",
        "families": {family: {"included": family_counts[family], "expected": EXPECTED_INCLUDED[family]} for family in EXPECTED_INCLUDED},
        "included_labels": len(included),
        "excluded_internal_labels": excluded,
        "core_terms_checked": sorted(set(core_checked), key=str.casefold),
        "reviewed_canonical_labels": CANONICAL_LABELS,
        "origin_counts": dict(Counter(item.get("origin", "missing") for item in included)),
        "unresolved": errors,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("included_labels", "origin_counts", "unresolved")}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
