#!/usr/bin/env python3
"""Apply the post-v1.2.4 terminology decisions to a copied j.33 catalog.

The v1.2.4 release translations remain an immutable baseline.  This script
copies that directory and applies only the manually reviewed terminology
delta recovered from the newer glossary/provenance pass.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


RULES: tuple[tuple[str, str, frozenset[str]], ...] = (
    (
        "海梅",
        "豪梅",
        frozenset(
            {
                "TAN-00080AC200DD", "TAN-107956B5060C", "TAN-145B63E294CC",
                "TAN-14BEF4D0A4DD", "TAN-164B3D0D7864", "TAN-1EAA8EE64164",
                "TAN-3482145EAE63", "TAN-423A39E845FE", "TAN-44442E3EDADB",
                "TAN-4AA3BB104298", "TAN-4E289908527C", "TAN-507FB862815E",
                "TAN-6657B632D0D5", "TAN-75404571E1F7", "TAN-769ADFC99286",
                "TAN-812905C673D4", "TAN-833B90064EEA", "TAN-A465F1FAE4A7",
                "TAN-AD2FC598762C", "TAN-ADD87CBCC5CF", "TAN-B26BD8B5DC1E",
                "TAN-B5C8373893F5", "TAN-B8072FF91AD8", "TAN-C5187E16DC46",
                "TAN-CB225B570206", "TAN-CC6906F9F547", "TAN-DC09742B338A",
                "TAN-EC2F66312420",
            }
        ),
    ),
    (
        "本体秘理",
        "本体梦理学",
        frozenset({"TAN-7FF6D750C9DC"}),
    ),
    (
        "本体秘理",
        "本体梦理",
        frozenset(
            {
                "TAN-010DBD1273B6", "TAN-01C33D98765B", "TAN-44442E3EDADB",
                "TAN-4B341F867B4E", "TAN-5C0580E48A0A", "TAN-7A309482D3E6",
                "TAN-7A56B4AA8507", "TAN-ADA6E9F599C6",
                "TAN-DA69B6FF4259", "TAN-DF25957F7240", "TAN-EAEDB7C9F263",
            }
        ),
    ),
    (
        "神链",
        "序链",
        frozenset(
            {
                "TAN-39E250445C87", "TAN-78BB922FB4F3", "TAN-8FA0F60408A7",
                "TAN-9BB1AA0EDBD3", "TAN-C42668E11016",
            }
        ),
    ),
    (
        "瞳中扉",
        "瞳中之扉",
        frozenset({"TAN-7246B23C834F", "TAN-A0875E0DEA7F"}),
    ),
    (
        "一元体",
        "一者",
        frozenset({"TAN-8B6BD21577F8", "TAN-96C181AC014A", "TAN-9BB1AA0EDBD3"}),
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    if not args.baseline.is_dir():
        raise SystemExit(f"baseline is not a directory: {args.baseline}")
    if args.output.exists():
        raise SystemExit(f"output already exists: {args.output}")
    shutil.copytree(args.baseline, args.output)

    expected_ids = set().union(*(ids for _, _, ids in RULES))
    seen_ids: set[str] = set()
    changes: list[dict[str, str]] = []

    for path in sorted(args.output.glob("chunk_*.jsonl")):
        rows = []
        changed = False
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            row = json.loads(line)
            row_id = str(row["id"])
            translation = str(row["translation"])
            for old, new, ids in RULES:
                if row_id not in ids:
                    continue
                if old not in translation:
                    raise RuntimeError(f"{row_id}: expected {old!r} in baseline translation")
                before = translation
                translation = translation.replace(old, new)
                changes.append(
                    {"id": row_id, "old": old, "new": new, "before": before, "after": translation}
                )
                seen_ids.add(row_id)
                changed = True
            if translation != row["translation"]:
                row["translation"] = translation
                suffix = "v1.2.5 术语终审：依最新版术语证据统一。"
                row["notes"] = (str(row.get("notes", "")).rstrip() + " " + suffix).strip()
            rows.append(row)
        if changed:
            path.write_text(
                "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
                encoding="utf-8",
                newline="\n",
            )

    if seen_ids != expected_ids:
        missing = sorted(expected_ids - seen_ids)
        extra = sorted(seen_ids - expected_ids)
        raise RuntimeError(f"term-update ID mismatch: missing={missing} extra={extra}")

    ledger = args.output / "v125_term_update_ledger.json"
    ledger.write_text(
        json.dumps(
            {
                "baseline": str(args.baseline),
                "unique_ids": len(seen_ids),
                "replacements": len(changes),
                "changes": changes,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"unique_ids": len(seen_ids), "replacements": len(changes)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
