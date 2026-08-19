#!/usr/bin/env python3
"""Safely apply reviewed localization recommendations by stable text ID.

The command is dry-run by default.  It refuses stale recommendations and any
change to source text, links, rich-text tags, placeholders, newlines or outer
whitespace.  This keeps literary review separate from structural mutation and
prevents character-level patches from drifting across JSONL rows.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable


TAG_RE = re.compile(r"<[^<>]+>")
FORMAT_RE = re.compile(r"(?<!\{)\{\d+(?::[^{}]+)?\}(?!\})")
QUERY_RE = re.compile(r"\[q=[^\]]+\]")
LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


class ReviewApplyError(RuntimeError):
    """Raised when a recommendation cannot be applied without ambiguity."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("translations_dir", type=Path)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write validated recommendations in place; otherwise dry-run",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("build/reviews/ultimate_apply_manifest.json"),
        help="Audit manifest written when --apply succeeds",
    )
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ReviewApplyError(
                    f"{path}:{line_number}: invalid JSON: {exc.msg}"
                ) from exc
            if not isinstance(value, dict):
                raise ReviewApplyError(f"{path}:{line_number}: expected object")
            value["_report_path"] = str(path)
            value["_report_line"] = line_number
            result.append(value)
    return result


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def counter(pattern: re.Pattern[str], value: str) -> collections.Counter[str]:
    return collections.Counter(pattern.findall(value))


def outer_whitespace(value: str) -> tuple[str, str]:
    leading = re.match(r"^\s*", value)
    trailing = re.search(r"\s*$", value)
    return (
        leading.group(0) if leading else "",
        trailing.group(0) if trailing else "",
    )


def validate_structure(
    row_id: str, source: str, current: str, recommended: str
) -> list[str]:
    issues: list[str] = []
    checks: Iterable[tuple[str, re.Pattern[str]]] = (
        ("rich-text tags", TAG_RE),
        ("format placeholders", FORMAT_RE),
        ("query tokens", QUERY_RE),
    )
    for label, pattern in checks:
        if counter(pattern, current) != counter(pattern, recommended):
            issues.append(f"{label} changed")
        if counter(pattern, source) != counter(pattern, recommended):
            issues.append(f"{label} no longer matches source")

    source_links = collections.Counter(LINK_RE.findall(source))
    current_links = collections.Counter(LINK_RE.findall(current))
    recommended_links = collections.Counter(LINK_RE.findall(recommended))
    if current_links != recommended_links:
        issues.append("[[...]] link targets changed from current translation")
    if source_links != recommended_links:
        issues.append("[[...]] link targets differ from source")

    for token, label in (("\n", "LF"), ("\r", "CR"), ("\t", "tab")):
        if current.count(token) != recommended.count(token):
            issues.append(f"{label} count changed")
    for token, label in (("[", "opening square bracket"), ("]", "closing square bracket")):
        if current.count(token) != recommended.count(token):
            issues.append(f"{label} count changed")
    if outer_whitespace(current) != outer_whitespace(recommended):
        issues.append("leading/trailing whitespace changed")
    if "�" in recommended:
        issues.append("Unicode replacement character introduced")
    if not recommended.strip():
        issues.append("recommended translation is empty")
    return [f"{row_id}: {issue}" for issue in issues]


def load_translations(
    translations_dir: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, Path], list[Path]]:
    rows: dict[str, dict[str, Any]] = {}
    owners: dict[str, Path] = {}
    paths = sorted(translations_dir.glob("chunk_*.jsonl"))
    if not paths:
        raise ReviewApplyError(f"no chunk_*.jsonl in {translations_dir}")
    for path in paths:
        for row in read_jsonl(path):
            row.pop("_report_path", None)
            row.pop("_report_line", None)
            row_id = str(row.get("id", ""))
            if not row_id:
                raise ReviewApplyError(f"{path}: translation row missing id")
            if row_id in rows:
                raise ReviewApplyError(f"duplicate translation id: {row_id}")
            rows[row_id] = row
            owners[row_id] = path
    return rows, owners, paths


def collect_recommendations(
    reports: list[Path], translations: dict[str, dict[str, Any]]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    recommendations: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for report in reports:
        for finding in read_jsonl(report):
            row_id = str(finding.get("id", ""))
            source = finding.get("source")
            current = finding.get("current")
            recommended = finding.get("recommended")
            location = f"{finding['_report_path']}:{finding['_report_line']}"
            if not row_id or not all(
                isinstance(value, str) for value in (source, current, recommended)
            ):
                errors.append(f"{location}: missing id/source/current/recommended")
                continue
            if row_id not in translations:
                errors.append(f"{location}: unknown id {row_id}")
                continue
            translation = translations[row_id]
            if source != translation.get("source"):
                errors.append(f"{location}: stale or altered source for {row_id}")
            if current != translation.get("translation"):
                errors.append(f"{location}: stale current translation for {row_id}")
            if recommended == current:
                errors.append(f"{location}: recommendation does not change {row_id}")
            errors.extend(validate_structure(row_id, source, current, recommended))
            previous = recommendations.get(row_id)
            if previous is not None and previous["recommended"] != recommended:
                errors.append(
                    f"{location}: conflicting recommendations for {row_id}"
                )
            else:
                finding.pop("_report_path", None)
                finding.pop("_report_line", None)
                finding["report"] = str(report)
                recommendations[row_id] = finding
    return recommendations, errors


def apply_files(
    paths: list[Path], recommendations: dict[str, dict[str, Any]], manifest: Path
) -> None:
    before_hashes = {str(path): sha256_bytes(path.read_bytes()) for path in paths}
    changed_files: list[str] = []
    for path in paths:
        raw_lines = path.read_text(encoding="utf-8-sig").splitlines(keepends=True)
        output: list[str] = []
        touched = False
        for line in raw_lines:
            ending = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")
            body = line[: -len(ending)] if ending else line
            row = json.loads(body)
            finding = recommendations.get(str(row.get("id", "")))
            if finding is not None:
                row["translation"] = finding["recommended"]
                body = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
                touched = True
            output.append(body + ending)
        if not touched:
            continue
        temporary = path.with_name(path.name + ".ultimate-review.tmp")
        temporary.write_text("".join(output), encoding="utf-8", newline="")
        # Parse the complete replacement before the atomic swap.
        read_jsonl(temporary)
        os.replace(temporary, path)
        changed_files.append(str(path))

    after_hashes = {str(path): sha256_bytes(path.read_bytes()) for path in paths}
    payload = {
        "applied_count": len(recommendations),
        "applied_ids": sorted(recommendations),
        "changed_files": changed_files,
        "reports": sorted({value["report"] for value in recommendations.values()}),
        "before_sha256": before_hashes,
        "after_sha256": after_hashes,
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> int:
    args = parse_args()
    translations, _owners, paths = load_translations(args.translations_dir)
    recommendations, errors = collect_recommendations(args.reports, translations)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print(f"Rejected: {len(errors)} issue(s)")
        return 1
    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "dry-run",
                "translation_rows": len(translations),
                "recommendations": len(recommendations),
                "reports": [str(path) for path in args.reports],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.apply:
        apply_files(paths, recommendations, args.manifest)
        print(f"Manifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
