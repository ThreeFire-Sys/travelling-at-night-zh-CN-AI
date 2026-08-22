#!/usr/bin/env python3
"""Audit cross-domain mechanism terms and genuinely same-source phrases."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


STATE_TAGS = {
    "Potential", "Possessed", "Flattery", "Spontaneity",
    "Sincere", "Insincere", "Truth", "Lie",
}

CANONICAL_ROWS = {
    "TAN-AECEF4454428": ("疲惫", "痛苦", "恐惧", "入迷"),
    "TAN-AD6CF3B17502": ("痛苦搅扰",),
    "TAN-E25AF64C3F26": ("恐惧与入迷",),
    "TAN-D96DBEE009A9": ("记忆",),
    "TAN-B62D1DCC1209": ("份冬之经历",),
    "TAN-77CD358ADEBF": ("犬儒之选", "演化为犬儒"),
    "TAN-F2C1CB0E38CB": ("演化为好奇心",),
    "TAN-00518A3891EB": ("心怀同情",),
    "TAN-7A0E132B3C00": ("乌布",),
    "TAN-F4DC389C93BC": ("叶疫",),
    "TAN-C57F4FE24EE8": ("秘学知识",),
    "TAN-AA8948D6FC24": ("米马塔",),
}


def strip_state_tag(value: str) -> tuple[str | None, str]:
    match = re.match(r"^\[([^\]]+)\]\s*", value)
    if not match or match.group(1) not in STATE_TAGS:
        return None, value
    return match.group(1), value[match.end():]


def strip_translated_tag(value: str) -> str:
    return re.sub(r"^\[[^\]]+\]\s*", "", value)


def compact_whitespace(value: str) -> str:
    return re.sub(r"\s+", "", value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--translations", type=Path, default=Path("translations_k6"))
    parser.add_argument("--report", type=Path, default=Path("build/reviews/global_semantic_consistency_j46.json"))
    args = parser.parse_args()

    rows = []
    # Supplement files are provenance snapshots whose rows are already folded
    # into chunk_*.jsonl by rebase; loading both silently double-counts them.
    for path in sorted(args.translations.glob("chunk_*.jsonl")):
        rows.extend(
            json.loads(line)
            for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line
        )
    by_id = {row["id"]: row for row in rows}
    errors: list[str] = []

    canonical_checks = 0
    for row_id, required_fragments in CANONICAL_ROWS.items():
        row = by_id.get(row_id)
        if row is None:
            errors.append(f"missing canonical row {row_id}")
            continue
        for fragment in required_fragments:
            canonical_checks += 1
            if fragment not in row["translation"]:
                errors.append(f"{row_id} missing canonical fragment {fragment!r}")

    # Identical English bodies behind state/intent labels are the same authored
    # sentence. The Chinese body must not drift merely because its gate changed.
    tagged_groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        tag, body = strip_state_tag(row["source"])
        if tag is not None:
            tagged_groups[body].append(row)
    reviewed_tagged_groups = 0
    for source_body, group in tagged_groups.items():
        if len(group) < 2:
            continue
        reviewed_tagged_groups += 1
        translated_bodies = {strip_translated_tag(row["translation"]) for row in group}
        if len(translated_bodies) != 1:
            errors.append(
                "state-tag drift: " + source_body + " :: " +
                ", ".join(row["id"] for row in group)
            )

    # Source variants that differ only by authored layout whitespace must keep
    # the same wording. Translation line breaks remain free to match each UI.
    whitespace_groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        whitespace_groups[compact_whitespace(row["source"])].append(row)
    reviewed_whitespace_groups = 0
    for source_key, group in whitespace_groups.items():
        if len({row["source"] for row in group}) < 2:
            continue
        reviewed_whitespace_groups += 1
        targets = {compact_whitespace(row["translation"]) for row in group}
        if len(targets) != 1:
            errors.append(
                "whitespace-source drift: " + source_key + " :: " +
                ", ".join(row["id"] for row in group)
            )

    # Cross-domain proper names / UI concepts: no known legacy spelling may
    # remain in a row that names the same entity or setting.
    forbidden = {
        "Riviera": ("里维埃拉",),
        "Ubu": ("于布",),
        "Mimata": ("米玛塔",),
        "Plague of Leaves": ("叶之瘟疫",),
    }
    cross_domain_rows = 0
    for row in rows:
        for source_term, forbidden_targets in forbidden.items():
            if source_term.lower() not in row["source"].lower():
                continue
            cross_domain_rows += 1
            for bad in forbidden_targets:
                if bad in compact_whitespace(row["translation"]):
                    errors.append(f"{row['id']} retains legacy {source_term} form {bad!r}")

    predecessor_mechanism_rows = 0
    for row in rows:
        if "fascination" not in row["source"].casefold():
            continue
        predecessor_mechanism_rows += 1
        for bad in ("迷狂", "迷恋", "着迷"):
            if bad in row["translation"]:
                errors.append(f"{row['id']} does not use predecessor Fascination term 入迷: {bad!r}")

    report = {
        "rows": len(rows),
        "canonical_checks": canonical_checks,
        "state_tag_same_body_groups": reviewed_tagged_groups,
        "whitespace_equivalent_source_groups": reviewed_whitespace_groups,
        "cross_domain_name_rows": cross_domain_rows,
        "predecessor_fascination_rows": predecessor_mechanism_rows,
        "unresolved": errors,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
