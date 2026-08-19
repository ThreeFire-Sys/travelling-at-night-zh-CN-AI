#!/usr/bin/env python3
"""Regression test for conversation-level interaction titles.

These values live in Pixel Crushers conversation ``Description`` fields.  A
previous extractor only admitted actor/item descriptions, which left every
scene-interaction heading in English.  This check makes that omission a hard
failure for future Demo updates.

v2.2.12 起改为直接断言当前工作单（worklist_k6）含有这批条目及其形态；
此前对比的两个历史工作单快照已在项目清理中删除。
"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKLIST = ROOT / "build" / "worklist_k6" / "worklist.jsonl"


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines()]


def main() -> None:
    rows = load(WORKLIST)
    # 对话标题 = dialogue_ui 域中挂在 conversations.[N].fields.[M].value 的
    # "Description" 位点。同域还合法地包含 actor 描述与 SkillCheckModifier 说明。
    TITLE_PATH = re.compile(r"^conversations\.\[\d+\]\.fields\.\[\d+\]\.value$")
    titles = []
    for row in rows:
        if row.get("domain") != "dialogue_ui":
            continue
        title_contexts = [c for c in (row.get("contexts") or [])
                          if TITLE_PATH.fullmatch(c.get("field_path", ""))
                          and c.get("field_title") == "Description"]
        if title_contexts:
            titles.append((row, title_contexts))
    errors: list[str] = []

    # 历史回归点：对话标题必须被工作单收录且形态正确。
    if len(titles) < 128:
        errors.append(f"expected at least 128 conversation titles, got {len(titles)}")

    for row, contexts in titles:
        row_id = row.get("id", "<missing>")
        for context in contexts:
            if not context.get("conversation"):
                errors.append(f"{row_id}: missing conversation identity")
        if not row.get("source"):
            errors.append(f"{row_id}: empty source")

    report = {
        "worklist_count": len(rows),
        "conversation_titles": len(titles),
        "error_count": len(errors),
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
