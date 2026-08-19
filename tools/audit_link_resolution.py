#!/usr/bin/env python3
"""Audit that every [[link]] term in baked zh-CN text resolves to a label.

The game's footnote hover resolves a link by matching the visible term against
``label``/``alternativeLabels`` (OrdinalIgnoreCase) of linkable scriptables
(Footnote, Skill, Passion, Sign, Aspect, Item, Destination).  After baking,
terms are Chinese; this script re-reads the baked assets, collects every
resolvable label/alias, and reports any ``[[term]]`` used in translated text
that would open an empty tooltip.

Usage: audit_link_resolution.py <baked_assets_dir|game_root> <review_catalog.jsonl> [game_root_for_typetrees]
Exit code 1 when unresolved terms exist.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
from bake_translations import read_raw_with_offset, UNITY_VERSION  # noqa: E402

LINKABLE_PREFIXES = (
    "Travelling.Infrastructure.Footnotes.Footnote",
    "Travelling.PCQualities.Skill",
    "Travelling.PCQualities.Passion",
    "Travelling.PCQualities.Sign",
    "Travelling.PCQualities.Aspect",
    "Travelling.PCQualities.Item",
    "Travelling.PCQualities.Destination",
)
LINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")
LABEL_FIELDS = ("label", "_label")
ALIAS_FIELDS = ("alternativeLabels", "_alternativeLabels")


def collect_labels(env) -> tuple[set[str], int]:
    labels: set[str] = set()
    objects_seen = 0
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        # 可链接的 ScriptableObject（Footnote/Skill/Aspect/Item 等）都在
        # resources.assets 里；关卡里的 MonoBehaviour 不参与 [[link]] 解析。
        if getattr(obj.assets_file, "name", "") != "resources.assets":
            continue
        # MonoBehaviour 的字段要靠 typetree/原始读取才能拿到；两类布局都试。
        tree = None
        try:
            tree = obj.read_typetree()
        except Exception:
            try:
                tree, _kind, _tail = read_raw_with_offset(obj)
            except Exception:
                continue
        if not isinstance(tree, dict):
            continue
        objects_seen += 1
        for field in LABEL_FIELDS:
            value = tree.get(field)
            if isinstance(value, str) and value.strip():
                labels.add(value.strip())
        for field in ALIAS_FIELDS:
            values = tree.get(field)
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, str) and value.strip():
                        labels.add(value.strip())
    return labels, objects_seen


def collect_link_terms(catalog: Path) -> dict[str, str]:
    terms: dict[str, str] = {}
    with catalog.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            entry = json.loads(line)
            translation = entry.get("translation") or ""
            for term in LINK_RE.findall(translation):
                terms.setdefault(term.strip(), entry.get("id", ""))
    return terms


def main() -> int:
    assets_root = Path(sys.argv[1]).resolve()
    catalog = Path(sys.argv[2]).resolve()
    typetree_root = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else None

    data_dir = assets_root
    if not (data_dir / "resources.assets").exists():
        candidates = sorted(p for p in assets_root.iterdir() if p.is_dir() and p.name.endswith("_Data"))
        if len(candidates) != 1:
            print(f"cannot locate *_Data under {assets_root}")
            return 1
        data_dir = candidates[0]

    baked = {p.name: p for p in data_dir.iterdir()
             if p.suffix == ".assets" or p.name == "globalgamemanagers"
             or re.fullmatch(r"level\d+", p.name)}
    if typetree_root is not None:
        # 烘焙目录只含被改写的文件；typetree 生成需要完整的文件集
        # （m_Script 引用 globalgamemanagers.assets），用游戏本体的文件补齐。
        game_data = next(p for p in typetree_root.iterdir()
                         if p.is_dir() and p.name.endswith("_Data"))
        files = [str(baked.get(p.name, p)) for p in sorted(game_data.iterdir())
                 if p.suffix == ".assets" or p.name == "globalgamemanagers"
                 or re.fullmatch(r"level\d+", p.name)]
    else:
        files = [str(p) for _, p in sorted(baked.items())]
    env = UnityPy.load(*files)
    if typetree_root is not None:
        try:
            generator = TypeTreeGenerator(UNITY_VERSION)
            generator.load_local_game(str(typetree_root))
            env.typetree_generator = generator
        except Exception as exc:  # 原始布局读取不依赖 typetree，生成器失败不致命
            print(f"typetree generator unavailable: {exc}")

    labels, objects_seen = collect_labels(env)
    labels_ci = {value.casefold() for value in labels}
    terms = collect_link_terms(catalog)
    unresolved = {term: entry_id for term, entry_id in terms.items()
                  if term.casefold() not in labels_ci}

    print(f"linkable labels/aliases: {len(labels)} (objects read: {objects_seen})")
    print(f"distinct [[terms]] in translations: {len(terms)}")
    if unresolved:
        print(f"UNRESOLVED: {len(unresolved)}")
        for term, entry_id in sorted(unresolved.items()):
            print(f"  [[{term}]]  (first seen in {entry_id})")
        return 1
    print("all [[link]] terms resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
