#!/usr/bin/env python3
"""Ensure My Past reveal states only append text after their visible prefix."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MEMORY_LINK_RE = re.compile(r'<link="(mypast[^"]+)">')
LEGION_EXCEPTION = "mypasteveofstjamesthegreater"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--catalog", type=Path, default=ROOT / "build/merged_k97/review_catalog.jsonl"
    )
    parser.add_argument(
        "--fields", type=Path, default=ROOT / "build/extracted_k97/all_string_fields.jsonl"
    )
    return parser.parse_args()


def short_source_body(value: str) -> tuple[str, bool]:
    body = value.split("\n\nRecall ", 1)[0].rstrip()
    if body.endswith("..."):
        return body[:-3].rstrip(), True
    return body, False


def short_target_body(value: str, expects_ellipsis: bool) -> str:
    body = value.split("\n\n", 1)[0].rstrip()
    if expects_ellipsis:
        if not body.endswith("……"):
            raise ValueError("translated concealed state must end with a Chinese ellipsis")
        return body[:-2]
    return body


def main() -> int:
    args = parse_args()
    catalog = [
        json.loads(line)
        for line in args.catalog.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    fields = [
        json.loads(line)
        for line in args.fields.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    id_paths = {
        row["source"]: row["path_id"]
        for row in fields
        if row.get("field_path") == "id" and row.get("source", "").startswith("mypast")
    }
    full_by_path = {
        context["path_id"]: row
        for row in catalog
        for context in row.get("contexts", [])
        if context.get("asset_file") == "resources.assets"
        and context.get("field_path") == "description"
        and context.get("script", "").startswith("Travelling.Infrastructure.Footnotes.Footnote")
    }
    errors: list[str] = []
    pairs = 0
    source_exceptions: list[str] = []
    seen_links: set[str] = set()
    for short in catalog:
        match = MEMORY_LINK_RE.search(short.get("source", ""))
        if match is None:
            continue
        link_id = match.group(1)
        pairs += 1
        seen_links.add(link_id)
        path_id = id_paths.get(link_id)
        full = full_by_path.get(path_id) if path_id is not None else None
        if full is None:
            errors.append(f"{link_id}: revealed Footnote description not found")
            continue
        source_core, concealed = short_source_body(short["source"])
        source_prefix_ok = full["source"].startswith(source_core)
        if not source_prefix_ok:
            source_exceptions.append(link_id)
        try:
            target_core = short_target_body(short.get("translation", ""), concealed)
        except ValueError as exc:
            errors.append(f"{link_id}: {exc}")
            continue
        full_target = full.get("translation", "")
        if source_prefix_ok:
            if not full_target.startswith(target_core):
                errors.append(
                    f"{link_id}: Chinese reveal rewrites visible prefix: "
                    f"{target_core[:55]!r} != {full_target[:55]!r}"
                )
        elif link_id == LEGION_EXCEPTION:
            # The English full state alone inserts "of the [[Légion]]".  Chinese
            # may therefore insert [[军团]], but every surrounding character stays fixed.
            without_legion = full_target.replace("[[军团]]", "", 1)
            if not full_target.startswith("我们[[军团]]") or not without_legion.startswith(target_core):
                errors.append(f"{link_id}: Légion exception changes more than the source does")
        else:
            errors.append(f"{link_id}: unreviewed English source-prefix exception")

    expected_links = set(id_paths)
    if pairs != 17 or seen_links != expected_links:
        errors.append(
            f"memory pair inventory drift: pairs={pairs}, links={len(seen_links)}, "
            f"footnote ids={len(expected_links)}"
        )
    if source_exceptions != [LEGION_EXCEPTION]:
        errors.append(f"unexpected English source-prefix exceptions: {source_exceptions!r}")
    print(
        json.dumps(
            {
                "pairs": pairs,
                "exact_english_prefix_pairs": pairs - len(source_exceptions),
                "source_exceptions": source_exceptions,
                "errors": errors,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
