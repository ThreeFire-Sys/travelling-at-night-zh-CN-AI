#!/usr/bin/env python3
"""Regression-test the runtime fallback for already-rendered footnote links."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


WIKI_RE = re.compile(r"\[\[([^\[\]]+)\]\]")
TMP_RE = re.compile(
    r"<link\s*=\s*(?P<quote>[\"'])(?P<id>.*?)(?P=quote)[^>]*>.*?</link>",
    re.I | re.S,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worklist", type=Path, default=Path("build/worklist_k6/worklist.jsonl"))
    parser.add_argument("--catalog", type=Path, default=Path("build/merged_k6/catalog.zh-CN.json"))
    parser.add_argument("--links", type=Path, default=Path("build/merged_k6/link_targets.zh-CN.json"))
    args = parser.parse_args()

    catalog = load_json(args.catalog)
    links = load_json(args.links)
    checked = 0
    errors: list[str] = []
    for line_number, line in enumerate(args.worklist.read_text(encoding="utf-8-sig").splitlines(), 1):
        row = json.loads(line)
        source = row["source"]
        ids = WIKI_RE.findall(source)
        if not ids:
            continue
        rendered_source = WIKI_RE.sub(lambda m: f'<link="{m.group(1)}">{m.group(1)}</link>', source)

        def canonicalise(match: re.Match[str]) -> str:
            link_id = match.group("id")
            return f"[[{link_id}]]" if digest(link_id) in links else match.group(0)

        canonical = TMP_RE.sub(canonicalise, rendered_source)
        if canonical != source:
            errors.append(f"line {line_number} {row['id']}: canonical mismatch")
            continue
        target = catalog.get(digest(canonical))
        if target is None:
            errors.append(f"line {line_number} {row['id']}: catalog miss")
            continue

        target_labels = WIKI_RE.findall(target)
        if len(target_labels) != len(ids):
            errors.append(f"line {line_number} {row['id']}: target link count changed")
            continue
        link_index = 0

        def render_target(match: re.Match[str]) -> str:
            nonlocal link_index
            link_id = ids[link_index]
            link_index += 1
            return f'<link="{link_id}">{match.group(1)}</link>'

        rendered_target = WIKI_RE.sub(render_target, target)
        target_ids = [
            match.group("id")
            for match in TMP_RE.finditer(rendered_target)
            if digest(match.group("id")) in links
        ]
        if target_ids != ids:
            errors.append(f"line {line_number} {row['id']}: link IDs changed")
            continue
        if "[[" in rendered_target or "]]" in rendered_target:
            errors.append(f"line {line_number} {row['id']}: unrendered wiki link")
            continue
        checked += 1

    result = {"checked_linked_rows": checked, "errors": errors[:50], "error_count": len(errors)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
