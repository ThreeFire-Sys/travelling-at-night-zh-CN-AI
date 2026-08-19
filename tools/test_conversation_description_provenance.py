#!/usr/bin/env python3
"""Audit every DialogueDatabase conversation-level Description in j.46."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse


DESCRIPTION_PATH = re.compile(r"^conversations\.\[\d+\]\.fields\.\[\d+\]\.value$")
EXPECTED_TRANSLATIONS = {
    "TAN-CC2C59856798": "“海报是诗，报纸是散文”",
    "TAN-A7D29320BFDB": "鱼儿游来敲一敲 / 再侧耳倾听",
    "TAN-BB2392A30593": "秋天已死 你要记得",
    "TAN-2DDDA1E9FCCD": "他们的乐声震撼天地，恐惧袭遍一切生灵",
    "TAN-46E41B3A805B": "醒来吧，沉睡者，莫再迟延",
    "TAN-FBE1AA5D52C5": "我能说些什么\n能胜过沉默？",
}


def base_script(value: str) -> str:
    return value.split(",", 1)[0]


def fallback_kind(conversation: str, source: str) -> str:
    if conversation.startswith("internal/") or source in {"I DO TEST!", "TELL US YOU SAW THIS, AND WHERE", "TELL US YOU SAW THIS AND WHERE"}:
        return "内部机制或测试元数据"
    if "painting" in conversation.casefold() or "(oil," in source or "(print," in source:
        return "藏品题签"
    if conversation.startswith("_read/package"):
        return "物品或装束标签"
    if conversation.startswith("_dest/"):
        return "地点题铭（本轮未判为诗歌）"
    if conversation.startswith("_read/"):
        return "阅读场景题辞（未核得外部诗源）"
    return "游戏原创、设定内题辞或未核得外部出处"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worklist", type=Path, default=Path("build/worklist_k6/worklist.jsonl"))
    parser.add_argument("--translations", type=Path, default=Path("translations_k6"))
    parser.add_argument("--provenance", type=Path, default=Path("glossary/conversation_description_provenance.jsonl"))
    parser.add_argument("--report", type=Path, default=Path("build/reviews/conversation_description_provenance_j46.json"))
    args = parser.parse_args()

    translations = {}
    for path in sorted(args.translations.glob("*.jsonl")):
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            if raw:
                row = json.loads(raw)
                translations[row["id"]] = row

    descriptions = {}
    errors = []
    for raw in args.worklist.read_text(encoding="utf-8-sig").splitlines():
        if not raw:
            continue
        row = json.loads(raw)
        for context in row.get("contexts", []):
            if (
                base_script(context.get("script", "")) == "PixelCrushers.DialogueSystem.Wrappers.DialogueDatabase"
                and context.get("field_title") == "Description"
                and DESCRIPTION_PATH.fullmatch(context.get("field_path", ""))
            ):
                key = (row["id"], context.get("conversation", ""))
                descriptions[key] = {
                    "id": row["id"],
                    "source": row["source"],
                    "translation": translations.get(row["id"], {}).get("translation"),
                    "conversation": context.get("conversation", ""),
                }

    if len(descriptions) != 134:
        errors.append(f"expected 134 conversation descriptions, found {len(descriptions)}")
    if any(row["translation"] is None for row in descriptions.values()):
        errors.append("one or more conversation descriptions lacks a candidate translation")

    records = []
    by_id = {}
    for line_no, raw in enumerate(args.provenance.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not raw.strip():
            continue
        record = json.loads(raw)
        records.append(record)
        row_id = record.get("id")
        if row_id in by_id:
            errors.append(f"duplicate provenance id {row_id} at line {line_no}")
        by_id[row_id] = record
        for field in ("kind", "work", "author", "reference_label", "reference_url", "evidence", "status"):
            if not str(record.get(field, "")).strip():
                errors.append(f"{row_id}: missing {field}")
        parsed = urlparse(str(record.get("reference_url", "")))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append(f"{row_id}: invalid reference URL")
        if record.get("status") not in {"verified", "attribution_only", "no_external_source_found"}:
            errors.append(f"{row_id}: invalid status {record.get('status')!r}")

    asset_ids = {row["id"] for row in descriptions.values()}
    unknown = sorted(set(by_id) - asset_ids)
    if unknown:
        errors.append("provenance ids absent from description assets: " + ", ".join(unknown))
    if by_id.get("TAN-02B01C5D399D", {}).get("status") != "no_external_source_found":
        errors.append("No refunds for the horizon must remain explicitly unverified as an external quotation")
    if by_id.get("TAN-BB2392A30593", {}).get("work") != "《告别》（L’Adieu）":
        errors.append("Autumn is dead provenance must identify L’Adieu")

    for row_id, expected in EXPECTED_TRANSLATIONS.items():
        actual = translations.get(row_id, {}).get("translation")
        if actual != expected:
            errors.append(f"{row_id}: expected reviewed translation {expected!r}, found {actual!r}")

    reviewed = []
    counts = Counter()
    for row in sorted(descriptions.values(), key=lambda item: (item["conversation"], item["id"])):
        record = by_id.get(row["id"])
        kind = record["kind"] if record else fallback_kind(row["conversation"], row["source"])
        status = record["status"] if record else "reviewed_no_external_source_identified"
        counts[kind] += 1
        reviewed.append({**row, "kind": kind, "status": status})

    report = {
        "conversation_descriptions": len(descriptions),
        "documented_external_or_special_records": len(records),
        "kind_counts": dict(counts),
        "reviewed": reviewed,
        "unresolved": errors,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("conversation_descriptions", "documented_external_or_special_records", "kind_counts", "unresolved")}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
