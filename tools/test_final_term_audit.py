#!/usr/bin/env python3
"""Validate the one-verdict-per-concept terminology final-audit ledger."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORIGINS = ("predecessor", "travelling_new", "real_world", "editorial")
ALLOWED_BASIS = {
    "predecessor_official_same_id",
    "predecessor_official_corpus",
    "same_game_official_zh",
    "external_authority",
    "explicit_editorial_policy",
    "editorial_transliteration",
    "language_or_professional_reference",
    "current_asset_semantics",
    "retired_not_in_current_assets",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--translations", type=Path, default=None, help=argparse.SUPPRESS)
    parser.parse_args()
    ledger_path = ROOT / "glossary/final_term_audit.jsonl"
    glossary_path = ROOT / "glossary/glossary.csv"
    provenance_dir = ROOT / "glossary/provenance"

    ledger = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8-sig").splitlines() if line]
    with glossary_path.open("r", encoding="utf-8-sig", newline="") as handle:
        glossary = {row["source_en"]: row for row in csv.DictReader(handle)}

    active: dict[str, dict] = {}
    aliases: dict[str, str] = {}
    for origin in ORIGINS:
        path = provenance_dir / f"{origin}.jsonl"
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            if not raw:
                continue
            row = json.loads(raw)
            canonical = row["canonical"]
            row["origin"] = origin
            active[canonical] = row
            for alias in row.get("aliases", []):
                aliases[alias] = canonical

    errors = []
    seen = Counter(row.get("canonical") for row in ledger)
    for canonical, count in seen.items():
        if count != 1:
            errors.append(f"ledger canonical count {count}: {canonical!r}")
    if len(ledger) != 350:
        errors.append(f"expected 350 historical audit verdicts, found {len(ledger)}")

    ledger_by_term = {row["canonical"]: row for row in ledger}
    for canonical, row in ledger_by_term.items():
        decision = row.get("decision")
        if decision not in {"keep", "change", "retire"}:
            errors.append(f"{canonical}: invalid decision {decision!r}")
        if row.get("basis") not in ALLOWED_BASIS:
            errors.append(f"{canonical}: invalid basis {row.get('basis')!r}")
        if row.get("confidence") not in {"fixed", "strong", "editorial"}:
            errors.append(f"{canonical}: invalid confidence {row.get('confidence')!r}")
        if not row.get("evidence_locators"):
            errors.append(f"{canonical}: missing evidence locators")
        if len(str(row.get("audit_note", ""))) < 20:
            errors.append(f"{canonical}: audit note too short")
        if row.get("reviewed_at") != "2026-08-22":
            errors.append(f"{canonical}: missing final review date")

        if decision == "retire":
            if canonical in active or canonical in glossary:
                errors.append(f"{canonical}: retired concept remains active")
            if row.get("target_final") is not None:
                errors.append(f"{canonical}: retired concept has a final target")
            continue

        reference_url = active.get(canonical, {}).get("reference_url")
        if reference_url and reference_url not in row.get("evidence_locators", []):
            errors.append(f"{canonical}: active provenance URL missing from evidence locators")

        record = active.get(canonical)
        if record is None:
            errors.append(f"{canonical}: audited active concept missing provenance")
            continue
        if record["origin"] != row.get("origin"):
            errors.append(f"{canonical}: origin drift")
        target = glossary.get(canonical, {}).get("target_zh")
        if target != row.get("target_final"):
            errors.append(
                f"{canonical}: final target mismatch {target!r} != {row.get('target_final')!r}"
            )
        if decision == "keep" and row.get("target_before") != row.get("target_final"):
            errors.append(f"{canonical}: keep verdict changes target")
        if decision == "change" and row.get("target_before") == row.get("target_final"):
            errors.append(f"{canonical}: change verdict is a no-op")

        expected_aliases = row.get("alias_targets_final", {})
        if set(record.get("aliases", [])) != set(expected_aliases):
            errors.append(
                f"{canonical}: alias set mismatch {record.get('aliases', [])!r} != "
                f"{sorted(expected_aliases)!r}"
            )
        for alias, expected in expected_aliases.items():
            actual = glossary.get(alias, {}).get("target_zh")
            if actual != expected:
                errors.append(f"{canonical}/{alias}: alias target {actual!r} != {expected!r}")

    for canonical in active:
        if canonical not in ledger_by_term:
            errors.append(f"active concept lacks final verdict: {canonical}")
    for term in glossary:
        if term not in active and term not in aliases:
            errors.append(f"glossary term is neither canonical nor alias: {term}")

    summary = {
        "historical_verdicts": len(ledger),
        "active_concepts": len(active),
        "retired_concepts": sum(row.get("decision") == "retire" for row in ledger),
        "decisions": dict(Counter(row.get("decision") for row in ledger)),
        "basis": dict(Counter(row.get("basis") for row in ledger)),
        "confidence": dict(Counter(row.get("confidence") for row in ledger)),
        "errors": errors,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
