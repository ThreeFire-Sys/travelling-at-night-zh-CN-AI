#!/usr/bin/env python3
"""Build lang_swap.json — the bidirectional value map for the in-game F9
language hot-swap (LanguageSwap plugin module).

Sources: merged review_catalog.jsonl (authored en -> reviewed zh) plus
glossary/runtime_supplement.csv (value-matched extras).  Only pairs where the
languages differ are emitted; identity strings need no swap.

Guarantees (verified here, non-negotiable):
  * en -> zh is a FUNCTION (zero conflicts) — an English-mode pass followed by
    a Chinese-mode pass restores every value exactly.
  * zh -> en may be ambiguous (several English originals share one reviewed
    translation, e.g. [Leave.]/[Go.] -> [离开。]); a deterministic choice is
    made and reported.  This only affects which English synonym is displayed.

Usage: build_lang_swap_map.py <review_catalog.jsonl> <runtime_supplement.csv> <out.json>
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

LINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")
TAG_RE = re.compile(r"<[^>]*>")
# 剥标签变体的最短长度：过短的剥标签键（如 "。"、"是的"）会在整串/子串级误伤
# 恰好等于它的无关显示文本。
MIN_STRIPPED_VARIANT_LEN = 4


def fold_links(value: str) -> str:
    """游戏渲染 [[X]] 后的可见形态：链接标记消失，只留标签文本。"""
    return LINK_RE.sub(lambda match: match.group(1), value)


def strip_tags(value: str) -> str:
    """TMP 富文本标签（<i>/<b>/<color>/<link> 等）全部剥掉后的纯文本形态。"""
    return TAG_RE.sub("", value)
    return LINK_RE.sub(lambda match: match.group(1), value)


def main() -> int:
    catalog_path = Path(sys.argv[1])
    supplement_path = Path(sys.argv[2])
    out_path = Path(sys.argv[3])
    # 可选第 4 参数：位点级译文覆盖表（缺省读工作区 glossary/site_overrides.csv）。
    overrides_path = Path(sys.argv[4]) if len(sys.argv) > 4 else Path("glossary/site_overrides.csv")

    pairs: dict[str, str] = {}
    with catalog_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            entry = json.loads(line)
            source = entry.get("source", "")
            translation = (entry.get("translation") or "").strip()
            if source and translation and translation != source:
                pairs[source] = translation
    with supplement_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            source = (row.get("source_en") or "").strip()
            target = (row.get("target_zh") or "").strip()
            if source and target and source != target:
                existing = pairs.get(source)
                if existing is not None and existing != target:
                    print(f"CONFLICT: {source[:40]!r}: {existing[:30]!r} vs {target[:30]!r}")
                    return 1
                pairs[source] = target

    # 显示态变体：游戏渲染时会折叠 [[链接]]、裁剪首尾空白，显示出来的字符串
    # 因此不等于任何原始键（v2.1.1 实测：拼装/折叠串掉进了半截子串替换）。
    # 变体只填原始对未占据的键：原始条目优先；变体间冲突的键整体封禁。
    # 注意：折叠变体的【值】保留原始形态（含 [[X]] 标记），由插件在交换时
    # 用被替换区段里找到的 <link> 包装器重新装饰——悬停链接因此不丢。
    variants: dict[str, str] = {}
    blocked: set[str] = set()

    def collect_variant(source: str, target: str) -> None:
        if not source or not target or source in pairs or source in blocked:
            return
        if source in variants and variants[source] != target:
            blocked.add(source)
            del variants[source]
            return
        variants[source] = target

    trimmed_count = 0
    folded_count = 0
    stripped_count = 0
    for source, target in list(pairs.items()):
        if source.strip() != source:
            before = len(variants)
            collect_variant(source.strip(), target.strip())
            trimmed_count += len(variants) - before
        folded_source = fold_links(source)
        if folded_source != source:
            before = len(variants)
            collect_variant(folded_source, target)  # 值保持原始形态（含 [[]]）
            folded_count += len(variants) - before
        # 剥标签变体：显示交换的"去标签整串/纯文本子串"两级在剥掉全部 TMP 标签
        # 的纯文本上匹配；译文内嵌 <i>/<b> 等标签时折叠键永远匹配不上
        # （v2.1.6 实测：法兰西三色旗整句只换了链接名）。值保持原始形态。
        stripped_source = strip_tags(fold_links(source))
        if stripped_source != folded_source and len(stripped_source) >= MIN_STRIPPED_VARIANT_LEN:
            before = len(variants)
            collect_variant(stripped_source, target)
            stripped_count += len(variants) - before
    pairs.update(variants)

    en2zh = dict(pairs)
    zh2en: dict[str, str] = {}
    ambiguous: dict[str, list[str]] = {}
    for source, target in sorted(pairs.items()):
        if target in zh2en and zh2en[target] != source:
            existing = zh2en[target]
            # 折叠变体与原始条目共享同一译文时，优先保留带 [[ ]] 链接标记的
            # 原始形态作值——否则交换到英文后链接标记丢失，SettleLinks 无标记
            # 可装饰，链接变裸文本（v2.1.11 实测："the [[Church]]'s" 在排序上
            # 输给折叠形态 "the Church's"，英文链接失效）。
            if "[[" in source and "[[" not in existing:
                ambiguous.setdefault(target, [existing]).append(source)
                zh2en[target] = source
                continue
            ambiguous.setdefault(target, [existing]).append(source)
            continue  # 先到先得，确定性选择
        zh2en[target] = source
    # zh2en 方向同样要折叠/剥标签键：显示态的中文（[[ ]] 与 TMP 标签已渲染）
    # 也能整句命中。值保持英文原始形态（含 [[ ]]），由插件交换时重新装饰。
    folded_zh_count = 0
    stripped_zh_count = 0
    for source, target in sorted(pairs.items()):
        folded_target = fold_links(target)
        if folded_target != target:
            # 与反转循环同例：折叠/剥标签的中文键若被折叠变体的源（无 [[ ]]）
            # 抢先占据，交换到英文后链接标记丢失。带标记的原始源优先。
            current = zh2en.get(folded_target)
            if current is None or ("[[" in source and "[[" not in current):
                if current is None:
                    folded_zh_count += 1
                zh2en[folded_target] = source
        stripped_target = strip_tags(folded_target)
        if stripped_target != folded_target and len(stripped_target) >= MIN_STRIPPED_VARIANT_LEN:
            current = zh2en.get(stripped_target)
            if current is None or ("[[" in source and "[[" not in current):
                if current is None:
                    stripped_zh_count += 1
                zh2en[stripped_target] = source

    # 位点级覆盖的 zh→en 单向键：烘焙资产中这些位点的显示值是覆盖译文
    # （如 Quote 题签《西班牙》），F9 切英文时要能换回英文源串。反向
    # （en→zh）不加——默认译文（地图标签裸名）优先；Quote 位点在 F9 切中文
    # 时显示裸名，属可接受的已知妥协（重开场景即恢复覆盖形态）。
    override_zh_count = 0
    if overrides_path.exists():
        with overrides_path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                target = (row.get("translation") or "").strip()
                source = (row.get("source_en") or "").strip()
                if not target or not source or target == source:
                    continue
                existing = zh2en.get(target)
                if existing is not None and existing != source:
                    print(f"site override zh2en conflict: {target!r} <- {existing!r} vs {source!r}")
                    return 1
                if existing is None:
                    zh2en[target] = source
                    override_zh_count += 1

    payload = {"version": 1, "en2zh": en2zh, "zh2en": zh2en}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    size_kb = out_path.stat().st_size // 1024
    print(f"pairs: {len(en2zh)} (含裁剪变体 {trimmed_count}、折叠变体 {folded_count}、剥标签变体 {stripped_count}、封禁冲突键 {len(blocked)})  zh2en: {len(zh2en)} (折叠键 {folded_zh_count}、剥标签键 {stripped_zh_count}、位点覆盖键 {override_zh_count})  ambiguous zh: {len(ambiguous)}  size: {size_kb} KiB")
    for target, sources in list(ambiguous.items())[:5]:
        print(f"  ambiguous {target[:24]!r} <- {[s[:24] for s in sources]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
