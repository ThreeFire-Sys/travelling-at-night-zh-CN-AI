#!/usr/bin/env python3
"""Build a deterministic, reviewable QA findings ledger.

The ledger deliberately records observations but never decides that an
observation is acceptable.  Human dispositions live in a separate file and
are checked by ``validate_qa_dispositions.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
TOOL_VERSION = "1.0.0"
EVIDENCE_FIELDS = (
    "term",
    "fragments",
    "findings",
    "source_dash_count",
    "translation_dash_count",
)


def canonical_json(value: Any) -> bytes:
    """Return the one canonical representation used by every ledger hash."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def value_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_path(path: Path) -> str:
    """Prefer a repository-relative path so identical inputs yield identical meta."""
    resolved = path.resolve()
    repository = Path(__file__).resolve().parents[1]
    try:
        return resolved.relative_to(repository).as_posix()
    except ValueError:
        return resolved.as_posix()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON {path}: {exc}") from exc


def finding(
    *,
    suite: str,
    finding_key: str,
    severity: str,
    code: str,
    locator: dict[str, Any],
    source_report: str,
    observation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "suite": suite,
        "finding_key": finding_key,
        "observation_sha256": value_sha256(observation),
        "severity": severity,
        "code": code,
        "locator": locator,
        "source_report": source_report,
        "observation": observation,
    }


def structural_findings(report: Any, source_report: str) -> Iterable[dict[str, Any]]:
    if not isinstance(report, dict) or not isinstance(report.get("issues"), list):
        raise ValueError("structural report must be an object with an issues array")
    for issue in report["issues"]:
        if not isinstance(issue, dict):
            raise ValueError("structural issues must be objects")
        row_id = str(issue.get("id", ""))
        code = str(issue.get("code", ""))
        if not row_id or not code:
            raise ValueError("structural issue is missing id or code")
        yield finding(
            suite="structural",
            finding_key=f"structural|{row_id}|{code}",
            severity=str(issue.get("severity", "error")),
            code=code,
            locator={"id": row_id},
            source_report=source_report,
            observation=issue,
        )

    # These arrays describe structural failures outside the ordinary issues
    # array.  Keeping them in the ledger prevents a human-only gate from
    # accidentally overlooking them.
    array_codes = {
        "missing": "missing_translation",
        "unknown": "unknown_translation_id",
        "duplicate_ids": "duplicate_translation_id",
        "order_mismatches": "chunk_order_mismatch",
        "unmapped_link_targets": "unmapped_link_target",
    }
    for field, code in array_codes.items():
        values = report.get(field, [])
        if not isinstance(values, list):
            raise ValueError(f"structural report field {field!r} must be an array")
        for raw_locator in values:
            locator_value = str(raw_locator)
            observation = {"field": field, "value": raw_locator}
            yield finding(
                suite="structural",
                finding_key=f"structural|{locator_value}|{code}",
                severity="error",
                code=code,
                locator={"value": raw_locator},
                source_report=source_report,
                observation=observation,
            )


def consistency_findings(report: Any, source_report: str) -> Iterable[dict[str, Any]]:
    if not isinstance(report, dict) or not isinstance(report.get("issues"), list):
        raise ValueError("consistency report must be an object with an issues array")
    for issue in report["issues"]:
        if not isinstance(issue, dict):
            raise ValueError("consistency issues must be objects")
        row_id = str(issue.get("id", ""))
        code = str(issue.get("code", ""))
        if not code:
            raise ValueError("consistency issue is missing code")
        evidence = {key: issue[key] for key in EVIDENCE_FIELDS if key in issue}
        evidence_sha256 = value_sha256(evidence)
        context = issue.get("context") if isinstance(issue.get("context"), dict) else {}
        locator = {"id": row_id}
        if isinstance(issue.get("ids"), list):
            locator["ids"] = issue["ids"]
        for key in ("asset_file", "line", "field_path"):
            if key in context:
                locator[key] = context[key]
        yield finding(
            suite="consistency",
            finding_key=f"consistency|{row_id}|{code}|{evidence_sha256}",
            severity=str(issue.get("severity", "error")),
            code=code,
            locator=locator,
            source_report=source_report,
            observation=issue,
        )


def extraction_findings(report: Any, source_report: str) -> Iterable[dict[str, Any]]:
    if not isinstance(report, list):
        raise ValueError("extraction diagnostics must be an array")
    for diagnostic in report:
        if not isinstance(diagnostic, dict):
            raise ValueError("extraction diagnostics entries must be objects")
        if "summary" in diagnostic and "error" not in diagnostic:
            continue
        required = ("asset_file", "path_id", "script", "error")
        if any(key not in diagnostic for key in required):
            raise ValueError("extraction diagnostic is missing locator or error fields")
        asset_file = str(diagnostic["asset_file"])
        path_id = str(diagnostic["path_id"])
        script = str(diagnostic["script"])
        yield finding(
            suite="extraction",
            finding_key=f"extraction|{asset_file}|{path_id}|{script}",
            severity="warning",
            code="extraction_error",
            locator={
                "asset_file": diagnostic["asset_file"],
                "path_id": diagnostic["path_id"],
                "script": diagnostic["script"],
            },
            source_report=source_report,
            observation=diagnostic,
        )


def build_ledger(
    structural_path: Path,
    consistency_path: Path,
    extraction_path: Path,
    worklist_path: Path,
    catalog_path: Path,
    *,
    source_labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    paths = {
        "structural_report": structural_path,
        "consistency_report": consistency_path,
        "extraction_diagnostics": extraction_path,
        "worklist": worklist_path,
        "catalog": catalog_path,
    }
    labels = source_labels or {name: stable_path(path) for name, path in paths.items()}
    structural = load_json(structural_path)
    consistency = load_json(consistency_path)
    extraction = load_json(extraction_path)
    findings = [
        *structural_findings(structural, labels["structural_report"]),
        *consistency_findings(consistency, labels["consistency_report"]),
        *extraction_findings(extraction, labels["extraction_diagnostics"]),
    ]
    findings.sort(key=lambda row: (row["suite"], row["finding_key"]))
    keys = [row["finding_key"] for row in findings]
    if len(keys) != len(set(keys)):
        duplicates = sorted(key for key in set(keys) if keys.count(key) > 1)
        raise ValueError(f"duplicate finding keys: {duplicates}")
    counts: dict[str, int] = {"total": len(findings)}
    for suite in ("structural", "consistency", "extraction"):
        counts[suite] = sum(row["suite"] == suite for row in findings)
    return {
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "tool": "generate_qa_findings.py",
            "tool_version": TOOL_VERSION,
            "artifacts": {
                name: {"path": labels[name], "sha256": file_sha256(path)}
                for name, path in paths.items()
            },
            "counts": counts,
        },
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic release QA findings")
    parser.add_argument("--structural-report", type=Path, required=True)
    parser.add_argument("--consistency-report", type=Path, required=True)
    parser.add_argument("--extraction-diagnostics", type=Path, required=True)
    parser.add_argument("--worklist", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ledger = build_ledger(
        args.structural_report,
        args.consistency_report,
        args.extraction_diagnostics,
        args.worklist,
        args.catalog,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(ledger["meta"]["counts"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        raise SystemExit(1)
