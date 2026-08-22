#!/usr/bin/env python3
"""Apply terminology that is explicitly attested on the official Steam page.

This is intentionally source-guarded.  It only changes a row when the English
source contains the relevant capitalised game term (or an explicitly listed
mechanics row), so ordinary words such as ``passion`` and ``sign`` are not
silently rewritten.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

FIXED_ARTS = {
    "光之技艺": "@@BRIGHT_ARTS@@",
    "夜之技艺": "@@NIGHT_ARTS@@",
    "未拾技艺": "@@UNCONSIDERED_ARTS@@",
}


def has_term(source: str, term: str, *, ignore_case: bool = False) -> bool:
    flags = re.IGNORECASE if ignore_case else 0
    return re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", source, flags) is not None


def replace_skill_word(text: str) -> str:
    """Apply the project's in-game rendering of the Skill mechanic.

    The Steam synopsis uses “技能”, but the patch deliberately uses “技艺”
    throughout the game so that the umbrella term agrees with the established
    Chinese register of the predecessor localisations.  This is an explicit
    editorial choice, not an omission of the official-page evidence.
    """
    return text.replace("世俗技能", "世俗技艺").replace("异世技能", "异世技艺").replace("技能", "技艺")


def transform(row: dict[str, str]) -> bool:
    source = row["source"]
    old_translation = row["translation"]
    old_notes = row.get("notes", "")
    translation = old_translation
    notes = old_notes

    # Same-game mechanics terminology, with the user-approved Skill override.
    if has_term(source, "Skill", ignore_case=True) or has_term(source, "Skills", ignore_case=True):
        if row["id"] == "TAN-9DE0E24F3EC6":
            translation = translation.replace("一定技能", "一定技巧").replace("一定技艺", "一定技巧")
        else:
            translation = replace_skill_word(translation)
            notes = replace_skill_word(notes)

    if has_term(source, "Passion") or has_term(source, "Passions"):
        translation = translation.replace("激情", "心念")
        notes = notes.replace("激情", "心念")

    if has_term(source, "Sign") or has_term(source, "Signs"):
        translation = translation.replace("印记", "征象")
        notes = notes.replace("印记", "征象")

    if has_term(source, "Career") and row["id"] != "TAN-29F0E866052E":
        translation = translation.replace("职业", "职涯").replace("生涯", "职涯")
        notes = notes.replace("职业", "职涯").replace("生涯", "职涯")

    if has_term(source, "Spivvery"):
        translation = translation.replace("黑市手腕", "钻营")
        notes = notes.replace("黑市手腕", "钻营")

    if has_term(source, "Sophistication"):
        translation = translation.replace("世故", "修养")
        notes = notes.replace("世故", "修养")

    # Capitalised faction term.  Preserve “全联盟” in the unrelated official
    # Soviet committee name while replacing the old faction rendering.
    if has_term(source, "Ministries"):
        translation = translation.replace("联盟各部", "部委").replace("联盟\n各部", "部委")
        translation = re.sub(r"(?<!全)联盟", "部委", translation)
        notes = notes.replace("联盟各部", "部委")
        notes = re.sub(r"(?<!全)联盟", "部委", notes)
        translation = translation.replace("部委领土", "部委辖区")

    # Singular Ministry occurs in compounds and office titles.  Keep the
    # independently attested “全联盟” in the proper name All-Union Committee.
    if has_term(source, "Ministry"):
        translation = translation.replace("联盟政委", "部委政委")
        translation = translation.replace("联盟文员", "部委文员")
        translation = translation.replace("联盟势力范围", "部委势力范围")
        notes = notes.replace("联盟政委", "部委政委")
        notes = notes.replace("联盟文员", "部委文员")
        notes = notes.replace("联盟势力范围", "部委势力范围")

    # Plural faction = official 集团.  Singular/adjectival Incorporate is also
    # normally 集团, with explicit legal-person contexts refined below.
    if has_term(source, "Incorporates"):
        translation = translation.replace("法人团体", "集团")
        notes = notes.replace("法人团体", "集团")
    elif has_term(source, "Incorporate") and row["id"] != "TAN-C47390808478":
        translation = translation.replace("法人团体", "集团")
        notes = notes.replace("法人团体", "集团")

    if row["id"] in {"TAN-5C0580E48A0A", "TAN-BBEB641B76F5"}:
        translation = re.sub(r"也是集团(?!法人)", "也是集团法人", translation)
        translation = translation.replace("某个集团在此", "某个集团法人在此")

    # Exact official labels and named motives.
    if row["id"] in {"TAN-732863FA5C61", "TAN-7D3C74BB4F28"}:
        translation = translation.replace("生涯", "职涯").replace("职业", "职涯")
    if has_term(source, "Sorrow"):
        translation = translation.replace("悲恸", "哀伤").replace("悲伤", "哀伤")
        notes = notes.replace("悲恸", "哀伤").replace("悲伤", "哀伤")
    if has_term(source, "Curiosity"):
        translation = translation.replace("好奇心", "好奇心")
        if row["id"] == "TAN-C0A70C188A99":
            translation = "好奇心"
    if has_term(source, "Appetite"):
        translation = translation.replace("欲求", "餍足")
        notes = notes.replace("欲求", "餍足")
        if row["id"] == "TAN-1B7037D5C7C8":
            translation = "餍足"
        elif row["id"] == "TAN-DC3AE610370B":
            translation = (
                "空虚原就是用来填满的。餍足之选总是自私，也往往愉快。\n\n"
                "[将这份心念演化为餍足；它会为你的性相池提供刃与杯。]\n\n"
            )
        elif row["id"] == "TAN-FF0F596B1108":
            translation = "[你正放任自己求取餍足。不过人总会变。尤其是斯宾塞·霍布森。]"

    if "War in the Sun" in source or "War in the [[Sun]]" in source:
        translation = translation.replace("太阳大战", "太阳之战")
        translation = translation.replace("[[Sun]]大战", "[[Sun]]之战")
        notes = notes.replace("太阳大战", "太阳之战")
    if "War in the World" in source:
        translation = translation.replace("世界大战", "世界之战")
        notes = notes.replace("世界大战", "世界之战")

    # The career tooltip uses lower-case prose but is the Career mechanic.
    if row["id"] == "TAN-FF692F45A4D1":
        translation = translation.replace("职业", "职涯").replace("技能", "技艺")
        notes = notes.replace("职业", "职涯").replace("技能", "技艺")

    row["translation"] = translation
    row["notes"] = notes
    return translation != old_translation or notes != old_notes


def main() -> None:
    changed_rows = 0
    for path in sorted((ROOT / "translations").glob("chunk_*.jsonl")):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines()]
        changed = sum(transform(row) for row in rows)
        if changed:
            path.write_text(
                "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
                encoding="utf-8",
            )
            changed_rows += changed
            print(f"{path.name}: {changed}")
    print(f"changed_rows={changed_rows}")


if __name__ == "__main__":
    main()
