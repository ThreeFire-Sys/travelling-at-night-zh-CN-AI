#!/usr/bin/env python3
"""Detect obvious encoding loss and empty/corrupt player-facing translations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--translations", type=Path, default=ROOT / "translations")
    args = parser.parse_args()
    errors: list[str] = []
    rows = 0
    for path in sorted(args.translations.glob("chunk_*.jsonl")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            row = json.loads(line)
            rows += 1
            target = str(row.get("translation", ""))
            notes = str(row.get("notes", ""))
            if not target.strip():
                errors.append(f"{path.name}:{line_number}:{row.get('id')}: empty translation")
            # A run of ASCII question marks is not natural Chinese prose in
            # this catalog.  It is the characteristic result of passing UTF-8
            # literals through a legacy Windows console code page.
            if "???" in target or "???" in notes:
                errors.append(f"{path.name}:{line_number}:{row.get('id')}: question-mark encoding loss")
            if "\ufffd" in target or "\ufffd" in notes:
                errors.append(f"{path.name}:{line_number}:{row.get('id')}: replacement character")

    print(json.dumps({"rows": rows, "error_count": len(errors), "errors": errors}, ensure_ascii=False, indent=2))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
