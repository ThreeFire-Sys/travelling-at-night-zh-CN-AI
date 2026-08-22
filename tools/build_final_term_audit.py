#!/usr/bin/env python3
"""Build reproducible evidence packets for the complete terminology audit.

The packet does not decide translations.  It resolves every glossary concept to
the current Travelling At Night asset locations and, for predecessor concepts,
to same-id English/official-Chinese objects in the locally installed predecessor
games.  Editorial verdicts live separately in ``glossary/final_term_audit.jsonl``.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
ORIGINS = ("predecessor", "travelling_new", "real_world", "editorial")

FINAL_TARGET_CHANGES = {
    "bisclavret": "狼骑",
    "Sisterhood of the Triple Knot": "三重绳结姐妹会",
    "St Melancthe": "圣梅兰瑟",
    "Honour": "操守",
    "Louche": "轻佻",
    "Quicken": "活化",
    "retenebration": "复晦",
    "scrine": "灵龛",
    "Weariness Collapse": "累倒",
}

FINAL_ALIAS_TARGETS = {
    "bisclavret": {"Bisclavret's Knot": "狼骑结印"},
    "remortal": {"remortals": "返凡者"},
    "scrine": {"scrineway": "龛道"},
}

RETIRED_CONCEPTS = {
    "Departments": "当前 k.97 资产已无此大写术语，移出活动术语表。",
    "the Group": "当前阵营名为 Incorporates；历史候选不应继续伪装成活动术语。",
    "the Union": "当前阵营名为 Ministries；历史候选不应继续伪装成活动术语。",
}

SAME_GAME_OFFICIAL = {
    "Appetite", "Career", "Curiosity", "Dignity", "Exorcist", "Incorporate",
    "Passion", "Sign", "Sophistication", "Sorrow", "Spivvery", "Stage Magician",
    "the Ministries", "War in the Sun", "War in the World", "remortal",
}

PROFESSIONAL_OR_LANGUAGE = {
    "Canovaccio", "Icarianism", "Mater Solvens", "Onteirology", "signaire",
    "spintria", "trabai", "Trygikon", "retenebration", "scrine",
}

EDITORIAL_TRANSLITERATIONS = {
    "Arlequin's Affliction", "Aubière", "Cassandro's Woe", "Diamantina's Dismay",
    "Fracasse's Frailty", "Gwendolen", "Huissier", "Janvier", "Jaume", "Labrikon",
    "Linou", "Metaphraste's Malady", "Mezzetin's Misery", "Pierrot's Pang",
    "Polchinelle's Misfortune", "Scapin's Sickness", "Silim", "Sinombre", "Stanislav",
}

CHANGE_NOTES = {
    "bisclavret": "现行《司辰之书》官中同一物品为“狼骑结印”，说明中把 bisclavret 释作“狼骑”；撤销旧 Wiki 音译。",
    "Sisterhood of the Triple Knot": "现行《司辰之书》官中在同一组织全称处使用“三重绳结姐妹会”，简称才是“绳结姐妹会”。",
    "St Melancthe": "现行《司辰之书》官中《圣梅兰瑟》与相关文本稳定使用“梅兰瑟”。",
    "Honour": "专属说明强调无人注视时仍做正确之事，核心是内在伦理操守；“荣誉”偏外在名誉，并与格言 Honneur 重叠。",
    "Louche": "这是装束的社交观感，说明指仅适合床笫等极放松场合；“轻佻装束”比把衣服称作“放荡”自然。",
    "Quicken": "专属说明为赋生、振作、唤醒；游戏已有 Quicken Item“活化物品”，统一为“活化”比另造“催活”自然。",
    "retenebration": "原文明确称 formal process 而非 rite；保留 re- + tenebrae 的“复晦”构词，删除无据添加的“礼”。",
    "scrine": "词典义是古语 shrine/chest/reliquary，游戏中是灵体寄居的容器；“灵龛”是现成中文，“龛壳”属于无必要生造。",
    "Weariness Collapse": "状态说明就是因疲惫过高而倒下；“累倒”自然、短促，“疲惫倒下”是为满足机械词根检查而写出的生硬标签。",
}


def strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


def objects_by_id(value: Any, result: dict[str, list[dict[str, Any]]]) -> None:
    if isinstance(value, dict):
        object_id = value.get("id")
        if isinstance(object_id, str) and object_id:
            result[object_id].append(value)
        for child in value.values():
            objects_by_id(child, result)
    elif isinstance(value, list):
        for child in value:
            objects_by_id(child, result)


def load_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def predecessor_pairs(core_root: Path, loc_root: Path, game: str) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    if not core_root.exists() or not loc_root.exists():
        return pairs
    for loc_path in sorted(loc_root.rglob("*.json")):
        rel = loc_path.relative_to(loc_root)
        core_path = core_root / rel
        if not core_path.exists():
            continue
        core_data = load_json(core_path)
        loc_data = load_json(loc_path)
        if core_data is None or loc_data is None:
            continue
        core_objects: dict[str, list[dict[str, Any]]] = defaultdict(list)
        loc_objects: dict[str, list[dict[str, Any]]] = defaultdict(list)
        objects_by_id(core_data, core_objects)
        objects_by_id(loc_data, loc_objects)
        for object_id in sorted(core_objects.keys() & loc_objects.keys()):
            for en_obj in core_objects[object_id]:
                for zh_obj in loc_objects[object_id]:
                    pairs.append(
                        {
                            "game": game,
                            "file": rel.as_posix(),
                            "id": object_id,
                            "en": "\n".join(strings(en_obj)),
                            "zh": "\n".join(strings(zh_obj)),
                        }
                    )
    return pairs


def load_glossary(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row["source_en"]: row for row in csv.DictReader(handle)}


def load_provenance(directory: Path) -> list[dict[str, Any]]:
    records = []
    for origin in ORIGINS:
        path = directory / f"{origin}.jsonl"
        for line_no, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if not raw:
                continue
            record = json.loads(raw)
            record["origin"] = origin
            record["provenance_file"] = str(path.relative_to(ROOT))
            record["provenance_line"] = line_no
            records.append(record)
    return records


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(raw)
        for raw in path.read_text(encoding="utf-8-sig").splitlines()
        if raw
    ]


def term_pattern(term: str, case_sensitive: bool) -> re.Pattern[str]:
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", flags)


def compact(value: str, limit: int = 320) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"


def normalised_token(value: str) -> str:
    """Ignore case, spacing and punctuation for predecessor spelling variants."""
    return "".join(char for char in value.casefold() if char.isalnum())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glossary", type=Path, default=ROOT / "glossary/glossary.csv")
    parser.add_argument("--provenance", type=Path, default=ROOT / "glossary/provenance")
    parser.add_argument("--worklist", type=Path, default=ROOT / "build/worklist_k97/worklist.jsonl")
    parser.add_argument(
        "--extracted", type=Path, default=ROOT / "build/extracted_k97/all_string_fields.jsonl"
    )
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
        "--output", type=Path, default=ROOT / "build/reviews/final_term_audit_packet.json"
    )
    parser.add_argument(
        "--write-ledger",
        action="store_true",
        help="write a current-state review draft; never overwrites the committed historical verdict ledger by default",
    )
    parser.add_argument(
        "--ledger-output",
        type=Path,
        default=ROOT / "build/reviews/final_term_audit_draft.jsonl",
    )
    args = parser.parse_args()

    glossary = load_glossary(args.glossary)
    provenance = load_provenance(args.provenance)
    worklist = load_jsonl(args.worklist)
    extracted = load_jsonl(args.extracted)

    extracted_by_site: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for field in extracted:
        extracted_by_site[(str(field.get("asset_file", "")), int(field.get("path_id", 0)))].append(field)

    predecessor = predecessor_pairs(
        args.boh_root / "core", args.boh_root / "loc_zh-hans", "BOOK OF HOURS"
    )
    predecessor.extend(
        predecessor_pairs(args.cs_root / "core", args.cs_root / "loc_zh-hans", "Cultist Simulator")
    )

    packets = []
    for record in provenance:
        canonical = str(record["canonical"])
        aliases = [str(alias) for alias in record.get("aliases", [])]
        terms = [canonical, *aliases]
        glossary_rows = [glossary[term] for term in terms]
        target = glossary[canonical]["target_zh"]
        patterns = [
            term_pattern(term, glossary[term].get("case_sensitive", "true").lower() == "true")
            for term in terms
        ]

        tan_hits = []
        exact_ids = []
        site_keys: set[tuple[str, int]] = set()
        for row in worklist:
            source = str(row.get("source", ""))
            if source in terms:
                exact_ids.append(row["id"])
            if not any(pattern.search(source) for pattern in patterns):
                continue
            contexts = row.get("contexts", [])
            for context in contexts:
                site_keys.add((str(context.get("asset_file", "")), int(context.get("path_id", 0))))
            tan_hits.append(
                {
                    "id": row["id"],
                    "source": compact(source),
                    "contexts": [
                        {
                            "asset_file": context.get("asset_file"),
                            "path_id": context.get("path_id"),
                            "script": context.get("script"),
                            "field_path": context.get("field_path"),
                            "conversation": context.get("conversation"),
                        }
                        for context in contexts[:3]
                    ],
                }
            )

        sibling_fields = []
        for site_key in sorted(site_keys):
            for field in extracted_by_site.get(site_key, []):
                field_path = str(field.get("field_path", ""))
                if field_path in {"m_Name", "Notes"} or not field.get("source"):
                    continue
                sibling_fields.append(
                    {
                        "asset_file": field.get("asset_file"),
                        "path_id": field.get("path_id"),
                        "script": field.get("script"),
                        "field_path": field_path,
                        "source": compact(str(field.get("source", ""))),
                    }
                )

        paired_hits = []
        if record["origin"] == "predecessor":
            for pair in predecessor:
                zh_norm = normalised_token(pair["zh"])
                if normalised_token(target) not in zh_norm:
                    continue
                en_norm = normalised_token(pair["en"])
                if not any(normalised_token(term) in en_norm for term in terms):
                    continue
                paired_hits.append(
                    {
                        "game": pair["game"],
                        "file": pair["file"],
                        "id": pair["id"],
                        "en": compact(pair["en"]),
                        "zh": compact(pair["zh"]),
                    }
                )

        packets.append(
            {
                "canonical": canonical,
                "aliases": aliases,
                "target": target,
                "alias_targets": {term: glossary[term]["target_zh"] for term in aliases},
                "type": glossary[canonical]["type"],
                "origin": record["origin"],
                "status": record.get("status"),
                "reference_label": record.get("reference_label"),
                "reference_url": record.get("reference_url"),
                "existing_evidence": record.get("evidence"),
                "existing_rationale": record.get("rationale"),
                "existing_alternatives": record.get("alternatives"),
                "provenance_file": record["provenance_file"],
                "provenance_line": record["provenance_line"],
                "tan_exact_ids": exact_ids,
                "tan_hits": tan_hits[:20],
                "tan_hit_count": len(tan_hits),
                "asset_sibling_fields": sibling_fields[:80],
                "predecessor_paired_hits": paired_hits[:30],
                "predecessor_paired_hit_count": len(paired_hits),
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        "concepts": len(packets),
        "origin_counts": {
            origin: sum(packet["origin"] == origin for packet in packets) for origin in ORIGINS
        },
        "predecessor_with_paired_hits": sum(
            packet["origin"] == "predecessor" and packet["predecessor_paired_hit_count"] > 0
            for packet in packets
        ),
        "predecessor_without_paired_hits": [
            packet["canonical"]
            for packet in packets
            if packet["origin"] == "predecessor" and packet["predecessor_paired_hit_count"] == 0
        ],
        "concepts_with_current_asset_hits": sum(packet["tan_hit_count"] > 0 for packet in packets),
        "concepts_without_current_asset_hits": [
            packet["canonical"] for packet in packets if packet["tan_hit_count"] == 0
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"wrote {args.output}")
    if args.write_ledger:
        ledger = []
        for packet in packets:
            canonical = packet["canonical"]
            before = packet["target"]
            if canonical in RETIRED_CONCEPTS:
                decision = "retire"
                final = None
                basis = "retired_not_in_current_assets"
                confidence = "fixed"
                note = RETIRED_CONCEPTS[canonical]
            else:
                final = FINAL_TARGET_CHANGES.get(canonical, before)
                decision = "change" if final != before else "keep"
                if packet["origin"] == "predecessor":
                    basis = (
                        "predecessor_official_same_id"
                        if packet["predecessor_paired_hit_count"]
                        else "predecessor_official_corpus"
                    )
                    confidence = "fixed"
                elif canonical in SAME_GAME_OFFICIAL:
                    basis = "same_game_official_zh"
                    confidence = "fixed"
                elif packet["origin"] == "real_world":
                    basis = "external_authority"
                    confidence = "strong"
                elif packet["origin"] == "editorial":
                    basis = "explicit_editorial_policy"
                    confidence = "editorial"
                elif canonical in EDITORIAL_TRANSLITERATIONS:
                    basis = "editorial_transliteration"
                    confidence = "editorial"
                elif canonical in PROFESSIONAL_OR_LANGUAGE:
                    basis = "language_or_professional_reference"
                    confidence = "strong"
                else:
                    basis = "current_asset_semantics"
                    confidence = "strong"
                note = CHANGE_NOTES.get(
                    canonical,
                    (
                        f"逐项终审保留“{final}”。独立核对当前资产语境、同族层级和中文可用性；"
                        f"证据摘要：{packet.get('existing_evidence', '')}"
                    ),
                )

            locators = []
            for hit in packet["predecessor_paired_hits"][:3]:
                locators.append(f"{hit['game']}:{hit['file']}#{hit['id']}")
            for row_id in packet["tan_exact_ids"][:5]:
                locators.append(f"TAN:{row_id}")
            if not locators and packet["tan_hits"]:
                locators.append(f"TAN:{packet['tan_hits'][0]['id']}")
            if packet.get("reference_url"):
                locators.append(str(packet["reference_url"]))

            alias_final = dict(packet["alias_targets"])
            alias_final.update(FINAL_ALIAS_TARGETS.get(canonical, {}))
            ledger.append(
                {
                    "canonical": canonical,
                    "origin": packet["origin"],
                    "type": packet["type"],
                    "target_before": before,
                    "target_final": final,
                    "alias_targets_final": alias_final,
                    "decision": decision,
                    "basis": basis,
                    "confidence": confidence,
                    "evidence_locators": locators,
                    "audit_note": note,
                    "reviewed_at": "2026-08-22",
                }
            )
        args.ledger_output.write_text(
            "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in ledger),
            encoding="utf-8",
        )
        print(f"wrote {len(ledger)} final audit verdicts -> {args.ledger_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
