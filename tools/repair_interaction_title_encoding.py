#!/usr/bin/env python3
"""Restore the interaction-title edits after a Windows code-page incident.

The mappings are kept in a UTF-8 source file created through the patch API,
not passed through a PowerShell pipeline.  The script updates both editorial
review artifacts and the re-chunked translation directory by stable ID.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXES = {
    "TAN-1311D6BE30A8": (
        "我的爱人，沉睡海底",
        "将民歌 My Bonnie Lies over the Ocean 的 Bonnie 作“爱人”而非姓名；与同一封信上“ZIELA MY LOVE”及收件人泽莉娅对应。",
    ),
    "TAN-AAB4A35E7431": (
        "莫分圣言一体",
        "仿经文题辞；Word 指圣言／Logos，Unity 呼应《骄阳之书》“分而不裂”的教义。避免“汝言”误作“你的言语”。",
    ),
    "TAN-7812C05DFC51": ("上如是……", "与正文既定译句“上如是，下亦然”完全统一。"),
    "TAN-2A727E682D96": (
        "类别：未归类——局里从前这么说",
        "office 指主角旧职防剿局；“类别：未归类”保留官僚标签式冷幽默，也不把 unclassified 误作纯粹“非机密”。",
    ),
    "TAN-6B850B7650CB": (
        "需要的，不过是光，还有某种洁净与秩序。 ",
        "化用海明威《一个干净明亮的地方》；严格保留源文末尾空格。",
    ),
    "TAN-F299BDE736CE": (
        "侍立静候者，亦在效力",
        "截取弥尔顿“只须站立静候，也是在服务”的名句；对应车站守候者，保留典故与冷讽。",
    ),
    "TAN-8DEAE46677B1": ("阳光，舶来品", "保留原题逗号造成的货品标签腔与战时进口物资语感。"),
    "TAN-A7D29320BFDB": (
        "鱼儿游来敲击它 / 并侧耳聆听",
        "引文题辞；保留斜线结构及 fishes 指向鱼而非敲门的人。",
    ),
    "TAN-ECF7E9410E99": (
        "太阳的居屋沉寂之时",
        "House of the Sun 按前作术语作“太阳的居屋”；标题以题辞式短语收束。",
    ),
    "TAN-428218D417DA": ("……下亦然", "与正文既定译句“上如是，下亦然”完全统一。"),
    "TAN-D9F35176C99F": (
        "有名有姓，群戏一场",
        "按戏剧语汇处理：具名人物继而汇成群戏；不把 parts 误解为身体部位。",
    ),
    "TAN-0A19EF9986EA": (
        "不过，拿来堵门缝，或许还有点用处",
        "draft excluder 指挡门缝的防风物；保留对纹丝不动之猫的干冷玩笑。",
    ),
    "TAN-BB2392A30593": (
        "秋天已死 你要记住",
        "引自阿波利奈尔《告别》；保留原句无标点、直接召唤记忆的诗形。",
    ),
    "TAN-ED6DD970FF4A": (
        "《蠕虫之蠕虫：我的肖像》，朱利安·科赛利，1924年（板面油画）",
        "Worm 是本系列固定概念“蠕虫”；仿“王中之王”结构作“蠕虫之蠕虫”，采用藏品题签格式。",
    ),
    "TAN-52FE6E3B6A05": (
        "“我会奋争，霍布森先生；我会成功；我会崛起。”",
        "保留三段严格递进与奥比耶的野心；rise 不窄化为职位上的“步步高升”。",
    ),
    "TAN-FB98AA9A7A0C": (
        "已在奥比耶的防线之内，却尚未穿透全部防线。",
        "主角已进入奥比耶梦中，inside 表示已突破外层防线；后句说明仍有内层防备，避免“身在防线之内”的空间歧义。",
    ),
    "TAN-F6455BA03A23": ("在它成为心以前", "Heart 是准则“心”；before 保留神话时间感。"),
    "TAN-87CE74A4DADE": (
        "此非你所能涉足之地",
        "场景是修道院秘处的神秘禁令；不擅自具体化为普通“入内”标牌。",
    ),
    "TAN-AFD064BC3065": ("光滑如镜", "Smooth 明指触感与表面状态；“光洁”会减弱如玻璃般平滑的直观意象。"),
    "TAN-0254758873BB": ("门，横着的", "保留 Gate, Horizontal 的逗号停顿与把床一本正经归类为横门的冷幽默。"),
    "TAN-0DCE60BC0DA4": (
        "女士，后来",
        "呼应 Weather Factory 既有作品名 The Lady Afterwards 的核心构词，同时保留本作逗号造成的悬置；不擅加指示词“那位”。",
    ),
    "TAN-44F679962A19": (
        "司辰有分钟。天有吗？",
        "大写 Hours 指司辰，同时利用普通 hours/minutes/days 的时间单位双关；译文明确保住设定层，避免只剩时间单位。",
    ),
    "TAN-0768244D90DA": ("从前的扎祖", "与“扎祖当年”成对：前者落在身份，后者落在时间。"),
    "TAN-BB2F2B9D81FE": ("绿衣夜莺", "结合罗迪娅的绿意外貌与歌声般说话方式，保留人物题名感。"),
}


def update_file(path: Path) -> int:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines()]
    changed = 0
    for row in rows:
        fix = FIXES.get(row.get("id"))
        if fix is None:
            continue
        row["translation"], row["notes"] = fix
        changed += 1
    if changed:
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
            encoding="utf-8",
        )
    return changed


def main() -> None:
    changed = 0
    for path in (
        ROOT / "build" / "reviews" / "interaction_titles_001_064.jsonl",
        ROOT / "build" / "reviews" / "interaction_titles_065_128.jsonl",
    ):
        changed += update_file(path)
    for path in sorted((ROOT / "translations").glob("chunk_*.jsonl")):
        changed += update_file(path)
    print(json.dumps({"fixed_ids": len(FIXES), "updated_rows": changed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
