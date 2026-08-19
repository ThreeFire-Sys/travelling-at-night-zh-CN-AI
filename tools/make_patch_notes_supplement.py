#!/usr/bin/env python3
"""Create the reviewed translation row for the extracted patch-notes TextAsset."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKLIST = ROOT / "build" / "worklist_j33" / "worklist.jsonl"
TRANSLATION = ROOT / "localization" / "patch-notes.zh-CN.md"
OUTPUT = ROOT / "build" / "reviews" / "patch_notes_j33_supplement.jsonl"
TARGET_ID = "TAN-44442E3EDADB"


def main() -> int:
    row = next(
        json.loads(line)
        for line in WORKLIST.read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("id") == TARGET_ID
    )
    translation = TRANSLATION.read_text(encoding="utf-8")
    if not translation.strip():
        raise RuntimeError("patch-notes translation is empty")
    output = {
        "id": TARGET_ID,
        "source": row["source"],
        "translation": translation,
        "status": "translated",
        "notes": "玩家可见的版本新闻；同步 j.34 新段并保留 Markdown 标题、列表与版本顺序；依用户裁决不再作新闻页文学精修。",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
