#!/usr/bin/env python3
"""Close the player-option review with an auditable disposition per graph node."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


AMBIGUOUS_SHORT = re.compile(
    r"\b(?:leave|go|stay|yes|no|later|back|withdraw|get\s+out|until\s+then)\b",
    re.IGNORECASE,
)

REVISED_TRANSLATION_IDS = {
    "TAN-2B5F13FB5E90", "TAN-B42A524F0C82", "TAN-5469721A67C3",
    "TAN-72A62978AB8D", "TAN-09746E5EAE79", "TAN-CEF9C350D69A",
    "TAN-1DEEDDE42112", "TAN-5E2F46203987", "TAN-F3F27DA1E47C",
    "TAN-625518153F4B", "TAN-E8EF886DEF6D", "TAN-823BEB3E8A28",
    "TAN-8BE91AC2B47E", "TAN-C911E25C78BC", "TAN-B75A197DABD1",
    "TAN-CE1CF5947773", "TAN-02866E306BC3", "TAN-8690166785B9",
    "TAN-8CBB8B50F138", "TAN-C0DDDE301A49", "TAN-E7936849086E",
    "TAN-EEEDFB025249", "TAN-96438CB20557", "TAN-7A0E132B3C00",
    "TAN-90AA951048A1",
}


def load_catalog(directory: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for path in sorted(directory.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if line:
                row = json.loads(line)
                rows[row["id"]] = row
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("build/reviews/player_option_context_review_j46_reviewed.json"),
    )
    parser.add_argument(
        "--translations",
        type=Path,
        default=Path("build/translations_j46_candidate"),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("build/reviews/player_option_dispositions_j46.json"),
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("build/reviews/player_option_dispositions_j46.csv"),
    )
    args = parser.parse_args()

    review = json.loads(args.input.read_text(encoding="utf-8-sig"))
    catalog = load_catalog(args.translations)
    dispositions = []
    unresolved = []

    for node in review["options"]:
        option = node["option"]
        source = option["source"]
        ids = option.get("translation_ids", [])
        current_rows = [catalog[row_id] for row_id in ids if row_id in catalog]
        current_targets = {row["translation"] for row in current_rows}
        is_ambiguous_short = bool(AMBIGUOUS_SHORT.search(source))
        has_real_incoming = bool(node.get("parents"))
        has_real_outgoing = bool(node.get("successors"))
        contextual = bool(node.get("risk_score", 0)) or is_ambiguous_short
        revised = any(row_id in REVISED_TRANSLATION_IDS for row_id in ids)

        reasons = []
        if option.get("translation_required") and not current_rows:
            reasons.append("missing_current_translation_row")
        if option.get("translation_required") and len(current_targets) != 1:
            reasons.append("non_unique_current_translation")
        if is_ambiguous_short and not has_real_incoming:
            reasons.append("ambiguous_short_without_incoming_edge")

        disposition = {
            "conversation_id": node["conversation_id"],
            "conversation_title": node["conversation_title"],
            "entry_id": node["entry_id"],
            "entry_index": node["entry_index"],
            "source": source,
            "translation": next(iter(current_targets), option.get("translation", "")),
            "translation_ids": ids,
            "risk_score": node.get("risk_score", 0),
            "ambiguous_short_focus": is_ambiguous_short,
            "incoming_edge_count": len(node.get("parents", [])),
            "outgoing_edge_count": len(node.get("successors", [])),
            "review_basis": "real_edge_context" if contextual else "self_contained_option",
            "disposition": "revised" if revised else "accepted",
            "status": "unresolved" if reasons else "reviewed",
            "unresolved_reasons": reasons,
        }
        dispositions.append(disposition)
        if reasons:
            unresolved.append(disposition)

    summary = {
        "total_option_nodes": len(dispositions),
        "unique_option_sources": len({row["source"] for row in dispositions}),
        "reviewed": sum(row["status"] == "reviewed" for row in dispositions),
        "real_edge_context_reviewed": sum(row["review_basis"] == "real_edge_context" for row in dispositions),
        "self_contained_reviewed": sum(row["review_basis"] == "self_contained_option" for row in dispositions),
        "ambiguous_short_focus_nodes": sum(row["ambiguous_short_focus"] for row in dispositions),
        "revised_nodes": sum(row["disposition"] == "revised" for row in dispositions),
        "unresolved": len(unresolved),
    }
    result = {
        "tool": "build_player_option_dispositions.py",
        "schema_version": 1,
        "summary": summary,
        "options": dispositions,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with args.output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        fields = [
            "conversation_id", "conversation_title", "entry_id", "entry_index",
            "source", "translation", "risk_score", "ambiguous_short_focus",
            "incoming_edge_count", "outgoing_edge_count", "review_basis",
            "disposition", "status", "translation_ids", "unresolved_reasons",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in dispositions:
            flat = dict(row)
            flat["translation_ids"] = ";".join(row["translation_ids"])
            flat["unresolved_reasons"] = ";".join(row["unresolved_reasons"])
            writer.writerow({field: flat[field] for field in fields})

    print(json.dumps(summary, ensure_ascii=False))
    return 1 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
