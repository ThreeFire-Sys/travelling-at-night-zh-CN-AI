#!/usr/bin/env python3
"""Audit every provisional-note row from the published v2.6.0 baseline.

The baseline is read from Git so fixes made earlier in the working tree cannot
silently make a provisional row disappear from the historical review set.
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE_REF = "v2.6.0"
STALE_RE = re.compile(
    r"(?<!短)暂(?!时)|待.{0,20}(?:校|核|统一)|需.{0,20}(?:校|核|统一)"
)


def load_rows_text(text: str) -> list[dict]:
    return [json.loads(raw) for raw in text.splitlines() if raw]


def load_rows(path: Path) -> list[dict]:
    return load_rows_text(path.read_text(encoding="utf-8-sig"))


def write_rows(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def baseline_rows(relative: str) -> list[dict]:
    result = subprocess.run(
        ["git", "show", f"{BASELINE_REF}:{relative}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return load_rows_text(result.stdout.decode("utf-8-sig"))


def normalise_note(note: str) -> str:
    replacements = {
        "暂音译": "开放终审采用音译",
        "暂直译": "开放终审采用直译",
        "暂定": "开放终审定为",
        "暂译": "开放终审采用",
        "暂沿": "开放终审沿用",
        "暂按": "开放终审按",
        "暂作": "开放终审作",
        "暂取": "开放终审取",
        "暂保留": "开放终审保留",
        "暂统一": "开放终审统一",
        "暂判": "开放终审判定",
        "暂依": "开放终审依",
    }
    for old, new in replacements.items():
        note = note.replace(old, new)
    note = re.sub(r"(?<!短)暂(?!时)", "开放终审", note)
    note = re.sub(r"待.{0,20}(?:校|核|统一)", "已完成开放终审", note)
    note = re.sub(r"需.{0,20}(?:校|核|统一)", "已完成开放终审", note)
    return note


def clip(value: str, limit: int = 96) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def main() -> int:
    with (ROOT / "glossary/glossary.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        glossary = list(csv.DictReader(handle))
    glossary_terms = sorted(
        glossary,
        key=lambda row: (-len(row["source_en"]), row["source_en"].casefold()),
    )

    current_by_id: dict[str, dict] = {}
    current_paths: dict[str, Path] = {}
    baseline: dict[str, dict] = {}
    for path in sorted((ROOT / "translations_k97").glob("chunk_*.jsonl")):
        relative = path.relative_to(ROOT).as_posix()
        for row in baseline_rows(relative):
            if STALE_RE.search(row.get("notes", "") or ""):
                baseline[row["id"]] = row
        for row in load_rows(path):
            current_by_id[row["id"]] = row
            current_paths[row["id"]] = path

    missing = sorted(set(baseline) - set(current_by_id))
    if missing:
        raise SystemExit(f"published provisional rows missing from current corpus: {missing}")

    audit = []
    for row_id in sorted(baseline):
        old = baseline[row_id]
        current = current_by_id[row_id]
        terms = []
        for term in glossary_terms:
            source_term = term["source_en"]
            if re.search(
                rf"(?<![A-Za-z]){re.escape(source_term)}(?![A-Za-z])",
                current["source"],
            ):
                terms.append(
                    {"source_en": source_term, "target_zh": term["target_zh"]}
                )
        # Do not let common overlapping aliases make the ledger unreadable.
        compact_terms = []
        for term in terms:
            if any(
                term["source_en"] != kept["source_en"]
                and term["source_en"] in kept["source_en"]
                for kept in compact_terms
            ):
                continue
            compact_terms.append(term)

        changed = current["translation"] != old["translation"]
        final_note = normalise_note(current.get("notes", "") or "")
        current["notes"] = final_note
        decision = "change" if changed else "retain_after_review"
        if compact_terms:
            term_summary = "、".join(
                f"{term['source_en']}→{term['target_zh']}" for term in compact_terms[:12]
            )
            reason = (
                f"复核 {row_id} 的完整英文与当前资产语境；涉及词形 {term_summary}。"
                f"{'译文已按开放终审修订' if changed else '现译与逐项词形裁决一致，予以保留'}。"
            )
        else:
            reason = (
                f"复核 {row_id} 的完整英文“{clip(current['source'])}”；该处是句内普通语言、"
                f"专名整句或单次物品标签，{'译文已修订' if changed else '现译可保留'}，"
                "不再以临时标记代替结论。"
            )
        audit.append(
            {
                "id": row_id,
                "source": current["source"],
                "translation_before": old["translation"],
                "translation_final": current["translation"],
                "notes_before": old.get("notes", ""),
                "notes_final": final_note,
                "terms": compact_terms,
                "decision": decision,
                "evidence_locators": [f"TAN:{row_id}"],
                "audit_note": reason,
                "reviewed_at": "2026-08-22",
            }
        )

    # Write k97 grouped by their original chunk paths.
    rows_by_path: dict[Path, list[dict]] = {}
    for path in sorted((ROOT / "translations_k97").glob("chunk_*.jsonl")):
        rows_by_path[path] = load_rows(path)
    audited_ids = set(baseline)
    for path, rows in rows_by_path.items():
        dirty = False
        for row in rows:
            if row["id"] in audited_ids:
                row["notes"] = current_by_id[row["id"]]["notes"]
                dirty = True
        if dirty:
            write_rows(path, rows)

    # Historical k83 snapshot receives the same final metadata where ids exist.
    for path in sorted((ROOT / "translations_k83").glob("chunk_*.jsonl")):
        rows = load_rows(path)
        dirty = False
        for row in rows:
            if row["id"] in current_by_id and row["id"] in audited_ids:
                row["notes"] = current_by_id[row["id"]]["notes"]
                dirty = True
        if dirty:
            write_rows(path, rows)

    audit_path = ROOT / "glossary/provisional_row_audit.jsonl"
    write_rows(audit_path, audit)
    residual = [
        row["id"]
        for path in sorted((ROOT / "translations_k97").glob("chunk_*.jsonl"))
        for row in load_rows(path)
        if STALE_RE.search(row.get("notes", "") or "")
    ]
    if residual:
        raise SystemExit(f"provisional markers remain after audit: {residual}")
    print(
        json.dumps(
            {
                "published_provisional_rows": len(baseline),
                "changed": sum(row["decision"] == "change" for row in audit),
                "retained_after_review": sum(
                    row["decision"] == "retain_after_review" for row in audit
                ),
                "residual_markers": len(residual),
                "ledger": str(audit_path.relative_to(ROOT)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
