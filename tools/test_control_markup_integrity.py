#!/usr/bin/env python3
"""Hard-fail when translation corrupts engine control tokens or rich tags."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROL = re.compile(r"\[(?:END|Craft)\]")
TAG = re.compile(r"<[^<>]+>")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--translations", type=Path, default=ROOT / "translations")
    args = parser.parse_args()
    errors: list[str] = []
    count = 0
    for path in sorted(args.translations.glob("chunk_*.jsonl")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line:
                continue
            row = json.loads(line)
            source, target = row["source"], row["translation"]
            count += 1
            if CONTROL.findall(source) != CONTROL.findall(target):
                errors.append(f"{path.name}:{number}:{row['id']}: control token mismatch")
            if TAG.findall(source) != TAG.findall(target):
                errors.append(f"{path.name}:{number}:{row['id']}: rich tag mismatch")
    if errors:
        raise SystemExit("\n".join(errors))
    print(json.dumps({"checked": count, "errors": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
