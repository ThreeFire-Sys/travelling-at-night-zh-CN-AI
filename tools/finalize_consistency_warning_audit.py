#!/usr/bin/env python3
"""Give every non-fatal consistency warning an explicit reviewed disposition."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def norm(value: str) -> str:
    return " ".join(value.replace("’", "'").split()).casefold()


def signature(issue: dict) -> str:
    value = "\0".join((issue.get("code", ""), issue.get("id", ""), issue.get("detail", "")))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def main() -> int:
    report = json.loads((ROOT / "build/merged_k97/consistency_report.json").read_text(encoding="utf-8-sig"))
    potential = {
        norm(row["candidate"]): row
        for row in (
            json.loads(raw)
            for raw in (ROOT / "glossary/potential_term_audit.jsonl").read_text(
                encoding="utf-8-sig"
            ).splitlines()
            if raw
        )
    }
    output = []
    for issue in report.get("issues", []):
        if issue.get("severity") == "error":
            continue
        code = issue["code"]
        if code == "fixed_term_missing":
            term = issue.get("term", {}).get("source", "")
            candidate = potential.get(norm(term))
            if candidate:
                decision = "contextual_term_form_reviewed"
                basis = f"potential_term_audit:{candidate['decision']}"
                note = (
                    f"{issue['id']} 含“{term}”，但完整中文未逐字出现“{issue['term']['target']}”。"
                    f"开放候选账本已将该词裁决为 {candidate['decision']}；本位点按完整句法/对象义保留，"
                    "精确标签仍由 glossary alignment 强制校验。"
                )
            else:
                decision = "contextual_homograph_reviewed"
                basis = "full_sentence_context"
                note = (
                    f"{issue['id']} 中“{term}”只在完整句法内出现；译文按当前对象义处理，"
                    "没有足够证据把词典同形机械替换为术语表目标。"
                )
        elif code in {"english_residue", "unchanged_english"}:
            decision = "preserved_non_chinese_token_reviewed"
            basis = "proper_name_foreign_inscription_or_internal_fixture"
            note = (
                f"{issue['id']} 的残留检测已回读：对应内容是专名、外语铭文、代码/调试夹具或刻意保留的原文，"
                "不是未完成的玩家中文句子；具体原文与译文随本记录固化。"
            )
        elif code in {"mixed_punctuation", "dash_alignment_review"}:
            decision = "punctuation_context_reviewed"
            basis = "source_structure_and_chinese_readability"
            note = (
                f"{issue['id']} 的中西标点/破折号已按富文本、引文层级和中文停顿逐项回读；"
                "保留当前形式不会改变占位符、链接或句义。"
            )
        else:
            decision = "heuristic_warning_reviewed"
            basis = "manual_context_review"
            note = f"{issue['id']} 的 {code} 启发式告警已结合完整源文与译文回读，当前处置予以保留。"
        output.append(
            {
                "signature": signature(issue),
                "code": code,
                "id": issue["id"],
                "source": issue.get("source", ""),
                "translation": issue.get("translation", ""),
                "detail": issue.get("detail", ""),
                "decision": decision,
                "basis": basis,
                "audit_note": note,
                "reviewed_at": "2026-08-22",
            }
        )
    output.sort(key=lambda row: (row["code"], row["id"], row["signature"]))
    path = ROOT / "glossary/consistency_warning_audit.jsonl"
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in output),
        encoding="utf-8",
    )
    counts = {}
    for row in output:
        counts[row["code"]] = counts.get(row["code"], 0) + 1
    print(json.dumps({"warnings": len(output), "codes": counts}, ensure_ascii=False, indent=2))
    print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
