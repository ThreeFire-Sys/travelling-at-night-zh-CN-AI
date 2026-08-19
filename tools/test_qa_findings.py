#!/usr/bin/env python3
"""Tests for the deterministic QA findings/disposition gate."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = load_module("generate_qa_findings", "generate_qa_findings.py")
validator = load_module("validate_qa_dispositions", "validate_qa_dispositions.py")


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class QaFindingsTests(unittest.TestCase):
    def make_ledger(self, directory: Path):
        structural = directory / "qa.json"
        consistency = directory / "consistency.json"
        extraction = directory / "diagnostics.json"
        worklist = directory / "worklist.jsonl"
        catalog = directory / "catalog.json"
        write_json(structural, {"issues": [{"id": "TAN-1", "code": "unchanged", "severity": "warning", "source": "X"}], "missing": [], "unknown": [], "duplicate_ids": [], "order_mismatches": [], "unmapped_link_targets": []})
        write_json(consistency, {"issues": [{"id": "TAN-2", "code": "mixed_punctuation", "severity": "warning", "term": "dash", "findings": ["one"]}]})
        write_json(extraction, [{"asset_file": "level1", "path_id": 7, "script": "Example", "error": "parse"}, {"summary": {"rows": 1}}])
        worklist.write_text('{"id":"TAN-1","source":"X"}\n', encoding="utf-8")
        write_json(catalog, {"abc": "译文"})
        paths = (structural, consistency, extraction, worklist, catalog)
        return generator.build_ledger(*paths, source_labels={"structural_report": "qa.json", "consistency_report": "consistency.json", "extraction_diagnostics": "diagnostics.json", "worklist": "worklist.jsonl", "catalog": "catalog.json"})

    def test_generator_is_deterministic_and_builds_all_suites(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            first = self.make_ledger(directory)
            second = self.make_ledger(directory)
        self.assertEqual(first, second)
        self.assertEqual(first["meta"]["counts"], {"total": 3, "structural": 1, "consistency": 1, "extraction": 1})
        consistency = next(row for row in first["findings"] if row["suite"] == "consistency")
        self.assertRegex(consistency["finding_key"], r"^consistency\|TAN-2\|mixed_punctuation\|[0-9a-f]{64}$")

    def dispositions_for(self, ledger):
        return {
            "schema_version": 1,
            "dispositions": [
                {
                    "finding_key": item["finding_key"],
                    "observation_sha256": item["observation_sha256"],
                    "decision": "accepted_expected",
                    "category": "test fixture",
                    "reason": "Manually inspected and expected for this fixture.",
                    "evidence": ["fixture review record"],
                    "reviewer": "QA Tester",
                    "reviewed_at": "2026-08-14T08:00:00+08:00",
                    "game_build": "demo-test",
                }
                for item in ledger["findings"]
            ],
        }

    def test_complete_review_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = self.make_ledger(Path(temporary))
        summary, errors = validator.validate(ledger, self.dispositions_for(ledger))
        self.assertEqual(errors, [])
        self.assertEqual(summary["status"], "ok")

    def test_tampered_ledger_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = self.make_ledger(Path(temporary))
        document = self.dispositions_for(ledger)
        ledger["findings"][0]["observation"]["source"] = "tampered"
        _, errors = validator.validate(ledger, document)
        self.assertTrue(any("ledger observation_sha256" in error for error in errors))

    def test_hash_mismatch_and_pending_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = self.make_ledger(Path(temporary))
        document = self.dispositions_for(ledger)
        document["dispositions"][0]["observation_sha256"] = "0" * 64
        document["dispositions"][1]["decision"] = "pending_fix"
        summary, errors = validator.validate(ledger, document)
        self.assertEqual(summary["status"], "failed")
        self.assertTrue(any("does not match" in error for error in errors))
        self.assertTrue(any("blocks release" in error for error in errors))

    def test_set_must_match_and_evidence_is_mandatory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = self.make_ledger(Path(temporary))
        document = self.dispositions_for(ledger)
        document["dispositions"][0]["evidence"] = []
        document["dispositions"].pop()
        document["dispositions"].append({**document["dispositions"][0], "finding_key": "unknown|key"})
        _, errors = validator.validate(ledger, document)
        self.assertTrue(any("evidence must" in error for error in errors))
        self.assertTrue(any("missing dispositions" in error for error in errors))
        self.assertTrue(any("unknown findings" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
