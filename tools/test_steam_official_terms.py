#!/usr/bin/env python3
"""Source-aware regression checks for same-game official Steam terminology."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def has_term(source: str, term: str, *, ignore_case: bool = False) -> bool:
    flags = re.IGNORECASE if ignore_case else 0
    return re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", source, flags) is not None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--translations", type=Path, default=ROOT / "translations_k97")
    args = parser.parse_args()
    rows: list[dict[str, str]] = []
    for path in sorted(args.translations.glob("chunk_*.jsonl")):
        rows.extend(json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines())

    errors: list[str] = []
    exact = {
        "TAN-732863FA5C61": "职涯",
        "TAN-7D3C74BB4F28": "职涯：",
        "TAN-66D0F523A379": "技艺",
        "TAN-88F4BEE41EE1": "心念",
        "TAN-9CB5654B5540": "征象",
        "TAN-AE37AE2AE4BD": "钻营",
        "TAN-37DFCC3DE92B": "修养",
        "TAN-2886DEC38D47": "部委",
        "TAN-25A04C672386": "集团",
        "TAN-871C47DEB97B": "哀伤",
        "TAN-1B7037D5C7C8": "餍足",
        "TAN-DC3AE610370B": "空虚原就是用来填满的。餍足之选总是自私，也往往愉快。\n\n[将这份心念演化为餍足；它会为你的性相池提供刃与杯。]\n\n",
        "TAN-FF0F596B1108": "[你正放任自己求取餍足。不过人总会变。尤其是斯宾塞·霍布森。]",
        "TAN-C0A70C188A99": "好奇心",
    }
    by_id = {row["id"]: row for row in rows}
    for row_id, expected in exact.items():
        actual = by_id.get(row_id, {}).get("translation")
        if actual != expected:
            errors.append(f"{row_id}: expected {expected!r}, got {actual!r}")

    for row in rows:
        source, target, row_id = row["source"], row["translation"], row["id"]
        if (has_term(source, "Skill", ignore_case=True) or has_term(source, "Skills", ignore_case=True)):
            if "技能" in target:
                errors.append(f"{row_id}: Skill mechanism retains 技能")
        if (has_term(source, "Passion") or has_term(source, "Passions")) and "激情" in target:
            errors.append(f"{row_id}: Passion mechanism retains 激情")
        if has_term(source, "Appetite") and "欲求" in target:
            errors.append(f"{row_id}: official Appetite term retains old 欲求")
        if (has_term(source, "Sign") or has_term(source, "Signs")) and "印记" in target:
            errors.append(f"{row_id}: Sign mechanism retains 印记")
        if has_term(source, "Ministries"):
            old = target.replace("全联盟", "")
            if "联盟" in old or "联盟各部" in old:
                errors.append(f"{row_id}: Ministries retains old faction rendering")
        if has_term(source, "Incorporates") and "法人团体" in target:
            errors.append(f"{row_id}: Incorporates retains old faction rendering")

    print(json.dumps({"rows": len(rows), "errors": errors, "error_count": len(errors)}, ensure_ascii=False, indent=2))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
