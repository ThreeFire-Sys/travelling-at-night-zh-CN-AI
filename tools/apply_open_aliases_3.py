#!/usr/bin/env python3
"""Add open-set spelling and number variants that were previously link-only."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALIASES = {
    "Beachcrow": {"Beach-Crow": "拾滩鸦"},
    "Footnote": {"Footnotes": "脚注"},
    "Horned Axe": {"Horned-Axe": "双角斧"},
    "Hour": {"The Hours": "司辰"},
    "Stars": {"The Stars": "群星"},
    "Sun-in-Splendour": {"Sun": "太阳"},
    "Travelling": {"Travel": "旅行"},
}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(raw) for raw in path.read_text(encoding="utf-8-sig").splitlines() if raw]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")


def main() -> int:
    glossary_path=ROOT/"glossary/glossary.csv"
    with glossary_path.open("r",encoding="utf-8-sig",newline="") as h:
        rows=list(csv.DictReader(h));fields=list(rows[0])
    by={r["source_en"]:r for r in rows}
    prov_paths={o:ROOT/f"glossary/provenance/{o}.jsonl" for o in ("predecessor","travelling_new","real_world","editorial")}
    prov={o:load_jsonl(p) for o,p in prov_paths.items()}
    records={r["canonical"]:r for rs in prov.values() for r in rs}
    ledger_path=ROOT/"glossary/final_term_audit.jsonl";ledger=load_jsonl(ledger_path);audits={r["canonical"]:r for r in ledger}
    for canonical,aliases in ALIASES.items():
        if canonical not in by or canonical not in records or canonical not in audits: raise SystemExit(f"missing canonical {canonical}")
        records[canonical]["aliases"]=sorted(set(records[canonical].get("aliases",[]))|set(aliases),key=str.casefold)
        audits[canonical]["alias_targets_final"].update(aliases)
        for alias,target in aliases.items():
            if alias in by and by[alias]["target_zh"]!=target: raise SystemExit(f"collision {alias}")
            if alias not in by:
                row={"source_en":alias,"target_zh":target,"type":by[canonical]["type"],"case_sensitive":"true","confidence":"high","notes":f"开放终审：{canonical} 的链接/词形变体"};rows.append(row);by[alias]=row
    rows.sort(key=lambda r:(r["source_en"].casefold(),r["source_en"]))
    with glossary_path.open("w",encoding="utf-8",newline="") as h:
        w=csv.DictWriter(h,fieldnames=fields,lineterminator="\n");w.writeheader();w.writerows(rows)
    for o,p in prov_paths.items():
        prov[o].sort(key=lambda r:(r["canonical"].casefold(),r["canonical"]));write_jsonl(p,prov[o])
    ledger.sort(key=lambda r:(r["canonical"].casefold(),r["canonical"]));write_jsonl(ledger_path,ledger)
    print(json.dumps({"alias_families":len(ALIASES),"aliases":sum(map(len,ALIASES.values())),"glossary_terms":len(rows)},ensure_ascii=False))
    return 0


if __name__=="__main__":raise SystemExit(main())
