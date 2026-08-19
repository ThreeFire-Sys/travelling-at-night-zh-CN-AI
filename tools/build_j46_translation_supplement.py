#!/usr/bin/env python3
"""Build the reviewed j.46 supplement from the audited rebase delta."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REUSE_TRANSLATION = {
    "TAN-37CDC2EB2325": "TAN-43F1E8F3514A",
    "TAN-3ABC3DFBBA24": "TAN-D74E7EB18D89",
    "TAN-3BEE7E937131": "TAN-2BF6D487F483",
    "TAN-49BBBBC19F51": "TAN-FA9F09EC4EE1",
    "TAN-C688D5971478": "TAN-46F6A4558FA5",
    "TAN-CF493BB9AB0C": "TAN-6BD7E95ED6D2",
    "TAN-D2A1ADD54075": "TAN-96CD21B9ED7D",
    "TAN-D96EE30F118D": "TAN-0A9A49C829F7",
    "TAN-F1B376A8C558": "TAN-EFB19814D442",
}


DIRECT_TRANSLATIONS = {
    "TAN-1F101867A0AA": "霍布森先——生！霍布森先生。请恕我不再耽搁您。再会。",
    "TAN-38F4762D7C43": (
        "“我认识一个把飞蛾捕进钟形玻璃罩的人。每逢这样的夜晚，他会将它们逐只放出，"
        "让它们死在烛火里。”\n\n"
        "蛾是混沌与渴望的[[Principle]]。它的[[Hours]]如今已是[[Uncounted]]，还是只是变得不同了？"
        "蛾总教人捉摸不定。"
    ),
    "TAN-3F09151DD8C9": "或按 T 选择",
    "TAN-41534FAADFD7": (
        "离去、被[[Cross]]吞噬、遭囚、藏匿，还是仍在太阳之战中？你总不能打电话去查证。\n\n"
        "当然，任何不在数中、却<i>尚未</i>死去的[[Hour]]，随时都可能突然归来。"
    ),
    "TAN-5091B0E91317": "[斯特拉思科因装作对手边的书很感兴趣。]",
    "TAN-51499F86D296": (
        "智识、启示、金色清明的[[Principle]]。灯若太盛，一切都会变得<i>过于</i>清晰。"
    ),
    "TAN-55CC82711017": (
        "夜色得了消遣。它猜想着，到了外面的世界，在未来每一道阴影之间，会是怎样的光景。"
    ),
    "TAN-5723EE8AC2C3": (
        "‘祈祷？’我寻思着……有那条手臂，你做起来是不是更容易……[笑得说不下去。]"
    ),
    "TAN-7505C0CA790C": "您也一样，斯特拉思科因先生。",
    "TAN-7A17A5FD8475": (
        "“夜行既不更快，也不更安全——所以我们偏要夜行。”——克里斯托弗·伊利奥波里\n\n"
        "通晓超尘世的正路与幽径。[[Night Arts]]之一，可用于门槛与受创之地。"
    ),
    "TAN-7FC4484712C5": "[冷冰冰地]霍布森先生。祝您日安。",
    "TAN-83A702A1BDBA": (
        "饥饿，欲望，溺人的水。\n\n"
        "我们以之命名的[[Hour]]如今已是[[Uncounted]]。杯之[[Principle]]曾同等尊崇诞生与盛宴。"
        "或许如今仍是如此。诸战以来，世界仍不断诞育婴孩，只是婴孩降生时，未必还像从前那样。"
    ),
    "TAN-86B3373895C2": (
        "栖居于世界背后的隐秘诸神；凶险，崇高，在压制竞争者时绝不留情。"
        "有些从[[Know]]、[[Long]]与[[Names]]的位阶中一路攀升。有些则以全然不同的方式取得神位。\n\n"
        "诸战之前，司辰维系着历史的意义。祂们的辩论与妥协，将每一种可能的过去编织成连贯的未来。"
        "如今祂们大概——基本上——都已离去，成为[[Uncounted]]。"
        "历史任由本体梦理的不连贯与圣显破坏摆布。直白地说：季节不对，人不是人，法国处处漏洞。"
    ),
    "TAN-8E69312FD5FB": (
        "研究那些不应研究之物：蠕虫、地震、亚现实的干预。\n\n"
        "[[Night Arts]]之一；可用于受创之地与暗影之地。"
    ),
    "TAN-8E9416C75FC7": (
        "得了，霍布森先生，别再放在心上。绅士自然明白，仆役阶级做事，也不能指望他们有多高明。"
    ),
    "TAN-8F1F6B92ACED": (
        "只有天气坏时才难受。所以我待在公园这边，明白吧？不过我看，昂蒂布最近的天气可不怎么好。"
    ),
    "TAN-91C3971E0729": (
        "这场演变绝非什么笑料，霍布森先生。一点也不好笑。"
    ),
    "TAN-94D548798EAB": (
        "“火，”我曾读到，“是暖人的冬，是吞噬的春。”\n\n"
        "我们称作[[Forge of Days]]的[[Hour]]如今已是[[Uncounted]]，但铸仍是转化与毁灭的[[Principle]]。"
        "最近，这类事可发生了不少。"
    ),
    "TAN-9A037F2B58BD": "一个精瘦英俊的男人在入口处闲荡，轻快地吹着口哨。",
    "TAN-9B41444214D4": (
        "心是守护、坚忍的[[Principle]]。因而世界延续不息。然而[[Thunderskin]]——不息之心，"
        "那位曾守护我们所知世界表皮的[[Hour]]——如今已经沉默。"
    ),
    "TAN-C845E3AF1487": (
        "[[Huissier]]中尉！我听说您在这儿。真不敢相信您竟没来找我！"
    ),
    "TAN-D5F748CAE05C": "观感——菲洛梅勒",
    "TAN-DF380D40E6B2": (
        "实在抱歉，斯特拉思科因先生。一名护理员向我传了假话。看来我们俩都是这场恶作剧的受害者。"
    ),
    "TAN-E298B47DD2C9": (
        "正是如此，斯特拉思科因先生。正是如此。多谢您的宽宏大量。"
    ),
    "TAN-E33131FDA755": (
        "我先给驱灵师当助手，后来又在一个非同寻常的堂区担任神父。那段日子里的见闻动摇了我的信仰——"
        "不久，我便离开了教会。\n\n"
        "<i>1919 至 1921 年间，斯宾塞曾是无敌太阳教会的神父。领受圣职时，灵魂中发光的魂质——"
        "<b>明识</b>——会被永久烙下印记。因此严格说来，他仍能施行圣礼，尽管这可能违反教会法。</i>"
    ),
    "TAN-E3E75A181231": "[保持沉默。挑起一边眉毛。]",
    "TAN-EA2E8CA060C4": (
        "穿过边境的幽暗夹角，贴着近侧表层前行。“屋壁广如星光。”"
    ),
    "TAN-EA4523016E31": (
        "启不容封缄，也不容隔绝。它是将我们推出无知庇护的[[Principle]]。伤口与门皆为启。\n\n"
        "那位解封又拆缝的[[Hour]]如今已不在数中。另一位司辰曾立于每一道门槛：或许仍然存在。"
    ),
    "TAN-EF1EF2C12A2A": (
        "反复点击，似乎意味着你掉进了某种小小的寻路遗忘坑里？如果确是如此，可以试试选项菜单里的“脱困”按钮——"
        "它也许能把你解救出来。\n\n"
        "如果你只是点得兴起、点得恼火，或是渴望踏上禁地，那就抱歉打扰了，请继续。"
    ),
    "TAN-FA69C0A8364F": "菲洛梅勒",
    "TAN-FF7CFA2854C3": (
        "所有征服都发生在刃上。曾有一位居于那里，双目失明。另一位强壮。第三位，我们总尽量避而不谈。\n\n"
        "刃是战斗与抗争的[[Principle]]。上校、狮子匠、裂分之狼曾是它的司辰；"
        "但如今祂们都已成为[[Uncounted]]，纷争则以纷争为食。"
    ),
}


PATCH_NOTES_ID = "TAN-589F52D51AC1"
OLD_PATCH_NOTES_ID = "TAN-44442E3EDADB"
PATCH_NOTES_PREFIX_ZH = """## 2026.8.j.46 - “双生子的另一半”

- 修复疗养院夜间音乐不播放的问题
- 即使斯宾塞没正经睡觉，他现在也会需要刮胡子（249d7a2f6）
- 角色创建提示现在会安全地限制长度，免得引起误解
- 莉努不再为洗袜水收两遍钱
- 圣雷帕拉塔的窗边少了一段记忆
- 点击角色面板的焦点窗格不再一片空白；升级技艺也不再破坏其他技艺的悬停效果
- 继续修复昂蒂布的寻路
- 修复一座钟和一艘船上可无限获取影响的漏洞
- 只有进入 NPC 所在的局部场景后，才能点击他们
- 文森特不那么爱瞬移了
- 在[SPOILER]已从[SPOILER]、[SPOILER]或[SPOILER]处得到消息后，[SPOILER]不再令人费解地拒谈此事
- 特别高的脚注应该不会再滑出屏幕
- 修复斯特拉思科因对话里的几处错误，并新增几个回应
- 还有，别再把斯特拉思科因当成错误报告了。可怜的人
- 离开时，新同伴现在会可靠地加入队伍，不再只陪你坐半程火车
- 阿里斯蒂德现在说的是“Welllll”而不是“Welll”，这样就能看出这是有意为之，不是错字了 :)
- 修复醒来前的画面闪烁
- 仪式说明更加清楚
- 选择提示原本漏了“或按 T”（3b496165c）
- 移除菲洛梅勒名字末尾的空格

"""


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def collect_reviewed(directory: Path) -> dict[str, dict[str, Any]]:
    rows = [
        row
        for path in sorted(directory.glob("chunk_*.jsonl"))
        for row in read_jsonl(path)
    ]
    result = {str(row["id"]): row for row in rows}
    if len(result) != len(rows):
        raise RuntimeError("reviewed translations contain duplicate IDs")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("delta_report", type=Path)
    parser.add_argument("reviewed_translations", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    delta = json.loads(args.delta_report.read_text(encoding="utf-8"))
    additions = {str(row["id"]): row for row in delta["additions"]}
    reviewed = collect_reviewed(args.reviewed_translations)
    expected = set(REUSE_TRANSLATION) | set(DIRECT_TRANSLATIONS) | {PATCH_NOTES_ID}
    if expected != set(additions):
        missing = sorted(set(additions) - expected)
        stale = sorted(expected - set(additions))
        raise RuntimeError(f"j.46 delta mismatch; unhandled={missing}, stale={stale}")

    translations = dict(DIRECT_TRANSLATIONS)
    for new_id, old_id in REUSE_TRANSLATION.items():
        translations[new_id] = str(reviewed[old_id]["translation"])

    new_patch_source = str(additions[PATCH_NOTES_ID]["source"])
    old_patch_source = str(reviewed[OLD_PATCH_NOTES_ID]["source"])
    if not new_patch_source.endswith(old_patch_source):
        raise RuntimeError("j.46 patch notes are not an exact prefix extension")
    translations[PATCH_NOTES_ID] = (
        PATCH_NOTES_PREFIX_ZH + str(reviewed[OLD_PATCH_NOTES_ID]["translation"])
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for row_id in sorted(additions):
            source_row = additions[row_id]
            output_row = {
                "id": row_id,
                "source": source_row["source"],
                "translation": translations[row_id],
                "status": "translated",
                "notes": "2026.8.j.46 增量：对照真实对话图、旧译与版本差异人工复核。",
            }
            if not str(output_row["translation"]).strip():
                raise RuntimeError(f"empty supplement translation: {row_id}")
            handle.write(
                json.dumps(output_row, ensure_ascii=False, separators=(",", ":"))
                + "\n"
            )
    print(json.dumps({"supplement_entries": len(additions)}, ensure_ascii=False))
    print(f"Output: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
