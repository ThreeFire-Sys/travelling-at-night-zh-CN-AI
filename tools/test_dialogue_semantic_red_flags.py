"""Guard source-side semantic traps that structural QA cannot detect.

These checks deliberately key off the English meaning first.  They prevent a
translation from being accepted merely because it is fluent Chinese, has the
right punctuation, and preserves all markup while changing the speaker's job,
an idiom, or the natural relationship between adjoining fragments.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_rows(path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for chunk in sorted(path.glob("chunk_*.jsonl")):
        for line in chunk.read_text(encoding="utf-8-sig").splitlines():
            row = json.loads(line)
            rows[row["id"]] = row
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--translations",
        type=Path,
        default=ROOT / "build" / "translations_j66_candidate",
    )
    args = parser.parse_args()
    rows = load_rows(args.translations)
    errors: list[str] = []

    private_agents = [
        row for row in rows.values() if "private inquiry agent" in row.get("source", "")
    ]
    if len(private_agents) != 3:
        errors.append(f"expected 3 private-inquiry-agent rows, found {len(private_agents)}")
    for row in private_agents:
        target = row.get("translation", "")
        if "私家侦探" not in target or "私人调查" in target or "私家调查员" in target:
            errors.append(
                f"{row['id']}: private inquiry agent is a profession and must be 私家侦探"
            )

    expected = {
        "TAN-E0E811B7B0EF": "不知我能否为民兵团效劳？我当过私家侦探。",
        "TAN-3A5C49114B56": "幸会，先生。不过，您还没告诉我该如何称呼。",
        "TAN-D125BC33B4CD": "我在找一个人——一位女士。",
        "TAN-1684CDF0CC08": "我也在找人。一位女士，[[Nina Lagasse]]。",
        "TAN-0C50B1CB110C": "我在找一位女士——[[Nina Lagasse]]。",
        "TAN-9B5E7EFA895E": "找一个人。一位女士，[[Nina Lagasse]]。",
    }
    for row_id, target in expected.items():
        row = rows.get(row_id)
        if row is None:
            errors.append(f"{row_id}: semantic regression fixture is missing")
        elif row.get("translation") != target:
            errors.append(
                f"{row_id}: semantic regression ({row.get('translation')!r} != {target!r})"
            )

    # Source-side cluster check: all direct Nina-search dialogue variants must
    # avoid the mechanically segmented “一个女人”, not just the reported line.
    for row in rows.values():
        source = row.get("source", "")
        target = row.get("translation", "")
        if "looking for" in source and ("Nina Lagasse" in source or "A woman." in source):
            if "一个女人" in target:
                errors.append(f"{row['id']}: literal Nina-search fragment remains: {target}")

    if errors:
        print(json.dumps({"error_count": len(errors), "errors": errors}, ensure_ascii=False, indent=2))
        return 1
    print(
        json.dumps(
            {
                "checked_rows": len(rows),
                "private_inquiry_agent_rows": len(private_agents),
                "semantic_fixtures": len(expected),
                "error_count": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
