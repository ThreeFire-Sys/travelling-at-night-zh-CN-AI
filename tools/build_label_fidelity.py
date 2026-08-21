#!/usr/bin/env python3
"""Build label_fidelity.json — asset-exact EN label restoration for F9 hot-swap.

The generic zh2en value map is per-STRING: when several English originals share
one reviewed Chinese label (e.g. footnote "Travelling" and verb-string "Travel"
both -> 旅行), the map can only pick one — the other asset's label then swaps to
the wrong variant and case-insensitive label-based link resolution breaks
(v2.4.13: authored link id "travelling" no longer matches label "Travel" ->
cyan broken link).

This map is built from asset LABEL SITES in the vanilla English extraction:
  * byId: runtime asset id (field "id"/"_id") -> true authored EN label
          (ids are unique, so this is always a function);
  * byCn: reviewed CN label -> true EN label, only where unambiguous within
          asset-label scope (conflicts dropped and reported).

Usage: build_label_fidelity.py <all_string_fields.jsonl> <review_catalog.jsonl> <out.json>
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

LABEL_PATHS = ("label", "_label")
ID_PATHS = ("id", "_id")


def main() -> int:
    fields_path = Path(sys.argv[1])
    catalog_path = Path(sys.argv[2])
    out_path = Path(sys.argv[3])

    catalog: dict[str, str] = {}
    with catalog_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            entry = json.loads(line)
            source = (entry.get("source") or "").strip()
            target = (entry.get("translation") or "").strip()
            if source and target and source != target:
                catalog[source] = target

    # 先按资产（asset_file+path_id）聚合 id 与 label 位点。
    assets: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    with fields_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            field = json.loads(line)
            field_path = field.get("field_path", "")
            if field_path in LABEL_PATHS:
                key = (field["asset_file"], str(field["path_id"]))
                assets[key]["label"] = (field.get("source") or "").strip()
            elif field_path in ID_PATHS:
                key = (field["asset_file"], str(field["path_id"]))
                assets[key]["id"] = (field.get("source") or "").strip()

    by_id: dict[str, str] = {}
    by_cn: dict[str, str] = {}
    cn_conflicts: dict[str, set[str]] = defaultdict(set)
    labelled = 0
    for site in assets.values():
        en_label = site.get("label") or ""
        if not en_label or en_label not in catalog:
            continue
        zh_label = catalog[en_label]
        labelled += 1
        asset_id = site.get("id") or ""
        if asset_id:
            if asset_id in by_id and by_id[asset_id] != en_label:
                print(f"WARN: id {asset_id!r} 对应两个英文标签，保留先见："
                      f"{by_id[asset_id]!r} vs {en_label!r}")
            else:
                by_id[asset_id] = en_label
        if zh_label in by_cn and by_cn[zh_label] != en_label:
            cn_conflicts[zh_label].add(en_label)
            cn_conflicts[zh_label].add(by_cn[zh_label])
        else:
            by_cn[zh_label] = en_label
    for zh_label in cn_conflicts:
        by_cn.pop(zh_label, None)

    payload = {"version": 1, "byId": by_id, "byCn": by_cn}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1)
    print(f"label sites: {labelled}  byId: {len(by_id)}  byCn: {len(by_cn)}  "
          f"byCn 冲突剔除: {len(cn_conflicts)}")
    for zh_label, ens in sorted(cn_conflicts.items()):
        print(f"  byCn conflict {zh_label!r} <- {sorted(ens)}（仍由 byId 精确覆盖）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
