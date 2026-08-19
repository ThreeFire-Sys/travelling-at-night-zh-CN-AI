#!/usr/bin/env python3
"""构建 k.52 增补译文：fuzzy 复用（含按条目调整）+ 手工新译 + 补丁说明新章节。"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKLIST = ROOT / "build" / "worklist_k52" / "worklist.jsonl"
FUZZY = ROOT / "build" / "k52_fuzzy.jsonl"
PATCHDOC = ROOT / "localization" / "patch-notes.zh-CN.md"
OUT = ROOT / "build" / "translations_k52_supplement.jsonl"

# 手工新译（无近似可复用的 18 条）
HAND = {
    "TAN-08EBF44543C2": "[点头；径自走过。]",
    "TAN-330F62B120B7": "呃。",
    "TAN-4B882E6D1152": "啊？",
    "TAN-A4A1DB6294D3": "泽莉娅托我办的事，现在是办不成了。最好点点头，径自走过。",
    "TAN-AC19AB61D325": "[奥比耶不以为然地摆了摆手。]用我一位老朋友的话说：“为什么只能一个？为什么只能两个？”或者不如说：“我拒绝你的二选一。”",
    "TAN-EE2BA0C5277C": "西农布尔",
    "TAN-0A95E2C0A0F2": "泽莉娅的<i>trabai</i>，现在是没法完成了。",
    "TAN-7623B1FA270E": "不可能",
    "TAN-D7EEB6D3A80A": "天堂之眼",
    "TAN-E8BB57D17D5C": "视角会跟随斯宾塞；你也可以按住右键拖拽来移动视角。也可以在选项菜单的“操作”页查看键位。",
    "TAN-10680A57AABD": "已选奖励：",
    "TAN-149C5363336C": "选择你的奖励：",
    "TAN-20A41AD29F14": "以{0}解锁",
    "TAN-2EB0ED016060": "以杯提升",
    "TAN-5964E6A88520": "获得 +5 份铸之经历",
    "TAN-5A1288EC3658": "以{0}提升",
    "TAN-609C7E8B07B1": "获得 {0} 份经历",
    "TAN-AD7946328EC0": "演化为{0}？",
}

# fuzzy 复用条目的逐个调整规则（在旧译文上做精确替换）
ADJUST = {
    # Menace→Trouble 改名（k.51 起 Menaces 更名 Troubles；链接形态随行）
    "TAN-601D2B9AAACF": [("用于降低一项威胁，", "用于降低一项[[Trouble]]，")],
    "TAN-A97768092C18": [("用于降低一项威胁，", "用于降低一项[[Trouble]]，"),
                          ("提升另一项威胁。", "提升另一项麻烦。")],
    "TAN-C028ABD95606": [("用于降低一项威胁，", "用于降低一项[[Trouble]]，"),
                          ("提升另一项威胁。", "提升另一项麻烦。")],
    # 疲惫/痛苦交换数值 3→4
    "TAN-ACA340F42833": [("失去 3 点疲惫并获得 3 点痛苦", "失去 4 点疲惫并获得 4 点痛苦")],
    # 新增列表 "- " 前缀
    "TAN-1E5456791797": [("防剿局侦探司阍（已革职）", "- 防剿局侦探司阍（已革职）")],
    "TAN-5C91D827B003": [("门槛军团军医中尉（退役）", "- 门槛军团军医中尉（退役）")],
    "TAN-BCA7945D6D22": [("多塞特郡团上尉（已复员）", "- 多塞特郡团上尉（已复员）")],
    # Gain 模板加 "+"
    "TAN-E51AD81139B8": [("获得 {0} 份 {1} 经历", "获得 +{0} 份 {1} 经历")],
    # litany 源文少一层空行
    "TAN-27B7C5A62EDB": [("</i>\n\n\n", "</i>\n\n")],
    # 译文顺手修正同一意大利语拼写
    "TAN-378CC22F9FB6": [("commedia del'arte", "commedia dell'arte")],
    # k.52 给 Corona 补了链接，译文同步
    "TAN-6A9C3DB4951C": [("受冕触及的", "受[[Corona]]触及的")],
}


def main() -> int:
    old_zh = {}
    for line in FUZZY.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            old_zh[row["id"]] = row["old_translation"]

    k52_source = {}
    for line in WORKLIST.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            k52_source[row["id"]] = row["source"]

    patchnotes_zh = PATCHDOC.read_text(encoding="utf-8").strip()
    rows = []
    for rid, zh in sorted(old_zh.items()):
        if rid == "TAN-A068779E498D":
            continue  # 补丁说明单独处理
        for old, new in ADJUST.get(rid, []):
            assert old in zh, f"{rid}: 调整锚点不在旧译文中: {old!r}"
            zh = zh.replace(old, new)
        rows.append({
            "id": rid,
            "source": k52_source[rid],
            "translation": zh,
            "status": "translated",
            "notes": "k.52 迁移：复用既有译文并随源文微调（详见 polish changelog）",
        })
    for rid, zh in HAND.items():
        rows.append({
            "id": rid,
            "source": k52_source[rid],
            "translation": zh,
            "status": "translated",
            "notes": "k.52 迁移：新增内容人工新译",
        })
    # 补丁说明：更新后的 localization 文档（已含 k.51/k.6 两节新译）
    rows.append({
        "id": "TAN-A068779E498D",
        "source": k52_source["TAN-A068779E498D"],
        "translation": patchnotes_zh,
        "status": "translated",
        "notes": "k.52 迁移：前置 k.51 与 k.6 两节新译；其余沿用 localization/patch-notes.zh-CN.md",
    })
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"written {len(rows)} rows -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
