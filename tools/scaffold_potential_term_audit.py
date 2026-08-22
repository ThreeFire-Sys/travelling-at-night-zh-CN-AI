#!/usr/bin/env python3
"""Create a review scaffold from open-set terminology candidates.

The scaffold only pre-closes two mechanically provable classes: concepts
already covered by the final glossary ledger, and strict fragments wholly
contained in a stronger candidate at the same source rows.  Everything else is
left pending for an explicit editorial disposition.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STRONG = {
    "provisional_note",
    "double_bracket_link",
    "label_source",
    "lore_context",
}


def norm(value: str) -> str:
    return " ".join(value.replace("’", "'").split()).casefold()


def contained(candidate: str, parent: str) -> bool:
    return re.search(
        rf"(?<![A-Za-zÀ-ÖØ-öø-ÿ]){re.escape(candidate)}(?![A-Za-zÀ-ÖØ-öø-ÿ])",
        parent,
        re.IGNORECASE,
    ) is not None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--candidates",
        type=Path,
        default=ROOT / "build/reviews/potential_term_candidates.json",
    )
    parser.add_argument(
        "--official-map",
        type=Path,
        default=ROOT / "build/reviews/predecessor_official_string_map.json",
    )
    parser.add_argument(
        "--quote-provenance",
        type=Path,
        default=ROOT / "glossary/quote_provenance.jsonl",
    )
    parser.add_argument(
        "--runtime-supplement",
        type=Path,
        default=ROOT / "glossary/runtime_supplement.csv",
    )
    parser.add_argument(
        "--glossary", type=Path, default=ROOT / "glossary/glossary.csv"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "build/reviews/potential_term_audit_scaffold.jsonl",
    )
    args = parser.parse_args()

    data = json.loads(args.candidates.read_text(encoding="utf-8-sig"))
    candidates = data["candidates"]
    official_data = json.loads(args.official_map.read_text(encoding="utf-8-sig"))
    official = {
        norm(row["candidate"]): row for row in official_data.get("candidate_exact_matches", [])
    }
    with args.glossary.open("r", encoding="utf-8-sig", newline="") as handle:
        live_glossary = {norm(row["source_en"]): row for row in csv.DictReader(handle)}
    for candidate in candidates:
        if norm(candidate["candidate"]) in live_glossary:
            candidate["existing_glossary"] = live_glossary[norm(candidate["candidate"])]
    quote_terms = {}
    for raw in args.quote_provenance.read_text(encoding="utf-8-sig").splitlines():
        if not raw:
            continue
        record = json.loads(raw)
        quote_terms[norm(record["source_en"])] = {
            "target": record["source_zh"],
            "url": record["reference_url"],
            "kind": "quote title",
        }
        quote_terms[norm(record["author_en"])] = {
            "target": record["author_zh"],
            "url": record["reference_url"],
            "kind": "quote author",
        }
    with args.runtime_supplement.open("r", encoding="utf-8-sig", newline="") as handle:
        runtime_terms = {
            norm(row["source_en"]): row for row in csv.DictReader(handle)
        }

    # A fragment can only close against a stronger candidate that covers every
    # one of its rows.  Prefer the shortest such parent for a useful audit note.
    parents: dict[str, str] = {}
    strong_rows = [
        row for row in candidates if STRONG & set(row["signals"])
    ]
    for row in candidates:
        if row["existing_glossary"] or row["existing_link_target"]:
            continue
        value = row["candidate"]
        row_ids = set(row["row_ids"])
        possible = [
            parent
            for parent in strong_rows
            if len(parent["candidate"]) > len(value)
            and row_ids
            and row_ids <= set(parent["row_ids"])
            and contained(value, parent["candidate"])
        ]
        if possible:
            parents[norm(value)] = min(possible, key=lambda item: len(item["candidate"]))[
                "candidate"
            ]

    output = []
    for row in candidates:
        value = row["candidate"]
        normalized = norm(value)
        exact_targets = sorted(
            {
                hit["translation"]
                for hit in row["hits"]
                if norm(hit["source"]) == normalized
            }
        )
        base = {
            "candidate": value,
            "forms": row["forms"],
            "signals": row["signals"],
            "row_ids": row["row_ids"],
            "current_exact_targets": exact_targets,
            "official_exact_targets": official.get(normalized, {}).get(
                "official_targets", []
            ),
            "evidence_locators": [f"TAN:{row_id}" for row_id in row["row_ids"][:8]],
            "reviewed_at": None,
        }
        if row["existing_glossary"]:
            base.update(
                {
                    "decision": "covered_existing",
                    "canonical": row["existing_glossary"]["source_en"],
                    "target_final": row["existing_glossary"]["target_zh"],
                    "basis": "existing_final_term_ledger",
                    "audit_note": (
                        f"“{value}”已由当前活动术语表及最终术语账本覆盖；"
                        "本轮开放扫描确认其仍有当前资产位点。"
                    ),
                    "reviewed_at": "2026-08-22",
                }
            )
        elif normalized in quote_terms:
            quote = quote_terms[normalized]
            base.update(
                {
                    "decision": "covered_quote_provenance",
                    "canonical": value,
                    "target_final": quote["target"],
                    "basis": "quote_provenance",
                    "audit_note": (
                        f"“{value}”是已逐项核过出处的{quote['kind']}，"
                        f"本轮沿用“{quote['target']}”；其作品级证据见 quote_provenance。"
                    ),
                    "evidence_locators": base["evidence_locators"] + [quote["url"]],
                    "reviewed_at": "2026-08-22",
                }
            )
        elif normalized in runtime_terms:
            runtime = runtime_terms[normalized]
            base.update(
                {
                    "decision": "covered_runtime_registry",
                    "canonical": value,
                    "target_final": runtime["target_zh"],
                    "basis": "runtime_supplement_registry",
                    "audit_note": (
                        f"“{value}”是资产外运行时字段，已有独立映射“{runtime['target_zh']}”；"
                        f"登记说明：{runtime.get('notes', '')}"
                    ),
                    "reviewed_at": "2026-08-22",
                }
            )
        elif normalized in parents and "provisional_note" not in row["signals"]:
            parent = parents[normalized]
            base.update(
                {
                    "decision": "exclude_fragment",
                    "canonical": None,
                    "target_final": None,
                    "basis": "strict_fragment_of_stronger_candidate",
                    "audit_note": (
                        f"“{value}”只作为同位点更完整候选“{parent}”的片段出现；"
                        "不把截断片段另立为术语，完整候选另行裁决。"
                    ),
                    "reviewed_at": "2026-08-22",
                }
            )
        elif (
            len(row["row_ids"]) == 1
            and len(exact_targets) == 1
            and not ({"provisional_note", "provisional_context", "double_bracket_link", "lore_context"} & set(row["signals"]))
            and not base["official_exact_targets"]
        ):
            target = exact_targets[0]
            base.update(
                {
                    "decision": "retain_one_off_label",
                    "canonical": value,
                    "target_final": target,
                    "basis": "current_asset_exact_label",
                    "audit_note": (
                        f"“{value}”只在 {row['row_ids'][0]} 作为完整玩家可见标签出现，"
                        f"当前整字段译为“{target}”。它不是跨位点替换词，故记录终审形态而不加入全局术语替换表。"
                    ),
                    "reviewed_at": "2026-08-22",
                }
            )
        elif (
            len(row["row_ids"]) >= 2
            and len(exact_targets) == 1
            and not ({"provisional_note", "provisional_context", "double_bracket_link", "lore_context"} & set(row["signals"]))
            and not base["official_exact_targets"]
        ):
            target = exact_targets[0]
            base.update(
                {
                    "decision": "retain_recurrent_label",
                    "canonical": value,
                    "target_final": target,
                    "basis": "current_asset_recurrent_exact_label",
                    "audit_note": (
                        f"“{value}”在 {len(row['row_ids'])} 条当前资产记录中均作为完整标签出现，"
                        f"可见译名稳定为“{target}”；记录固定整字段形态，但不授权脱离上下文的子串替换。"
                    ),
                    "reviewed_at": "2026-08-22",
                }
            )
        elif (
            not exact_targets
            and not ({"provisional_note", "provisional_context", "double_bracket_link", "lore_context"} & set(row["signals"]))
            and not base["official_exact_targets"]
        ):
            locators = "、".join(row["row_ids"][:4])
            base.update(
                {
                    "decision": "exclude_context_only",
                    "canonical": None,
                    "target_final": None,
                    "basis": "capitalized_substring_without_independent_term_site",
                    "audit_note": (
                        f"“{value}”只在 {locators} 等位点作为句内大写片段出现；"
                        "全量扫描未找到它独立充当标签、链接目标、引文设定词或暂译对象的位点。"
                        "因此保留所在整句的语境译法，不建立脱离句法的固定术语。"
                    ),
                    "reviewed_at": "2026-08-22",
                }
            )
        else:
            base.update(
                {
                    "decision": "pending",
                    "canonical": None,
                    "target_final": None,
                    "basis": None,
                    "audit_note": None,
                }
            )
        output.append(base)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in output),
        encoding="utf-8",
    )
    counts = Counter(row["decision"] for row in output)
    print(json.dumps({"candidates": len(output), "decisions": counts}, ensure_ascii=False, indent=2))
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
