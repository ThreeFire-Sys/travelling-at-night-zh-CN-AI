#!/usr/bin/env python3
"""Apply the source-checked conversation-description (epigraph) review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


TRANSLATION_FIXES = {
    "TAN-CC2C59856798": ("“诗歌用海报，散文用报纸”", "“海报是诗，报纸是散文”"),
    "TAN-A7D29320BFDB": ("鱼儿游来敲击它 / 并侧耳聆听", "鱼儿游来敲一敲 / 再侧耳倾听"),
    "TAN-BB2392A30593": ("秋天已死 你要记住", "秋天已死 你要记得"),
    "TAN-2DDDA1E9FCCD": ("其乐震撼天地，恐惧袭遍一切生灵", "他们的乐声震撼天地，恐惧袭遍一切生灵"),
    "TAN-46E41B3A805B": ("沉睡者醒来，莫再迟延", "醒来吧，沉睡者，莫再迟延"),
    "TAN-FBE1AA5D52C5": ("我能说什么\n会比沉默更好？", "我能说些什么\n能胜过沉默？"),
}


NOTE_FIXES = {
    "TAN-1311D6BE30A8": "改写自传统民歌《My Bonnie Lies over the Ocean》首句：游戏把 over 改作 under，译文以“沉睡海底”保留溺亡暗示。",
    "TAN-6B850B7650CB": "直接截取海明威短篇《一个干净明亮的地方》句子；这是小说散文，不按诗行拆分。严格保留源文末尾空格。",
    "TAN-F299BDE736CE": "截取弥尔顿十四行诗《当我思考我如何耗尽光明》末句 they also serve；对应车站守候者，保留典故与冷讽。",
    "TAN-8496305CA11C": "化用柯南·道尔《银色马》中 the curious incident of the dog；对应圣吉内福尔故事中的狗。",
    "TAN-02B01C5D399D": "已用完整短语、单复数变体及诗歌限定检索，未发现早于或独立于游戏的可靠文本见证；暂判为针对 HORIZON 海报的游戏原创题辞，不能标作诗句。",
    "TAN-CC2C59856798": "改写自阿波利奈尔《地带》中将海报／广告视作诗、报纸视作散文的诗行；译成对称短句，不倒置为“诗歌使用海报”。",
    "TAN-A7D29320BFDB": "引自查尔斯·西米奇诗作《石头》（Stone）；保留斜线所示的两行诗形与敲击、倾听动作。",
    "TAN-BB2392A30593": "引自阿波利奈尔《告别》（L’Adieu）：法文 souviens-t’en 是直接劝记，游戏所用英译为 Autumn is dead you will remember；保留原句无标点的单行诗形。",
    "TAN-2DDDA1E9FCCD": "直接引自纪伯伦诗性散文《人子耶稣》（Jesus, the Son of Man）“Jesus and Pan”一节；保留单段，不伪拆成诗行。",
    "TAN-B5A0F4F3C490": "直接引自阿瑟·梅琴小说《大神潘》；这是小说散文，不标作诗句。",
    "TAN-46E41B3A805B": "化用菲利普·尼古拉的路德宗赞美诗 Wachet auf（英语常称 Sleepers, Wake）；按呼告语气译出，不误作陈述句。",
    "TAN-9604E4295AE4": "广泛署名为 W·H·奥登的名句，但未核得奥登诗集中可定位的篇名；保留署名层级，不虚构诗名或断言它是诗行。",
    "TAN-D8F7EB66B214": "直接引自莎士比亚《暴风雨》第二幕第一场 Of it own kind, all foison, all abundance；保留同义复沓。",
    "TAN-7BF9E973552C": "引自《启示录》3:20；沿中文经文通行措辞，作为经文而非诗歌记录。",
    "TAN-BC4656130F38": "化用米兰·昆德拉小说题名《不能承受的生命之轻》，并与标本熊交互构成反差；不是诗句。",
    "TAN-343C16B8A1B5": "指向宗教诗《沙滩上的脚印》（Footprints in the Sand）；该诗作者署名长期有争议，出处表不强行裁定作者。",
    "TAN-B6CB0D3BF624": "引自谢尔·希尔弗斯坦短诗《Batty》的末两行；游戏合并为一行，中文也保持会话题辞的一行格式。",
    "TAN-FBE1AA5D52C5": "引自朗费罗《将死者致意》（Morituri Salutamus）；严格保留游戏截取的两行诗形。",
    "TAN-6F162A266993": "引自托马斯·坎贝尔长诗《希望之乐》（The Pleasures of Hope）第一部第七行；保留格言感。",
    "TAN-B97891A4A2F0": "指向布尔沃-利顿小说《未来种族》（The Coming Race），并呼应介壳种蜕变；不是诗句。",
    "TAN-4CD9F4EBD491": "截取托马斯·亨利·赫胥黎《生源说与自然发生说》中 the great tragedy of Science 句；这是演说／论文散文，不是诗句。",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--translations", type=Path, default=Path("build/translations_j46_candidate"))
    args = parser.parse_args()

    chunks: dict[Path, list[dict]] = {}
    by_id: dict[str, tuple[Path, dict]] = {}
    for path in sorted(args.translations.glob("*.jsonl")):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
        chunks[path] = rows
        for row in rows:
            by_id[row["id"]] = (path, row)

    wanted = set(TRANSLATION_FIXES) | set(NOTE_FIXES)
    missing = sorted(wanted - set(by_id))
    if missing:
        raise SystemExit("missing translation IDs: " + ", ".join(missing))

    changed = 0
    note_changed = 0
    touched: set[Path] = set()
    for row_id, (expected, replacement) in TRANSLATION_FIXES.items():
        path, row = by_id[row_id]
        if row["translation"] == replacement:
            continue
        if row["translation"] != expected:
            raise SystemExit(f"{row_id}: expected {expected!r}, found {row['translation']!r}")
        row["translation"] = replacement
        touched.add(path)
        changed += 1

    for row_id, replacement in NOTE_FIXES.items():
        path, row = by_id[row_id]
        if row.get("notes", "") == replacement:
            continue
        row["notes"] = replacement
        touched.add(path)
        note_changed += 1

    for path in sorted(touched):
        path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in chunks[path]) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(f"translation fixes: {changed}; note fixes: {note_changed}; chunks: {len(touched)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
