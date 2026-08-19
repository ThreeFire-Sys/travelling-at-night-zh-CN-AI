"""Re-chunk reviewed translations against an updated extraction worklist.

Existing translations are matched by stable ID.  A small supplemental JSONL can
provide translations for IDs introduced by a newer game build.  The output
chunk layout is copied from the updated worklist so the normal merge validator
can continue to enforce exact ID order.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


REQUIRED_OUTPUT_FIELDS = ("id", "source", "translation", "status", "notes")


class RebaseError(RuntimeError):
    pass


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise RebaseError(f"{path}:{line_number}: row is not an object")
                rows.append(value)
    except (OSError, json.JSONDecodeError) as exc:
        raise RebaseError(f"cannot read {path}: {exc}") from exc
    return rows


def collect_rows(paths: Iterable[Path]) -> dict[str, dict[str, Any]]:
    collected: dict[str, dict[str, Any]] = {}
    for path in paths:
        for row in read_jsonl(path):
            row_id = str(row.get("id", ""))
            if not row_id:
                raise RebaseError(f"{path}: row has no id")
            if row_id in collected:
                raise RebaseError(f"duplicate translation id: {row_id}")
            collected[row_id] = row
    return collected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("updated_worklist_dir", type=Path)
    parser.add_argument("reviewed_translations_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--supplement", type=Path, action="append", default=[])
    args = parser.parse_args()

    worklist_path = args.updated_worklist_dir / "worklist.jsonl"
    worklist = read_jsonl(worklist_path)
    worklist_by_id = {str(row["id"]): row for row in worklist}
    if len(worklist_by_id) != len(worklist):
        raise RebaseError("updated worklist contains duplicate IDs")

    reviewed = collect_rows(sorted(args.reviewed_translations_dir.glob("chunk_*.jsonl")))
    supplement: dict[str, dict[str, Any]] = {}
    if args.supplement:
        supplement = collect_rows(args.supplement)
        overlap = sorted(set(reviewed) & set(supplement))
        if overlap:
            raise RebaseError(f"supplement duplicates reviewed IDs: {overlap[:5]}")

    available = {**reviewed, **supplement}
    missing = sorted(set(worklist_by_id) - set(available))
    if missing:
        raise RebaseError(f"missing {len(missing)} updated IDs: {missing[:10]}")

    args.output_dir.mkdir(parents=True, exist_ok=False)
    emitted: set[str] = set()
    chunk_paths = sorted((args.updated_worklist_dir / "chunks").glob("chunk_*.jsonl"))
    if not chunk_paths:
        raise RebaseError("updated worklist has no chunk files")

    for source_chunk_path in chunk_paths:
        source_rows = read_jsonl(source_chunk_path)
        output_path = args.output_dir / source_chunk_path.name
        with output_path.open("w", encoding="utf-8", newline="\n") as handle:
            for source_row in source_rows:
                row_id = str(source_row["id"])
                if row_id in emitted:
                    raise RebaseError(f"updated chunks repeat ID: {row_id}")
                reviewed_row = available[row_id]
                reviewed_source = reviewed_row.get("source")
                if reviewed_source is not None and str(reviewed_source) != str(source_row.get("source", "")):
                    raise RebaseError(f"source mismatch for {row_id}")
                output_row = {
                    "id": row_id,
                    "source": source_row["source"],
                    "translation": reviewed_row.get("translation", ""),
                    "status": reviewed_row.get("status", "translated"),
                    "notes": reviewed_row.get("notes", ""),
                }
                if not str(output_row["translation"]).strip():
                    raise RebaseError(f"empty translation for {row_id}")
                handle.write(json.dumps(output_row, ensure_ascii=False, separators=(",", ":")) + "\n")
                emitted.add(row_id)

    if emitted != set(worklist_by_id):
        missing_from_chunks = sorted(set(worklist_by_id) - emitted)
        raise RebaseError(f"updated chunks omit IDs: {missing_from_chunks[:10]}")

    retired = sorted(set(reviewed) - set(worklist_by_id))
    print(
        json.dumps(
            {
                "updated_entries": len(worklist),
                "reused_entries": len(set(reviewed) & set(worklist_by_id)),
                "supplement_entries": len(supplement),
                "retired_entries": len(retired),
                "output_chunks": len(chunk_paths),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RebaseError as exc:
        raise SystemExit(f"error: {exc}")
