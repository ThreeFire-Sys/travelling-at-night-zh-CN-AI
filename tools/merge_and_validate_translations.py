#!/usr/bin/env python3
"""Merge agent translation chunks and run structural localization QA."""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any


TAG_RE = re.compile(r"<[^<>]+>")
FORMAT_RE = re.compile(r"(?<!\{)\{\d+(?::[^{}]+)?\}(?!\})")
QUERY_RE = re.compile(r"\[q=[^\]]+\]")
LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
ASCII_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z'’-]*\b")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("worklist", type=Path)
    parser.add_argument("translations_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument(
        "--link-targets",
        type=Path,
        help="可选的 [[link]] 固定译名 CSV；默认使用工作区 glossary/link_targets.csv",
    )
    parser.add_argument(
        "--supplement",
        type=Path,
        help="可选的运行时补充条目 CSV；默认使用工作区 glossary/runtime_supplement.csv",
    )
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def token_multiset(pattern: re.Pattern[str], value: str) -> collections.Counter[str]:
    return collections.Counter(pattern.findall(value))


def read_link_overrides(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            source = (row.get("source_en") or "").strip()
            target = (row.get("target_zh") or "").strip()
            if source and target:
                result[source] = target
    return result


def normalize_links(value: str, mapping: dict[str, str]) -> str:
    return LINK_RE.sub(lambda match: f"[[{mapping.get(match.group(1), match.group(1))}]]", value)


def source_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def utf16_length(value: str) -> int:
    """C# string.Length counts UTF-16 code units; keep the runtime contract."""
    return len(value.encode("utf-16-le")) // 2


TOKEN_RE = re.compile(r"(?:\[q=[^\]]+\]|(?<!\{)\{\d+(?::[^{}]+)?\}(?!\}))")


def build_query_patterns(merged: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fingerprinted [q=...] / {0} variable patterns for the runtime matcher.

    The game substitutes [q=...] tokens and {0} format arguments before the
    localisation boundaries see the text, so an exact source fingerprint can
    never match the rendered string.  Each pattern stores only per-literal-
    segment fingerprints (first and last char, UTF-16 length, SHA-256) plus
    the verbatim token texts and the reviewed translation, so no English
    prose ships in the payload.
    """
    patterns: dict[str, dict[str, Any]] = {}
    for entry in merged:
        source = entry["source"]
        translation = entry.get("translation", "")
        if not TOKEN_RE.search(source) or not translation.strip():
            continue
        if "[[" in source or "[[" in translation:
            # Link-bearing lines are handled by the canonical link path, where
            # authored link IDs can be restored for the game's resolver.
            continue
        segments = TOKEN_RE.split(source)
        tokens = [match.group(0) for match in TOKEN_RE.finditer(source)]
        # 中间的空段意味着相邻变量之间没有字面锚点，无法可靠切分捕获值。
        if any(not segment for segment in segments[1:-1]):
            continue
        if any(token not in translation for token in tokens):
            continue
        fingerprinted = [
            {
                "len": utf16_length(segment),
                "sha": source_hash(segment),
                "first": segment[:1],
                "last": segment[-1:],
            }
            for segment in segments
        ]
        patterns[source_hash(source)] = {
            "id": entry["id"],
            "segments": fingerprinted,
            "tokens": tokens,
            "translation": translation,
        }
    ordered = sorted(
        patterns.values(),
        key=lambda pattern: -sum(segment["len"] for segment in pattern["segments"]),
    )
    return ordered


def fold_link_labels(value: str) -> str:
    """游戏渲染 [[X]] 脚注链接后的可见形态：链接标记消失，只留标签文本。"""
    return LINK_RE.sub(lambda match: match.group(1), value)


def validate_pair(entry: dict[str, Any]) -> list[dict[str, str]]:
    source = entry["source"]
    target = entry["translation"]
    is_patch_notes = any(
        context.get("script") == "UnityEngine.TextAsset" and
        context.get("game_object") == "patch-notes"
        for context in entry.get("contexts", [])
    )
    issues: list[dict[str, str]] = []

    def error(code: str, detail: str) -> None:
        issues.append({"severity": "error", "code": code, "detail": detail})

    def warning(code: str, detail: str) -> None:
        issues.append({"severity": "warning", "code": code, "detail": detail})

    if not target.strip():
        error("empty_translation", "译文为空")
        return issues
    if token_multiset(TAG_RE, source) != token_multiset(TAG_RE, target):
        error("rich_text_mismatch", "TMP/富文本标签集合或属性发生变化")
    if token_multiset(FORMAT_RE, source) != token_multiset(FORMAT_RE, target):
        error("format_placeholder_mismatch", ".NET 格式占位符不一致")
    if token_multiset(QUERY_RE, source) != token_multiset(QUERY_RE, target):
        error("query_token_mismatch", "[q=...] 查询标记不一致")
    if not is_patch_notes and len(LINK_RE.findall(source)) != len(LINK_RE.findall(target)):
        error("footnote_link_count", "[[...]] 脚注链接数量不一致")
    if source.count("\n") != target.count("\n"):
        warning("newline_count", "换行数量发生变化，请确认是有意排版")
    if target == source and ASCII_WORD_RE.search(source):
        warning("unchanged", "译文与原文完全相同")
    if "�" in target:
        error("replacement_character", "译文含 Unicode 替换字符")
    source_link_balance = source.count("[[") - source.count("]]" )
    target_link_balance = target.count("[[") - target.count("]]" )
    reviewed_source_link_repair = (
        entry.get("id") == "TAN-39F83BAE9CB6" and
        source_link_balance == -1 and
        target_link_balance == 0
    )
    if (not is_patch_notes and
            target_link_balance != source_link_balance and
            not reviewed_source_link_repair):
        error("unbalanced_link", "译文改变了源文的脚注链接括号平衡")
    elif target_link_balance and not reviewed_source_link_repair:
        warning("source_unbalanced_link_preserved", "源文链接括号本就不平衡，译文已原样保留")
    return issues


def main() -> int:
    args = parse_args()
    worklist = read_jsonl(args.worklist)
    by_id = {entry["id"]: entry for entry in worklist}
    translated: dict[str, dict[str, Any]] = {}
    duplicate_ids: list[str] = []

    for path in sorted(args.translations_dir.glob("chunk_*.jsonl")):
        for row in read_jsonl(path):
            row_id = row.get("id", "")
            if row_id in translated:
                duplicate_ids.append(row_id)
            translated[row_id] = row

    missing = [entry["id"] for entry in worklist if entry["id"] not in translated]
    unknown = sorted(set(translated) - set(by_id))
    order_mismatches: list[str] = []
    for path in sorted(args.translations_dir.glob("chunk_*.jsonl")):
        source_path = args.worklist.parent / "chunks" / path.name
        if not source_path.exists():
            continue
        source_ids = [row["id"] for row in read_jsonl(source_path)]
        target_ids = [row["id"] for row in read_jsonl(path)]
        if source_ids != target_ids:
            order_mismatches.append(path.name)

    merged: list[dict[str, Any]] = []
    for source_entry in worklist:
        row = translated.get(source_entry["id"])
        if row is None:
            continue
        entry = dict(source_entry)
        entry["translation"] = row.get("translation", "")
        entry["status"] = row.get("status", "translated")
        entry["notes"] = row.get("notes", "")
        merged.append(entry)

    # Link text is both the visible label and Pixel Crushers' lookup key.  Build
    # the default map from translated standalone labels, then apply reviewed
    # overrides for aliases, plurals and deliberate lore spellings.
    link_mapping = {
        entry["source"]: entry["translation"]
        for entry in merged
        if "\n" not in entry["source"]
        and "\r" not in entry["source"]
        and "[[" not in entry["source"]
        and entry["translation"].strip()
    }
    workspace = args.worklist.resolve().parents[2]
    link_overrides_path = args.link_targets or workspace / "glossary" / "link_targets.csv"
    link_mapping.update(read_link_overrides(link_overrides_path))
    source_link_targets = sorted(
        {target for entry in merged for target in LINK_RE.findall(entry["source"])},
        key=str.casefold,
    )
    unmapped_link_targets = [target for target in source_link_targets if target not in link_mapping]
    for entry in merged:
        entry["translation"] = normalize_links(entry["translation"], link_mapping)

    issues: list[dict[str, Any]] = []
    for entry in merged:
        for issue in validate_pair(entry):
            issues.append({"id": entry["id"], "source": entry["source"], **issue})

    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "review_catalog.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for entry in merged:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    # The distributable catalog intentionally contains only source fingerprints,
    # not a copy of the game's English prose.
    catalog = {source_hash(entry["source"]): entry["translation"] for entry in merged}

    # Runtime supplement: alias presets, friendlyText labels and other strings
    # that never reached the translation worklist (reviewed in the open as
    # glossary/runtime_supplement.csv).  A supplement row may repeat a catalog
    # entry verbatim, but must never disagree with one.
    supplement_path = args.supplement or workspace / "glossary" / "runtime_supplement.csv"
    supplement = read_link_overrides(supplement_path)
    supplement_conflicts: list[str] = []
    for supp_source, supp_target in supplement.items():
        key = source_hash(supp_source)
        existing = catalog.get(key)
        if existing is not None:
            if existing != supp_target:
                supplement_conflicts.append(supp_source)
            continue
        catalog[key] = supp_target

    # Rendered-form variants.  The game trims authored padding and expands
    # [[links]] into visible labels before text reaches the localisation
    # boundaries, so the verbatim source fingerprint can never match those
    # rendered strings.  Variants only fill fingerprints the exact catalog
    # does not claim: an authored entry always outranks a derived one.
    blocked_variants: set[str] = set()

    def collect_variant(variants: dict[str, str], source: str, target: str) -> None:
        key = source_hash(source)
        if not source or not target or key in catalog or key in blocked_variants:
            return
        if key in variants and variants[key] != target:
            blocked_variants.add(key)
            del variants[key]
            return
        variants[key] = target

    trimmed_variants: dict[str, str] = {}
    folded_variants: dict[str, str] = {}
    for entry in merged:
        source, translation = entry["source"], entry["translation"]
        trimmed_source = source.strip()
        if trimmed_source != source:
            collect_variant(trimmed_variants, trimmed_source, translation.strip())
        if "[[" in source:
            folded_source = fold_link_labels(source)
            folded_target = fold_link_labels(translation)
            if folded_source != source and "[[" not in folded_target:
                collect_variant(folded_variants, folded_source, folded_target)
    trimmed_variant_count = 0
    folded_variant_count = 0
    for variants, counter in ((trimmed_variants, "trimmed"), (folded_variants, "folded")):
        for key, value in variants.items():
            if key in catalog or key in blocked_variants:
                continue
            catalog[key] = value
            if counter == "trimmed":
                trimmed_variant_count += 1
            else:
                folded_variant_count += 1

    (args.output_dir / "catalog.zh-CN.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    query_patterns = build_query_patterns(merged)
    (args.output_dir / "patterns.zh-CN.json").write_text(
        json.dumps(
            {"version": 1, "patterns": query_patterns},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    link_target_entries = {
        source_hash(target): link_mapping[target]
        for target in source_link_targets
        if target in link_mapping
    }
    # Supplement entries double as resolvable link IDs: the game renders some
    # labels (for example AxisQuality friendlyText) as <link> markup, and the
    # runtime canonicaliser only folds links whose ID is in this map.
    for supp_source, supp_target in supplement.items():
        if supp_source not in supplement_conflicts:
            link_target_entries.setdefault(source_hash(supp_source), supp_target)
    (args.output_dir / "link_targets.zh-CN.json").write_text(
        json.dumps(link_target_entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report = {
        "expected": len(worklist),
        "translated": len(merged),
        "missing": missing,
        "unknown": unknown,
        "duplicate_ids": duplicate_ids,
        "order_mismatches": order_mismatches,
        "link_target_count": len(source_link_targets),
        "unmapped_link_targets": unmapped_link_targets,
        "query_pattern_count": len(query_patterns),
        "supplement_count": len(supplement) - len(supplement_conflicts),
        "supplement_conflicts": supplement_conflicts,
        "trimmed_variant_count": trimmed_variant_count,
        "folded_variant_count": folded_variant_count,
        "errors": sum(issue["severity"] == "error" for issue in issues),
        "warnings": sum(issue["severity"] == "warning" for issue in issues),
        "issues": issues,
    }
    (args.output_dir / "qa_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in report.items() if key not in {"missing", "issues"}}, ensure_ascii=False, indent=2))
    print(f"Missing: {len(missing)}")
    if duplicate_ids or unknown or order_mismatches or unmapped_link_targets or report["errors"] or supplement_conflicts:
        return 1
    if missing and not args.allow_partial:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
