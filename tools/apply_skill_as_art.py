#!/usr/bin/env python3
"""Apply the editorial decision Skill(s) = 技艺 to translated player text.

The replacement is source guarded: only rows whose English source contains
the standalone word ``skill`` or ``skills`` are touched.  This prevents
ordinary Chinese prose elsewhere from being rewritten.  The one row where
English ``skills`` means general dexterity rather than the named mechanic is
kept as ``技巧``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_RE = re.compile(r"(?<![A-Za-z])skills?(?![A-Za-z])", re.IGNORECASE)
GENERAL_DEXTERITY_IDS = {"TAN-9DE0E24F3EC6"}


def main() -> None:
    changed_rows = 0
    for path in sorted((ROOT / "translations").glob("chunk_*.jsonl")):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines()]
        changed = 0
        for row in rows:
            if not SKILL_RE.search(row["source"]):
                continue
            replacement = "技巧" if row["id"] in GENERAL_DEXTERITY_IDS else "技艺"
            old_translation = row["translation"]
            old_notes = row.get("notes", "")
            row["translation"] = old_translation.replace("技能", replacement)
            row["notes"] = old_notes.replace("技能", replacement)
            if row["translation"] != old_translation or row["notes"] != old_notes:
                changed += 1
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
