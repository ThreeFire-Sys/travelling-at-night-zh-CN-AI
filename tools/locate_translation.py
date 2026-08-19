#!/usr/bin/env python3
"""Locate a player-visible Chinese string by ID or screenshot transcription.

The tool indexes raw translations and their rendered [[link]] labels, then
returns the stable text ID together with English source and Unity/dialogue
context.  It is intentionally read-only and useful for screenshot-based QA.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any


LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
TAG_RE = re.compile(r"<[^<>]+>")
SPACE_RE = re.compile(r"\s+")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="?", help="Chinese fragment or stable TAN-* ID")
    parser.add_argument(
        "--worklist",
        type=Path,
        default=Path("build/worklist/worklist.jsonl"),
    )
    parser.add_argument("--translations", type=Path, default=Path("translations"))
    parser.add_argument(
        "--link-targets", type=Path, default=Path("glossary/link_targets.csv")
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.query:
        parser.error("provide a text fragment or TAN-* ID")
    if args.limit < 1:
        parser.error("--limit must be positive")
    return args


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def read_translations(path: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for chunk in sorted(path.glob("chunk_*.jsonl")):
        for row in read_jsonl(chunk):
            result[str(row["id"])] = row
    return result


def read_links(path: Path, rows: list[dict[str, Any]]) -> dict[str, str]:
    result = {
        str(row["source"]): str(row.get("translation", ""))
        for row in rows
        if "\n" not in str(row.get("source", ""))
        and "[[" not in str(row.get("source", ""))
        and str(row.get("translation", "")).strip()
    }
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                source = (row.get("source_en") or "").strip()
                target = (row.get("target_zh") or "").strip()
                if source and target:
                    result[source] = target
    return result


def render_links(value: str, links: dict[str, str]) -> str:
    return LINK_RE.sub(lambda match: links.get(match.group(1), match.group(1)), value)


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFC", value)
    value = TAG_RE.sub("", value)
    value = value.replace("[[", "").replace("]]", "")
    return SPACE_RE.sub("", value).strip().casefold()


def context_summary(row: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for context in row.get("contexts", [])[:3]:
        result.append(
            {
                key: context.get(key)
                for key in (
                    "domain",
                    "conversation",
                    "speaker",
                    "conversant",
                    "previous_text",
                    "next_text",
                    "game_object",
                    "field_path",
                    "scene",
                )
                if context.get(key) not in (None, "")
            }
        )
    return result


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    worklist = read_jsonl(args.worklist)
    translations = read_translations(args.translations)
    merged: list[dict[str, Any]] = []
    for source_row in worklist:
        row = dict(source_row)
        translated = translations.get(str(row["id"]), {})
        row["translation"] = translated.get("translation", "")
        row["notes"] = translated.get("notes", "")
        merged.append(row)
    links = read_links(args.link_targets, merged)

    query = args.query.strip()
    query_normalized = normalize(query)
    matches: list[tuple[float, dict[str, Any], str]] = []
    for row in merged:
        raw = str(row.get("translation", ""))
        rendered = render_links(raw, links)
        if query.casefold() == str(row["id"]).casefold():
            score = 4.0
        elif query_normalized and query_normalized == normalize(rendered):
            score = 3.0
        elif query_normalized and query_normalized in normalize(rendered):
            score = 2.0 + min(0.9, len(query_normalized) / max(1, len(normalize(rendered))))
        elif query_normalized and query_normalized in normalize(raw):
            score = 1.9
        else:
            ratio = difflib.SequenceMatcher(None, query_normalized, normalize(rendered)).ratio()
            if ratio < 0.32:
                continue
            score = ratio
        matches.append((score, row, rendered))

    matches.sort(key=lambda item: (-item[0], str(item[1]["id"])))
    payload = [
        {
            "score": round(score, 4),
            "id": row["id"],
            "domain": row.get("domain", ""),
            "source": row.get("source", ""),
            "translation_raw": row.get("translation", ""),
            "translation_rendered": rendered,
            "notes": row.get("notes", ""),
            "contexts": context_summary(row),
        }
        for score, row, rendered in matches[: args.limit]
    ]
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for item in payload:
            print(f"[{item['score']:.4f}] {item['id']} ({item['domain']})")
            print(f"  EN: {item['source']}")
            print(f"  ZH: {item['translation_rendered']}")
            for context in item["contexts"]:
                print(f"  CTX: {json.dumps(context, ensure_ascii=False)}")
    return 0 if payload else 1


if __name__ == "__main__":
    raise SystemExit(main())
