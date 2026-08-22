#!/usr/bin/env python3
"""Validate that the current consistency warning set is fully dispositioned."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def signature(issue: dict) -> str:
    value = "\0".join((issue.get("code", ""), issue.get("id", ""), issue.get("detail", "")))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def main() -> int:
    report = json.loads((ROOT / "build/merged_k97/consistency_report.json").read_text(encoding="utf-8-sig"))
    ledger = [
        json.loads(raw)
        for raw in (ROOT / "glossary/consistency_warning_audit.jsonl").read_text(
            encoding="utf-8-sig"
        ).splitlines()
        if raw
    ]
    by_signature = {row["signature"]: row for row in ledger}
    warnings = [issue for issue in report.get("issues", []) if issue.get("severity") != "error"]
    expected = {signature(issue) for issue in warnings}
    errors = []
    if len(by_signature) != len(ledger):
        errors.append("duplicate consistency warning signatures")
    if expected != set(by_signature):
        errors.append(
            f"warning disposition drift missing={sorted(expected-set(by_signature))[:20]} "
            f"obsolete={sorted(set(by_signature)-expected)[:20]}"
        )
    for issue in warnings:
        row = by_signature.get(signature(issue))
        if not row:
            continue
        if row.get("source") != issue.get("source") or row.get("translation") != issue.get("translation"):
            errors.append(f"{issue['id']}/{issue['code']}: warning text drift")
        if not row.get("decision") or len(str(row.get("audit_note", ""))) < 20:
            errors.append(f"{issue['id']}/{issue['code']}: incomplete warning disposition")
    print(json.dumps({"warnings": len(warnings), "ledger_rows": len(ledger), "errors": errors}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
