#!/usr/bin/env python3
"""构建 2026.8.l.8 迁移的增补译文（rebase 缺译 20 条）。

用法：python tools/build_l8_supplement.py
输出：build/translations_l8_supplement.jsonl

补丁说明条目（TAN-C7B87AB7C781）的新译文 = l.5 新章节译文 + tmp/l8_missing_diffs.json
里的旧译文全文（保持既有章节逐字不动）。两条 Worms 文本是 k.97 旧译加 [[ ]] 链接
（l.8 只给首处 Worms 补了链接，其余逐字复用旧译）。
"""

from __future__ import annotations

import json
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
DIFFS = WORKSPACE / "tmp" / "l8_missing_diffs.json"
OUT = WORKSPACE / "build" / "translations_l8_supplement.jsonl"

# l.5 补丁说明新章节（接旧译文时中间隔 \r\n\r\n，与旧译文既有章节分隔一致）
L5_SECTION = (
    "## 2026.8.l.5 — “隐秘圈层中的冷峻回廊”\n"
    "- 地图的观感与手感大下功夫！目前只有一个旅行目的地，你还不能充分体会，但旅行的体验优雅了不少"
    "（暗角、斯宾塞气泡、更好玩的按钮、更大的城市点击框、更漂亮的选择标记）\n"
    "- 默认提示泡延迟减半（对既有安装不生效，你仍可在配置中调低提示泡延迟）\n"
    "- 误选对话选项难上加难！文本走完后我们会等上四分之一秒，且不按方向键就不会选中第一个选项"
    "——可以放心猛敲空格了。另外，下方向键现在也能推进文本\n"
    "- 在场所里从制作切到物品栏再切回来，制作界面会记得该场所\n"
    "- 在水洼边行走，不再会诱发斯宾塞的怪异举动\n"
    "- 存档文件夹权限不对时，游戏不再崩溃\n"
    "- 新增镜头移动教程弹窗\n"
    "- 修了一大堆琐碎的高亮 bug\n"
    "- 已见过面但对方还摸不透你的人，日志里会显示“不确定”而非“未结识”\n"
    "- 没有存档时“读取游戏”按钮会隐藏，与继续按钮看齐\n"
    "- 错误报告上限 3000 字符（想写长篇的话，我们仍在 support@weatherfactory.biz）\n"
    "- 厘清了“消耗”与“耗尽”\n"
    "- 你表演戏法时，莉努的台词会有变化\n"
    "- 昂蒂布迎宾区不再转动斯宾塞。别怒而回首\n"
    "- 读取／保存菜单首次打开时滚动已正常"
)

TRANSLATIONS: dict[str, tuple[str, str]] = {
    # id: (translation, notes)
    "TAN-8B898F0EB820": (
        "莉努警惕地眨了眨眼。",
        "l.8 新增（莉努变戏法台词差分配套）；舞台指示短句，按既有风格译。",
    ),
    "TAN-0D5FABC43054": (
        "等级制度蠢得很。",
        "l.8 新增脚注选项描述；口语调侃语气。",
    ),
    "TAN-1A77138DE0A5": (
        "不是我",
        "l.8 新增脚注选项标签，与另一选项相对。",
    ),
    "TAN-B35E132F174C": (
        "精准很重要。",
        "l.8 新增脚注选项描述。",
    ),
    "TAN-FA43291C9769": (
        "“骄阳遭分裂时，其具名者亦随之碎裂。” \r\n\r\n"
        "[[司辰]]的具名者，是他们主要的仆从——或曰侧面，或曰流溢。其中一些，或许全部，都曾是[[长生者]]。\n\n"
        "[[漫宿]]的灵体与轻信的凡人交谈时，常自称是具名者。谁又会去较真呢？",
        "l.8 新增脚注（具名者条目）；术语按终审：Sun-in-Splendour 骄阳、Name 具名者、"
        "Hour 司辰、Long 长生者、Mansus 漫宿、spirit 灵体；保留 3 个 [[ ]] 链接。",
    ),
    "TAN-FC3DCDDCE71C": (
        "[[蠕虫]]还在我体内时是什么情形，我已记不得多少。痛楚；毒液；残破之剑明亮的刃面；"
        "黏滞浓稠的金色血液。我只清楚记得，我从不孤单。把蠕虫植入我体内的那些人，命令我们将"
        "特雷西加洛夷为废墟；他们以为，未建之城将在那里升起。可蠕虫有人要吃，也有旧账要算。",
        "l.8 修订：仅首处 Worms 补 [[ ]] 链接；其余逐字复用 k.97 旧译（TAN-B71DA24DCC7F）。",
    ),
    "TAN-07EBE4EAD18C": (
        "[[蠕虫]]还在我体内时是什么情形，我已记不得多少……\n\n"
        "回忆  <link=\"mypaststagneseve\">我的过往：圣亚割妮节前夕，1937 年（？）</link>",
        "l.8 修订：仅首处 Worms 补 [[ ]] 链接；其余逐字复用 k.97 旧译（TAN-9885F1012D2C），"
        "保留 <link> 标签与双空格排版。",
    ),
    "TAN-6EEF79653D65": (
        "镜头通常会跟随斯宾塞，但你可以按住右键拖拽，把它移到想要的位置。"
        "也可以查看选项菜单里“操作”标签页的键盘控制。",
        "l.8 新增镜头教程弹窗；镜头／右键拖拽沿用 k.6 补丁说明译法，"
        "Options→选项、Controls→操作沿用既有 UI 条目。",
    ),
    "TAN-2FECA9812E9C": (
        "用这件物品辅助一次成功的技艺检定，会让它耗尽！（技艺检定失败则不会耗尽它。）",
        "l.5 起物品 exhaust 统一“耗尽”，与 crafting 燃料 consume“消耗”区分；"
        "skill check 沿用“技艺检定”。",
    ),
    "TAN-3A8AF7FA6A37": (
        "使用时耗尽：{0}",
        "l.8 新增；保留 {0} 占位符；exhausted on use 沿用“耗尽”。",
    ),
    "TAN-4E313210BF91": (
        "不确定",
        "l.5 起日志好感标签：见过面但无看法时显示；与 Unmet“未结识”并列的短标签。",
    ),
    "TAN-58CACD3FC5D1": (
        "无法保存——请检查 {0} 的权限",
        "l.8 新增存档权限报错；保留 {0} 占位符。",
    ),
    "TAN-5F1554E2DCB1": (
        "右键单击使用（会耗尽这件物品）。",
        "l.8 新增；“右键单击”沿用既有 UI 译法；exhaust 统一“耗尽”。",
    ),
    "TAN-78CE94E32B4C": (
        "前往另一座城市时，这叠物品中会有一件消失。",
        "l.8 新增旅行物品提示；stack 译“这叠物品”。",
    ),
    "TAN-7DF8665BBCF5": (
        "右键单击，在你的性相池中恢复 {0} 点{1}（会耗尽这件物品）。",
        "l.8 新增；Aspect Pool 沿用终审“性相池”，refresh（点数）沿用“恢复”；"
        "保留 {0} {1} 两个占位符。",
    ),
    "TAN-9DDD89CCC230": (
        "要旅行，请前往车站。",
        "复用既有同句译法（k.97 无句点版“要旅行，请前往车站”），按新源文补句点。",
    ),
    "TAN-A2CC01F2E418": (
        "前往另一座城市时，它会变成别的东西。",
        "l.8 新增旅行物品提示。",
    ),
    "TAN-DCC421127E8A": (
        "前往另一座城市时，这叠物品中会有一件变成别的东西。",
        "l.8 新增旅行物品提示。",
    ),
    "TAN-FCE9D026159C": (
        "前往另一座城市时，它会消失。",
        "l.8 新增旅行物品提示。",
    ),
}


def main() -> None:
    diffs = json.loads(DIFFS.read_text(encoding="utf-8"))
    rows: list[dict] = []
    seen: set[str] = set()
    for d in diffs:
        wid = d["id"]
        seen.add(wid)
        if wid == "TAN-C7B87AB7C781":
            old_tr = d.get("old_translation")
            if not old_tr:
                raise SystemExit("补丁说明条目缺 old_translation，无法拼接")
            tr = L5_SECTION + "\r\n\r\n" + old_tr
            notes = ("l.5 新章节前置新译；k.98 及更早章节逐字保留旧译。"
                     "l.5 新词：Uncertain“不确定”/exhausted“耗尽”与 consumed“消耗”的区分。")
        else:
            tr, notes = TRANSLATIONS[wid]
        rows.append({
            "id": wid,
            "source": d["new"],
            "translation": tr,
            "status": "translated",
            "notes": notes,
        })
    missing = set(TRANSLATIONS) - seen - {"TAN-C7B87AB7C781"}
    if missing:
        raise SystemExit(f"手译条目不在缺译清单里：{sorted(missing)}")
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"写出 {len(rows)} 条 -> {OUT}")


if __name__ == "__main__":
    main()
