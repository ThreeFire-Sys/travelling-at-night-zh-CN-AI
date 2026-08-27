#!/usr/bin/env python3
"""构建 2026.8.l.43 迁移的增补译文（rebase 缺译 8 条）。

用法：python tools/build_l43_supplement.py
输出：build/translations_l43_supplement.jsonl

补丁说明条目（TAN-0D88BAFE7B7A）= l.42 新章节译文 + tmp/l43_missing_diffs.json
里的旧译文全文（l.31 及更早章节逐字保留）。
"""

from __future__ import annotations

import json
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
DIFFS = WORKSPACE / "tmp" / "l43_missing_diffs.json"
OUT = WORKSPACE / "build" / "translations_l43_supplement.jsonl"

L42_SECTION = (
    "## 2026.8.l.42 — “迪韦齐斯的约翰·亨利·斯莫尔”\n"
    "- 修复疗养院里画作消失的问题\n"
    "- 斯宾塞不再会卡在门框边缘，行走动画也微调了\n"
    "- 屋顶现在在所有情况下都渲染在雨幕之后\n"
    "- 已确认出发期间，地图会显示“立即出发——即将抵达”浮层且关闭按钮不可用"
    "——免得大家误以为地图关不上是 bug\n"
    "- 拖动物品时，已装备物品的图标不再原地滞留\n"
    "- 授权页面措辞调整——我们希望把配置选项（比如“多少人在用快/慢对话速度”）"
    "和剧情选择一起收集；仍不含任何个人身份信息\n"
    "- 脚注文案微调"
)

TRANSLATIONS: dict[str, tuple[str, str]] = {
    "TAN-A165B230C19D": (
        "在月台上",
        "l.43 修订（原 Trivial 退役）；车站月台状态标签。",
    ),
    "TAN-1705B24BDB72": (
        "是，并且允许将其与游戏内错误报告关联",
        "l.43 数据授权选项。",
    ),
    "TAN-41DF6730F529": (
        "我们不会收集任何关于剧情与配置选择的数据",
        "l.43 数据授权选项。",
    ),
    "TAN-446F058CA364": (
        "<b>我们可以收集你在剧情与配置上所做选择的数据吗？</b>\n\n"
        "<b>否</b>（或不作答）——我们不收集任何数据。\n\n"
        "<b>是</b>——我们将使用<b>假名化</b>的剧情与配置选择数据来改进游戏。\n\n"
        "<b>是，并关联</b>——允许我们把游戏内错误报告与你的数据相关联"
        "——也就是能把它和错误报告的联系邮箱对应起来",
        "l.43 修订的数据授权弹窗；保留 <b> 标记与分段结构；pseudonymised 译“假名化”。",
    ),
    "TAN-57F048F545BB": (
        "我们将收集关于剧情与配置选择的假名化数据",
        "l.43 数据授权选项。",
    ),
    "TAN-5CFA2330D2D2": (
        "立即出发——即将抵达",
        "l.43 地图出发确认浮层。",
    ),
    "TAN-94C116EE118A": (
        "数据分析",
        "l.43 修订（原“Analytics consent”缩短为“Analytics”）。",
    ),
}


def main() -> None:
    diffs = json.loads(DIFFS.read_text(encoding="utf-8"))
    rows: list[dict] = []
    seen: set[str] = set()
    for d in diffs:
        wid = d["id"]
        seen.add(wid)
        if wid == "TAN-0D88BAFE7B7A":
            old_tr = d.get("old_translation")
            if not old_tr or "2026.8.l.31" not in old_tr:
                raise SystemExit("补丁说明旧译异常（应含 l.31 章节）")
            tr = L42_SECTION + "\r\n\r\n" + old_tr
            notes = "l.42 新章节前置新译；l.31 及更早章节逐字保留旧译。"
        else:
            tr, notes = TRANSLATIONS[wid]
        rows.append({
            "id": wid,
            "source": d["new"],
            "translation": tr,
            "status": "translated",
            "notes": notes,
        })
    missing = set(TRANSLATIONS) - seen - {"TAN-0D88BAFE7B7A"}
    if missing:
        raise SystemExit(f"手译条目不在缺译清单里：{sorted(missing)}")
    if len(rows) != len(diffs):
        raise SystemExit(f"行数不符：{len(rows)} != {len(diffs)}")
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"写出 {len(rows)} 条 -> {OUT}")


if __name__ == "__main__":
    main()
