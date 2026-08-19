#!/usr/bin/env python3
"""Apply high-confidence graph/terminology fixes to the j.46 candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


FIXES = {
    "TAN-148DCD99F19D": (
        "昂蒂布。战争降临人世之前——",
        "昂蒂布。战争降临世界之前——",
        "与同源长句统一 World／世界。",
    ),
    "TAN-23A00CD4CAA3": (
        "悲影笼罩？",
        "哀伤笼罩？",
        "机制对话标题中的 Sorrow 统一为‘哀伤’。",
    ),
    "TAN-D62D5A38472F": (
        "走开。",
        "离开。",
        "真实父节点显示四处均为玩家退出当前对话，不是命令对方走开。",
    ),
    "TAN-F872ECBD3A23": (
        "<i>虽有许多尚存……也已有许多被夺走。</i>\n\n一项[[Passion]]。\n\n"
        "[承认悔恨的选择属于悲恸之选。通常，选择沉默也是。]",
        "<i>虽有许多尚存……也已有许多被夺走。</i>\n\n一项[[Passion]]。\n\n"
        "[承认悔恨的选择属于哀伤之选。通常，选择沉默也是。]",
        "机制说明中的 Sorrowful 统一为‘哀伤’。",
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("translations", type=Path)
    args = parser.parse_args()

    found: set[str] = set()
    changed = 0
    for path in sorted(args.translations.glob("chunk_*.jsonl")):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        touched = False
        for row in rows:
            row_id = str(row.get("id", ""))
            if row_id not in FIXES:
                continue
            if row_id in found:
                raise RuntimeError(f"duplicate target ID: {row_id}")
            found.add(row_id)
            expected, replacement, note = FIXES[row_id]
            current = str(row.get("translation", ""))
            if current != expected:
                raise RuntimeError(
                    f"unexpected current translation for {row_id}: {current!r}"
                )
            row["translation"] = replacement
            existing_note = str(row.get("notes", "")).strip()
            row["notes"] = f"{existing_note} {note}".strip()
            changed += 1
            touched = True
        if touched:
            with path.open("w", encoding="utf-8", newline="\n") as handle:
                for row in rows:
                    handle.write(
                        json.dumps(row, ensure_ascii=False, separators=(",", ":"))
                        + "\n"
                    )

    missing = sorted(set(FIXES) - found)
    if missing:
        raise RuntimeError(f"missing target IDs: {missing}")
    print(json.dumps({"reviewed": len(FIXES), "changed": changed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
