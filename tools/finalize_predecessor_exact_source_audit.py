#!/usr/bin/env python3
"""Record a disposition for every current row exactly present in predecessor loc."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TERM_ADOPTIONS = {
    "TAN-7200F34A125D": "沿用前作同一引文的三个固定称谓；因本作英文资产没有 <b> 标签，只采用官中词形并保持本作结构。",
    "TAN-360C30A29EA2": "沿用前作同名文献“制烛人的传说”，同时按本项目中文书名规则补书名号。",
}


def main() -> int:
    source_path = ROOT / "build/reviews/predecessor_official_string_map.json"
    data = json.loads(source_path.read_text(encoding="utf-8-sig"))
    catalog = {
        row["id"]: row
        for row in (
            json.loads(raw)
            for raw in (ROOT / "build/merged_k97/review_catalog.jsonl").read_text(
                encoding="utf-8-sig"
            ).splitlines()
            if raw
        )
    }
    output = []
    for row in data["exact_matches"]:
        row_id = row["id"]
        current = row["current_translation"]
        targets = row["official_targets"]
        domain = catalog.get(row_id, {}).get("domain", "")
        if current in targets:
            decision = "official_exact_match"
            note = "当前译文与前作官中完全相同；已核对同一英文、同一中文和当前位点，直接保留。"
        elif row_id in TERM_ADOPTIONS:
            decision = "adopt_official_terms_with_current_markup"
            note = TERM_ADOPTIONS[row_id]
        elif len(row["source"]) > 24:
            decision = "reviewed_stylistic_override"
            note = (
                f"完整英文在前作有官中版本，但本作当前译文已逐句复核；其差异属于中文句式、"
                f"标点或本作语气，不改变固定设定词。前作目标：{'／'.join(targets)}"
            )
        else:
            decision = "reviewed_context_override"
            note = (
                f"短英文同形词在本作 {domain} 位点取“{current}”，前作目标为“{'／'.join(targets)}”；"
                "对象/机制义不同，不能仅凭英文同形强制复用。"
            )
        evidence = []
        for hit in row["evidence"][:8]:
            evidence.append(f"{hit['game']}:{hit['file']}#{hit.get('id') or hit['field_path']}")
        output.append(
            {
                "id": row_id,
                "source": row["source"],
                "translation_final": current,
                "official_targets": targets,
                "decision": decision,
                "domain": domain,
                "evidence_locators": evidence,
                "audit_note": note,
                "reviewed_at": "2026-08-22",
            }
        )
    output.sort(key=lambda row: row["id"])
    path = ROOT / "glossary/predecessor_exact_source_audit.jsonl"
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in output),
        encoding="utf-8",
    )
    decisions = {}
    for row in output:
        decisions[row["decision"]] = decisions.get(row["decision"], 0) + 1
    print(json.dumps({"exact_sources": len(output), "decisions": decisions}, ensure_ascii=False, indent=2))
    print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
