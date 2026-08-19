#!/usr/bin/env python3
"""Apply the final, manually reviewed j.33 translation corrections.

The worklist is fingerprinted and each ID is unique.  Keeping these edits in a
small deterministic script makes the very long patch-notes JSONL row auditable
without hand-editing or reserialising unrelated records.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRANSLATIONS = ROOT / "build" / "translations_j33"

DIRECT_FIXES = {
    "TAN-A902603CE266": (
        "DEBUG：提前退出",
        "实际奥比耶对话中的可显示调试行；无不可达证明，按漏翻修复。",
    ),
    "TAN-B6F0E697F22F": (
        "DEBUG：提前退出，划走",
        "实际奥比耶对话中的可显示调试行；无不可达证明，按漏翻修复。",
    ),
    "TAN-D218670E6F16": (
        "重要：没错，这里正是回应心念选项的机会。",
        "实际文森特对话中的开发占位，按可显示文本翻译。",
    ),
    "TAN-0041826E9734": (
        "yyyy/MM/dd",
        "简中日期格式改用年／月／日顺序。",
    ),
    "TAN-5884300AEEAF": (
        "斯莫克",
        "与 TAN-31FB41158829 的既定专名音译统一。",
    ),
    "TAN-72A43EABBA1D": (
        "待定",
        "玩家可见的套装说明占位语；译出以避免英文漏出。",
    ),
    "TAN-9F86D081884C": (
        "测试",
        "“半正式”难度条目的占位说明；按可见字段翻译。",
    ),
}


def patch_notes(text: str) -> str:
    replacements = {
        "* 本体梦理协调局 +": "* 本体梦理协调办公室 +",
        "* 它又发生了——还记得《司辰之书》里“工作台打开时不再喵叫”吗？现在把物品拖入生效栏位时也不会喵叫了": (
            "* 它又发生了——还记得《司辰之书》里“工作台打开时不再喵叫”吗？"
            "如今在《夜游漫记》里，把物品拖入生效栏位时也不会再喵叫了"
        ),
        "Chez Félix": "菲利克斯之家",
    }
    for source, target in replacements.items():
        if source not in text:
            raise RuntimeError(f"patch-notes review source is missing: {source!r}")
        text = text.replace(source, target)
    return text


def main() -> int:
    seen: set[str] = set()
    for path in sorted(TRANSLATIONS.glob("chunk_*.jsonl")):
        changed = False
        rows = []
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            row = json.loads(line)
            row_id = row["id"]
            if row_id in DIRECT_FIXES:
                row["translation"], row["notes"] = DIRECT_FIXES[row_id]
                seen.add(row_id)
                changed = True
            elif row_id == "TAN-39F83BAE9CB6":
                if not row["translation"].endswith("。]]"):
                    raise RuntimeError("reviewed source-link typo fixture changed")
                row["translation"] = row["translation"][:-1]
                row["notes"] = (
                    "旧版开发结尾；修复源文多余右方括号；保留双段落、邮箱，"
                    "Cross 固定译“介壳种”。"
                )
                seen.add(row_id)
                changed = True
            elif row_id == "TAN-44442E3EDADB":
                row["translation"] = patch_notes(row["translation"])
                row["notes"] = (
                    "玩家可见的版本新闻；同步 j.34 新段并保留 Markdown 标题、列表与"
                    "版本顺序；依终审统一作品、机构与地点名。"
                )
                seen.add(row_id)
                changed = True
            rows.append(row)
        if changed:
            with path.open("w", encoding="utf-8", newline="\n") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    expected = set(DIRECT_FIXES) | {"TAN-39F83BAE9CB6", "TAN-44442E3EDADB"}
    if seen != expected:
        raise RuntimeError(f"review fix ID mismatch: missing={sorted(expected-seen)} extra={sorted(seen-expected)}")
    print(f"Applied {len(seen)} final review fixes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
