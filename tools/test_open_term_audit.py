#!/usr/bin/env python3
"""Validate open-set term discovery, provisional rows and predecessor reuse."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE_REF = "v2.6.0"
STALE_RE = re.compile(r"(?<!短)暂(?!时)|待.{0,20}(?:校|核|统一)|需.{0,20}(?:校|核|统一)")


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(raw) for raw in path.read_text(encoding="utf-8-sig").splitlines() if raw]


def norm(value: str) -> str:
    return " ".join(value.replace("’", "'").split()).casefold()


def baseline_provisional_ids() -> set[str]:
    ids = set()
    for index in range(1, 16):
        relative = f"translations_k97/chunk_{index:03d}.jsonl"
        result = subprocess.run(
            ["git", "show", f"{BASELINE_REF}:{relative}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        for raw in result.stdout.decode("utf-8-sig").splitlines():
            if raw:
                row = json.loads(raw)
                if STALE_RE.search(row.get("notes", "") or ""):
                    ids.add(row["id"])
    return ids


def latest_catalog() -> Path:
    """当前合并目录：build/merged_* 中取最新（游戏版本迁移后自动跟随）。"""
    import glob
    import os
    candidates = sorted(
        glob.glob(str(ROOT / "build" / "merged_*")), key=os.path.getmtime
    )
    if not candidates:
        raise SystemExit("未找到 build/merged_* 合并目录")
    return Path(candidates[-1]) / "review_catalog.jsonl"


def strip_links(value: str) -> str:
    return value.replace("[[", "").replace("]]", "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--translations", type=Path, default=ROOT / "translations_k97")
    parser.add_argument("--catalog", type=Path, default=None)
    args = parser.parse_args()
    catalog_path = args.catalog or latest_catalog()
    errors = []

    current_rows = {}
    for path in sorted(args.translations.glob("chunk_*.jsonl")):
        for row in load_jsonl(path):
            current_rows[row["id"]] = row
            stale = STALE_RE.search(row.get("notes", "") or "")
            if stale:
                errors.append(f"{row['id']}: residual provisional marker {stale.group(0)!r}")

    discovery_output = ROOT / "build/reviews/potential_term_candidates_test.json"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(ROOT / "tools/discover_potential_terms.py"),
            "--translations",
            str(args.translations),
            "--catalog",
            str(catalog_path),
            "--notes-baseline-ref",
            BASELINE_REF,
            "--output",
            str(discovery_output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode:
        errors.append(f"potential discovery failed: {result.stderr[-500:]}")
        discovered = []
    else:
        discovered = json.loads(discovery_output.read_text(encoding="utf-8-sig"))["candidates"]

    potential = load_jsonl(ROOT / "glossary/potential_term_audit.jsonl")
    potential_by_norm = {norm(row["candidate"]): row for row in potential}
    if len(potential_by_norm) != len(potential):
        errors.append("potential-term audit has duplicate normalized candidates")
    discovered_norms = {norm(row["candidate"]) for row in discovered}
    if discovered_norms != set(potential_by_norm):
        missing = sorted(discovered_norms - set(potential_by_norm))[:20]
        obsolete = sorted(set(potential_by_norm) - discovered_norms)[:20]
        errors.append(f"potential candidate ledger drift missing={missing} obsolete={obsolete}")
    for row in potential:
        if row.get("decision") == "pending" or not row.get("decision"):
            errors.append(f"{row.get('candidate')}: pending potential-term decision")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(row.get("reviewed_at") or "")):
            errors.append(f"{row.get('candidate')}: missing review date")
        if len(str(row.get("audit_note", ""))) < 20:
            errors.append(f"{row.get('candidate')}: audit note too short")
        if not row.get("evidence_locators"):
            errors.append(f"{row.get('candidate')}: missing evidence locators")

    provisional = load_jsonl(ROOT / "glossary/provisional_row_audit.jsonl")
    provisional_ids = {row["id"] for row in provisional}
    baseline_ids = baseline_provisional_ids()
    if provisional_ids != baseline_ids:
        errors.append(
            f"provisional baseline coverage drift missing={sorted(baseline_ids-provisional_ids)[:20]} "
            f"extra={sorted(provisional_ids-baseline_ids)[:20]}"
        )
    for row in provisional:
        current = current_rows.get(row["id"])
        if current is None:
            if row.get("retired_in"):
                # 源文被游戏更新改写/删除（retired_in 标记版本）：历史裁决保留，
                # 不再要求当前译文在位。接任行（若有）记 successor_id 备查。
                continue
            # 游戏版本更新可能让源文修订、换新内容哈希 ID（如 l.8 给 Worms 补链接）。
            # 台账行保留历史 ID 以维持基线覆盖，接任行用 successor_id 登记；
            # 接任译文允许只多链接括号（[[ ]]），其余逐字等于定稿译文。
            successor_id = row.get("successor_id")
            successor = current_rows.get(successor_id) if successor_id else None
            if successor is None:
                errors.append(f"{row['id']}: audited provisional row absent from current translations")
                continue
            if strip_links(successor["translation"]) != strip_links(row.get("translation_final", "")):
                errors.append(f"{row['id']}: provisional successor translation drift")
        elif current["translation"] != row.get("translation_final"):
            errors.append(f"{row['id']}: provisional final translation drift")
        if row.get("decision") not in {"change", "retain_after_review"}:
            errors.append(f"{row['id']}: invalid provisional decision")

    exact = load_jsonl(ROOT / "glossary/predecessor_exact_source_audit.jsonl")
    exact_ids = {row["id"] for row in exact}
    if len(exact) != 83 or len(exact_ids) != 83:
        errors.append(f"expected 83 unique predecessor exact-source audits, found {len(exact)}/{len(exact_ids)}")
    for row in exact:
        current = current_rows.get(row["id"])
        if current is None or current["translation"] != row.get("translation_final"):
            errors.append(f"{row['id']}: predecessor exact-source final drift")
        if not row.get("evidence_locators") or len(str(row.get("audit_note", ""))) < 20:
            errors.append(f"{row['id']}: incomplete predecessor exact-source evidence")

    expected_rows = {
        "TAN-5B5611A26303": "[你会尽力恪守操守。尽管人总会改变，尤其是斯宾塞·霍布森。]",
        "TAN-5181ACAB7562": "无人注视时的所作所为，才显出你是什么人。\n\n一项[[Passion]]。\n\n[出于操守的选择，可能关乎自律、诚实，或者不过是一点礼貌。]",
        "TAN-7200F34A125D": "“但我们必须动用刀刃，”以狮背为王座者说，“动用绞索、火焰、唤醒之语，去对付那些穿过三膜之门的人。因此，谁也不得通过：这就是我们的律法，也是太阳的律法。”",
        "TAN-360C30A29EA2": "《制烛人的传说》",
    }
    for row_id, target in expected_rows.items():
        if current_rows.get(row_id, {}).get("translation") != target:
            errors.append(f"{row_id}: open-term regression")

    with (ROOT / "glossary/link_targets.csv").open(encoding="utf-8-sig") as handle:
        link_text = handle.read()
    for expected in ("Ivory Dove,骨白鸽", "Lark,百灵鸟"):
        if expected not in link_text:
            errors.append(f"link registry missing corrected form: {expected}")

    summary = {
        "current_rows": len(current_rows),
        "potential_candidates": len(potential),
        "published_provisional_rows": len(provisional),
        "predecessor_exact_sources": len(exact),
        "errors": errors,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
