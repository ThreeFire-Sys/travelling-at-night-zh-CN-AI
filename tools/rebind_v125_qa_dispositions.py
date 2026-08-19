#!/usr/bin/env python3
"""Re-review and rebind the four QA observations changed by v1.2.5."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


TARGETS = {
    ("TAN-44442E3EDADB", "english_residue"),
    ("TAN-44442E3EDADB", "fixed_term_missing"),
    ("TAN-44442E3EDADB", "mixed_punctuation"),
    ("TAN-8FA0F60408A7", "fixed_term_missing"),
}


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def excerpt(text: str, limit: int = 220) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--findings", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    findings_doc = json.loads(args.findings.read_text(encoding="utf-8"))
    baseline_doc = json.loads(args.baseline.read_text(encoding="utf-8"))
    catalog = {
        row["id"]: row
        for row in (
            json.loads(line)
            for line in args.catalog.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }

    current: dict[tuple[str, str], dict[str, Any]] = {}
    for finding in findings_doc["findings"]:
        locator = finding.get("locator") or {}
        key = (str(locator.get("id", "")), str(finding.get("code", "")))
        if key in TARGETS:
            if key in current:
                raise RuntimeError(f"duplicate current target finding: {key}")
            current[key] = finding
    if set(current) != TARGETS:
        raise RuntimeError(f"current target mismatch: missing={sorted(TARGETS-set(current))}")

    updated: set[tuple[str, str]] = set()
    reviewed_at = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    for disposition in baseline_doc["dispositions"]:
        parts = str(disposition.get("finding_key", "")).split("|")
        if len(parts) < 3:
            continue
        key = (parts[1], parts[2])
        if key not in TARGETS:
            continue
        finding = current[key]
        observation = finding["observation"]
        row = catalog[key[0]]

        disposition["finding_key"] = finding["finding_key"]
        disposition["observation_sha256"] = finding["observation_sha256"]
        disposition["reviewer"] = "Codex QA（v1.2.5 术语增量人工复核）"
        disposition["reviewed_at"] = reviewed_at

        if key == ("TAN-8FA0F60408A7", "fixed_term_missing"):
            disposition["reason"] = (
                "人工复核 TAN-8FA0F60408A7：seirai 已依最新版术语表统一为“序链”；"
                "本句“沿各自的序链”是复数语义下的自然中文语法变形，审计器只因未出现"
                "孤立字符串“诸序链”而误报。"
            )

        for evidence in disposition.get("evidence", []):
            if "source_report" in evidence:
                evidence["source_report"] = finding["source_report"]
                evidence["locator"] = finding["locator"]
                evidence["code"] = finding["code"]
                evidence["observation_sha256"] = finding["observation_sha256"]
            if "review_catalog" in evidence:
                evidence["review_catalog"] = str(args.catalog).replace("\\", "/")
                evidence["notes"] = row.get("notes", "")
            if "translation_sha256" in evidence:
                source = str(observation.get("source", ""))
                translation = str(observation.get("translation", ""))
                evidence["source_excerpt"] = excerpt(source)
                evidence["source_sha256"] = sha256(source)
                evidence["translation_excerpt"] = excerpt(translation)
                evidence["translation_sha256"] = sha256(translation)
            for name in ("fragments", "findings", "term"):
                if name in evidence and name in observation:
                    evidence[name] = observation[name]
        updated.add(key)

    if updated != TARGETS:
        raise RuntimeError(f"baseline target mismatch: missing={sorted(TARGETS-updated)}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(baseline_doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"updated_dispositions": len(updated)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
