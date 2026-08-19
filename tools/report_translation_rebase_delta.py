#!/usr/bin/env python3
"""Report added and retired translation rows across worklist revisions."""

from __future__ import annotations

import argparse
import difflib
import json
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("updated_worklist", type=Path)
    parser.add_argument("reviewed_translations", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--closest", type=int, default=3)
    args = parser.parse_args()

    updated = read_jsonl(args.updated_worklist)
    reviewed = [
        row
        for path in sorted(args.reviewed_translations.glob("chunk_*.jsonl"))
        for row in read_jsonl(path)
    ]
    updated_by_id = {str(row["id"]): row for row in updated}
    reviewed_by_id = {str(row["id"]): row for row in reviewed}
    if len(updated_by_id) != len(updated) or len(reviewed_by_id) != len(reviewed):
        raise SystemExit("duplicate IDs in inputs")

    added_ids = sorted(set(updated_by_id) - set(reviewed_by_id))
    retired_ids = sorted(set(reviewed_by_id) - set(updated_by_id))
    retired = [reviewed_by_id[row_id] for row_id in retired_ids]
    additions: list[dict[str, Any]] = []
    for row_id in added_ids:
        row = updated_by_id[row_id]
        source = str(row.get("source", ""))
        candidates = sorted(
            (
                (
                    difflib.SequenceMatcher(
                        None, source.casefold(), str(old.get("source", "")).casefold()
                    ).ratio(),
                    old,
                )
                for old in retired
            ),
            key=lambda pair: pair[0],
            reverse=True,
        )[: args.closest]
        additions.append(
            {
                **row,
                "closest_retired": [
                    {
                        "similarity": round(score, 4),
                        "id": old.get("id", ""),
                        "source": old.get("source", ""),
                        "translation": old.get("translation", ""),
                        "notes": old.get("notes", ""),
                    }
                    for score, old in candidates
                ],
            }
        )

    report = {
        "tool": "report_translation_rebase_delta.py",
        "schema_version": 1,
        "inputs": {
            "updated_worklist": str(args.updated_worklist.resolve()),
            "reviewed_translations": str(args.reviewed_translations.resolve()),
        },
        "summary": {
            "updated": len(updated),
            "reviewed": len(reviewed),
            "reused": len(set(updated_by_id) & set(reviewed_by_id)),
            "added": len(added_ids),
            "retired": len(retired_ids),
        },
        "additions": additions,
        "retired": retired,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Output: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
