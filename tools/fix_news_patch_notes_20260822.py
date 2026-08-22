#!/usr/bin/env python3
"""Bring the in-game News translation into exact section parity with k.97 assets."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADING_RE = re.compile(r"(?m)^##\s+(\d{4}\.\d+\.[a-z]\.\d+).*?$")

MISSING_SECTIONS = {
    "2026.8.j.87": """## 2026.8.j.87 ——“我儿，你都做了什么”

* 制作 HUD 会提供更多关于刚制成或想要制作的物品的信息
* 与某位长生者交谈时，镜头现在会正确取景
* 若首次到访疗养院时没有打开冰箱，它不再自行变空
* 某些被遮蔽的房间在保存→读取后会显出内部物件的轮廓——已修复
* 光标不再对实际可通行的区域那么悲观
* 修复物品栏上下文菜单的一批问题
* 现在同一时间只应高亮一个回应
* 关闭产生删除确认的菜单时，确认框也会消失
* 伪造的邦国护照不再那么挑剔你所声称的姓名
* 若以其他方式达成目标，安德蕾的另一门生意仍可进行
* 首次进入书店前，即可与门口立牌互动
* 更新角色面板图像
* 大量叙事逻辑与文案修复""",
    "2026.8.j.65": """## 2026.8.j.65 ——“LANTERN 里有个 N”

* 紧急修复：角色创建界面把“Lantern”拼错，实在太丢人了""",
    "2026.8.j.61": """## 2026.8.j.61 ——“无题（钢琴），约 1948 年”

* 若你把猫一路追到钢琴顶上，（a）请对着镜子认真反省一下自己；（b）你无需先退到走廊，便可与它互动
* 修复游戏文件不可读／不可写时的启动崩溃——但愿如此
* 鼠标指针抖动会出现在非 16:9 显示器上，尤其是 Iris Xe 用户。我*觉得*现在应该好一点了？
* 谈论雪茄不再能让你重演勒索奥比耶的戏码
* 泽莉娅不再跳过一段对话。她*确实*是故意叫人摸不着头脑，但这一处我是真的没发现
* 另修一项难以解释的泽莉娅逻辑错误；若你此前无法对她撒谎，请再去找阿里斯蒂德等人
* 贝茜和罗迪娅不再意外把你踢出对话
* 第一处局部场景里那座该死的书架终于修好了
* 修复柏林目的地空白的旅行许可证提示；同时隐藏你尚未拥有的旅行物品描述
* 安德蕾不再出售你能在别处轻易免费找到的物品
* 文案修复""",
    "2026.8.j.46": """## 2026.8.j.46 ——“双生子的另一半”

* 修复疗养院夜间音乐不在夜间播放的问题
* 即使没睡好，斯宾塞现在也会需要刮脸（249d7a2f6）
* 角色创建提示现在有了安全上限，以免引起混乱
* 莉努不再对洗袜水重复收费
* 圣雷帕拉塔之窗现在少给一份记忆
* 角色面板焦点窗格点击后不再变空；升级技艺也不再破坏其他技艺的悬停显示
* 更多昂蒂布寻路修复
* 修复一座钟和一条船上的无限影响漏洞
* 不进入其局部场景，便不能再点击 NPC
* 文森特不那么爱瞬移了
* \\[SPOILER] 收到 \\[SPOILER]、\\[SPOILER] 或 \\[SPOILER] 的口信后，不再莫名拒绝谈论 \\[SPOILER]
* 特别高的脚注不应再滑出屏幕
* 修复斯特拉思科因对话中的几处问题，并新增几个回应
* 还有，别再把斯特拉思科因报告成 bug 了。可怜的人。
* 新同伴在你离开时会可靠地加入，不再只是半陪着你上火车
* 阿里斯蒂德现在会说“Welllll”，不是“Welll”，好让大家看出这是故意的，不是拼写错误 :)
* 修复醒来前的闪屏
* “仪式”说明更加清楚
* 选择提示中补上原先缺失的“或按 T”（3b496165c）
* 移除菲洛梅勒文本末尾的空格""",
}

TARGET_PAIRS = (
    (
        ROOT / "translations_k83/chunk_013.jsonl",
        ROOT / "translations_k83/translations_k83_supplement.jsonl",
    ),
    (
        ROOT / "translations_k97/chunk_014.jsonl",
        ROOT / "translations_k97/translations_k97_supplement.jsonl",
    ),
)


def sections(text: str) -> dict[str, str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    matches = list(HEADING_RE.finditer(normalized))
    return {
        match.group(1): normalized[
            match.start() : matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        ].strip()
        for index, match in enumerate(matches)
    }


def update(path: Path, canonical_translation: str | None = None) -> str:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    hits = [row for row in rows if "THE INVISIBLE CITY WHICH OCCUPIES THE SAME SPACE" in row.get("source", "")]
    if len(hits) != 1:
        raise SystemExit(f"{path}: expected one patch-notes row, found {len(hits)}")
    row = hits[0]
    source_order = list(sections(row["source"]))
    translated = sections(row["translation"])
    for version, replacement in MISSING_SECTIONS.items():
        if version in source_order:
            translated[version] = replacement
    missing = [version for version in source_order if version not in translated]
    if missing:
        raise SystemExit(f"{path}: untranslated News sections remain: {missing}")
    rebuilt = "\r\n\r\n".join(translated[version].strip() for version in source_order)
    rebuilt = rebuilt.replace("无限增加慈悲", "无限增加同情")
    rebuilt = rebuilt.replace("莫名出现的“发冷”提示", "莫名出现的“瑟瑟发抖”提示")
    rebuilt = rebuilt.replace("本体梦理协调局", "本体梦理协调办公室")
    rebuilt = rebuilt.replace("必需之印", "必然之印")
    row["translation"] = canonical_translation if canonical_translation is not None else rebuilt
    row["notes"] = (
        "News 完整性终审：中文公告版本标题与当前英文资产逐段对齐；"
        "补齐 j.87/j.65/j.61/j.46，并移除源文已删除的旧段。"
    )
    path.write_text(
        "".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n" for item in rows),
        encoding="utf-8",
    )
    print(f"updated {path.relative_to(ROOT)}: {len(source_order)} News sections")
    return row["translation"]


def main() -> None:
    for chunk, supplement in TARGET_PAIRS:
        canonical = update(chunk)
        update(supplement, canonical_translation=canonical)


if __name__ == "__main__":
    main()
