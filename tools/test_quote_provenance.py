#!/usr/bin/env python3
"""Validate all j.46 interactive quotation objects and their verse layout."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


QUOTE_SCRIPT = "Travelling.Narrative.Quote"


def base_script(value: str) -> str:
    return value.split(",", 1)[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worklist", type=Path, default=Path("build/worklist_k6/worklist.jsonl"))
    parser.add_argument("--translations", type=Path, default=Path("translations_k6"))
    parser.add_argument("--provenance", type=Path, default=Path("glossary/quote_provenance.jsonl"))
    parser.add_argument("--report", type=Path, default=Path("build/reviews/quote_provenance_j46.json"))
    parser.add_argument("--site-overrides", type=Path, default=Path("glossary/site_overrides.csv"),
                        help="位点级译文覆盖表；Quote 题签等位点的译文可能与条目默认译文不同")
    args = parser.parse_args()

    translations = {}
    for path in sorted(args.translations.glob("*.jsonl")):
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            if raw:
                row = json.loads(raw)
                translations[row["id"]] = row["translation"]

    site_overrides: dict[tuple[str, str, int, str], str] = {}
    if args.site_overrides.exists():
        import csv as csv_mod
        with args.site_overrides.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv_mod.DictReader(handle):
                target = (row.get("translation") or "").strip()
                if target:
                    site_overrides[(row["id"], row["asset_file"], int(row["path_id"]), row["field_path"])] = target

    quotes: dict[int, dict[str, dict]] = {}
    for raw in args.worklist.read_text(encoding="utf-8-sig").splitlines():
        if not raw:
            continue
        row = json.loads(raw)
        for context in row.get("contexts", []):
            if base_script(context.get("script", "")) != QUOTE_SCRIPT or context.get("asset_file") != "sharedassets2.assets":
                continue
            path_id = int(context["path_id"])
            override_key = (row["id"], context.get("asset_file"), path_id, context["field_path"])
            quotes.setdefault(path_id, {})[context["field_path"]] = {
                "id": row["id"], "source": row["source"],
                "translation": site_overrides.get(override_key, translations[row["id"]]),
            }

    records = [json.loads(raw) for raw in args.provenance.read_text(encoding="utf-8-sig").splitlines() if raw.strip()]
    by_path = {int(record["path_id"]): record for record in records}
    errors = []
    if len(records) != 23 or len(by_path) != 23:
        errors.append(f"expected 23 unique provenance records, found {len(records)}/{len(by_path)}")
    if set(quotes) != set(by_path):
        errors.append(f"quote/provenance path mismatch: assets={sorted(quotes)}, records={sorted(by_path)}")

    layout = []
    for path_id, fields in sorted(quotes.items()):
        record = by_path.get(path_id)
        if record is None:
            continue
        for required in ("_content", "_source", "_author"):
            if required not in fields:
                errors.append(f"path {path_id}: missing {required}")
        if any(required not in fields for required in ("_content", "_source", "_author")):
            continue
        comparisons = {
            "source_en": fields["_source"]["source"],
            "source_zh": fields["_source"]["translation"],
            "author_en": fields["_author"]["source"],
            "author_zh": fields["_author"]["translation"],
        }
        for key, actual in comparisons.items():
            if record.get(key) != actual:
                errors.append(f"path {path_id}: {key} mismatch: {record.get(key)!r} != {actual!r}")
        if not (record["source_zh"].startswith("《") and record["source_zh"].endswith("》")):
            errors.append(f"path {path_id}: work title lacks Chinese title marks: {record['source_zh']}")
        if record.get("status") != "verified":
            errors.append(f"path {path_id}: status is not verified")

        source_lines = fields["_content"]["source"].splitlines()
        target_lines = fields["_content"]["translation"].splitlines()
        if path_id == 9:
            if (len(source_lines), len(target_lines)) != (7, 8) or "资产把最后两行合成一行" not in record["format_note"]:
                errors.append(f"path 9: undocumented Nevermind layout {len(source_lines)}->{len(target_lines)}")
        elif len(source_lines) != len(target_lines):
            errors.append(f"path {path_id}: line-count drift {len(source_lines)}->{len(target_lines)}")
        layout.append({"path_id": path_id, "source_lines": len(source_lines), "target_lines": len(target_lines), "kind": record["kind"]})

    report = {
        "quote_objects": len(quotes),
        "provenance_records": len(records),
        "kind_counts": dict(Counter(record["kind"] for record in records)),
        "layout_checks": layout,
        "unresolved": errors,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"quote_objects": len(quotes), "kind_counts": report["kind_counts"], "unresolved": errors}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
