#!/usr/bin/env python3
"""Strictly validate human dispositions against a generated QA ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ALLOWED_DECISIONS = {
    "accepted_expected",
    "false_positive",
    "covered_elsewhere",
    "pending_fix",
    "block",
}
BLOCKING_DECISIONS = {"pending_fix", "block"}
REQUIRED_FIELDS = {
    "finding_key",
    "observation_sha256",
    "decision",
    "category",
    "reason",
    "evidence",
    "reviewer",
    "reviewed_at",
    "game_build",
}
SHA256_RE = re.compile(r"[0-9a-f]{64}")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON {path}: {exc}") from exc


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def value_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_timestamp(value: Any) -> bool:
    if not nonempty_string(value):
        return False
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def validate(
    ledger: Any, dispositions_document: Any
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if not isinstance(ledger, dict) or ledger.get("schema_version") != 1:
        return {}, ["findings ledger must use schema_version 1"]
    findings = ledger.get("findings")
    if not isinstance(findings, list):
        return {}, ["findings ledger must contain a findings array"]
    finding_by_key: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(findings):
        if not isinstance(item, dict):
            errors.append(f"finding[{index}] is not an object")
            continue
        key = item.get("finding_key")
        observation_hash = item.get("observation_sha256")
        if not nonempty_string(key) or not isinstance(observation_hash, str) or not SHA256_RE.fullmatch(observation_hash):
            errors.append(f"finding[{index}] has an invalid key or observation hash")
            continue
        if "observation" not in item or value_sha256(item["observation"]) != observation_hash:
            errors.append(f"{key}: ledger observation_sha256 does not match observation")
        if key in finding_by_key:
            errors.append(f"duplicate finding key in ledger: {key}")
        finding_by_key[key] = item

    recorded_counts = ledger.get("meta", {}).get("counts") if isinstance(ledger.get("meta"), dict) else None
    actual_counts = Counter(
        item.get("suite", "unknown") for item in findings if isinstance(item, dict)
    )
    expected_counts = {
        "total": len(findings),
        "structural": actual_counts["structural"],
        "consistency": actual_counts["consistency"],
        "extraction": actual_counts["extraction"],
    }
    for suite, count in actual_counts.items():
        if suite not in expected_counts:
            expected_counts[suite] = count
    if recorded_counts != expected_counts:
        errors.append(
            f"ledger meta counts do not match findings: recorded={recorded_counts!r}, actual={expected_counts!r}"
        )

    if isinstance(dispositions_document, dict):
        if dispositions_document.get("schema_version") != 1:
            errors.append("dispositions document must use schema_version 1")
        dispositions = dispositions_document.get("dispositions")
    else:
        dispositions = dispositions_document
    if not isinstance(dispositions, list):
        return {}, errors + ["dispositions must be an array"]

    disposition_by_key: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(dispositions):
        prefix = f"disposition[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} is not an object")
            continue
        missing_fields = sorted(REQUIRED_FIELDS - item.keys())
        extra_fields = sorted(item.keys() - REQUIRED_FIELDS)
        if missing_fields:
            errors.append(f"{prefix} missing fields: {missing_fields}")
        if extra_fields:
            errors.append(f"{prefix} has unknown fields: {extra_fields}")
        key = item.get("finding_key")
        if not nonempty_string(key):
            errors.append(f"{prefix} has an invalid finding_key")
            continue
        if key in disposition_by_key:
            errors.append(f"duplicate disposition key: {key}")
        disposition_by_key[key] = item
        observation_hash = item.get("observation_sha256")
        if not isinstance(observation_hash, str) or not SHA256_RE.fullmatch(observation_hash):
            errors.append(f"{key}: observation_sha256 must be lowercase SHA-256")
        finding_row = finding_by_key.get(key)
        if finding_row is not None and observation_hash != finding_row["observation_sha256"]:
            errors.append(f"{key}: observation_sha256 does not match current finding")
        decision = item.get("decision")
        if decision not in ALLOWED_DECISIONS:
            errors.append(f"{key}: invalid decision {decision!r}")
        elif decision in BLOCKING_DECISIONS:
            errors.append(f"{key}: unresolved decision {decision!r} blocks release")
        for field in ("category", "reason", "reviewer", "game_build"):
            if not nonempty_string(item.get(field)):
                errors.append(f"{key}: {field} must be a non-empty string")
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence or any(
            not (
                (isinstance(value, str) and bool(value.strip()))
                or (isinstance(value, dict) and bool(value))
            )
            for value in evidence
        ):
            errors.append(f"{key}: evidence must be a non-empty array of non-empty values")
        if not validate_timestamp(item.get("reviewed_at")):
            errors.append(f"{key}: reviewed_at must be an ISO-8601 timestamp with timezone")

    finding_keys = set(finding_by_key)
    disposition_keys = set(disposition_by_key)
    missing = sorted(finding_keys - disposition_keys)
    extra = sorted(disposition_keys - finding_keys)
    if missing:
        errors.append(f"missing dispositions for {len(missing)} findings: {missing}")
    if extra:
        errors.append(f"dispositions reference {len(extra)} unknown findings: {extra}")

    decisions = Counter(
        item.get("decision") for item in disposition_by_key.values() if item.get("decision") in ALLOWED_DECISIONS
    )
    suites = Counter(
        finding_by_key[key].get("suite", "unknown")
        for key in disposition_by_key.keys() & finding_by_key.keys()
    )
    summary = {
        "schema_version": 1,
        "status": "ok" if not errors else "failed",
        "finding_count": len(finding_by_key),
        "disposition_count": len(disposition_by_key),
        "matched_count": len(finding_keys & disposition_keys),
        "missing_count": len(missing),
        "extra_count": len(extra),
        "error_count": len(errors),
        "by_suite": dict(sorted(suites.items())),
        "by_decision": dict(sorted(decisions.items())),
        "errors": errors,
    }
    return summary, errors


def markdown_summary(summary: dict[str, Any]) -> str:
    lines = [
        "# QA disposition validation",
        "",
        f"- Status: **{summary['status']}**",
        f"- Findings: {summary['finding_count']}",
        f"- Dispositions: {summary['disposition_count']}",
        f"- Matched: {summary['matched_count']}",
        f"- Missing / extra: {summary['missing_count']} / {summary['extra_count']}",
        f"- Validation errors: {summary['error_count']}",
        "",
        "## Decisions",
        "",
    ]
    if summary["by_decision"]:
        lines.extend(f"- `{key}`: {value}" for key, value in summary["by_decision"].items())
    else:
        lines.append("- None")
    lines.extend(["", "## Errors", ""])
    if summary["errors"]:
        lines.extend(f"- {error}" for error in summary["errors"])
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate human QA dispositions")
    parser.add_argument("--findings", type=Path, required=True)
    parser.add_argument("--dispositions", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()
    summary, errors = validate(load_json(args.findings), load_json(args.dispositions))
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.output_md.write_text(markdown_summary(summary), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "errors"}, ensure_ascii=False))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
