#!/usr/bin/env python3
"""Guard reviewed inside/outside viewpoint renderings against regression."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    # Spencer is standing outside the station car and peers through its glass.
    "TAN-06BB8F09DBB3": "[隔着昏暗的车窗朝里瞥一眼。]",
    # Spencer has entered Aubière's dream: beyond the outer defences, but not
    # all the way through the doctor's remaining inner protections.
    "TAN-FB98AA9A7A0C": "已在奥比耶的防线之内，却尚未穿透全部防线。",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--translations", type=Path, default=ROOT / "translations")
    args = parser.parse_args()
    by_id: dict[str, dict] = {}
    for path in sorted(args.translations.glob("chunk_*.jsonl")):
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            row = json.loads(line)
            by_id[row["id"]] = row
    errors = []
    for row_id, expected in EXPECTED.items():
        actual = by_id.get(row_id, {}).get("translation")
        if actual != expected:
            errors.append(f"{row_id}: expected {expected!r}, got {actual!r}")
    print(json.dumps({"checked": len(EXPECTED), "error_count": len(errors), "errors": errors}, ensure_ascii=False, indent=2))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
