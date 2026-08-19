#!/usr/bin/env python3
"""Build the manually reviewed translation supplement for game build j.66."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DELTA = ROOT / "build" / "reviews" / "rebase_delta_j66.json"
OLD_TRANSLATIONS = ROOT / "build" / "translations_j47_candidate"
OUTPUT = ROOT / "build" / "translations_j66_supplement.jsonl"


def load_old() -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for path in sorted(OLD_TRANSLATIONS.glob("chunk_*.jsonl")):
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            row = json.loads(line)
            rows[row["id"]] = row
    return rows


def main() -> int:
    delta = json.loads(DELTA.read_text(encoding="utf-8-sig"))
    additions = {row["id"]: row for row in delta["additions"]}
    old = load_old()

    news_prefix = """## 2026.8.j.65 - “灯里有个 N”

* 紧急修复：角色创建界面把“Lantern”拼错了，实在太丢人


## 2026.8.j.61 - “无题（钢琴），约 1948 年”

* 如果你把猫追到了钢琴顶上：（a）请对着镜子好好反省一下；（b）与它互动前，不必先退出到走廊
* 修复游戏文件无法读取／写入时的启动崩溃——但愿如此
* 鼠标指针抖动会出现在非 16:9 显示器上，尤其是使用 Iris Xe 芯片的玩家。我*觉得*现在应该好一些了？
* 谈论雪茄不再让你重复上演勒索奥比耶的戏码
* 泽莉娅不再跳过对话中的一步。她*确实*是故意说得令人迷惑，但我之前真的没发现这一处
* 又一个难以解释的泽莉娅逻辑错误；如果你先前不能对她撒谎，请重新拜访阿里斯蒂德等人
* 贝茜与罗迪娅应该不会再出人意料地把你踢出对话
* 第一个局部场景里那个该死的书架现在终于修好了
* 修复柏林目的地的旅行许可提示为空白；同时隐藏了尚未拥有的旅行物品说明
* 安德蕾不再出售一件能在别处轻易免费找到的物品
* 文案修正


"""
    old_news = old["TAN-589F52D51AC1"]["translation"]
    old_news_start = old_news.index("## 2026.8.j.46")

    translations = {
        "TAN-046581AC68C2": "柏林：巡回演出许可证",
        "TAN-0B9FDD8C1351": "这会将你的电子邮件地址、game.log 和最近的存档（以及可选截图）发送到我们的安全数据库。如果你选择“是，链接”，还会包含你的安装 ID。我们只会使用你的电子邮件地址联系你处理技术问题，不会与任何人分享。你可以要求我们删除这些数据。",
        "TAN-0D1AB1F10D27": "开始考虑强迫方案（仅限未设置状态）。若已进入后续阶段或已经结束，则不执行任何操作，以免被放弃的计划死灰复燃。",
        "TAN-16CBB6B82EFB": "在身后烧掉些什么，向前走便会容易些。",
        "TAN-1CCF54F0A855": "发现雪茄证据（仅限未设置或考虑阶段）。若已进入后续阶段或已经结束，则不执行任何操作，以免被放弃的计划死灰复燃。",
        "TAN-23C50450F85F": "我早就问过了！换个话题吧。",
        "TAN-39048A018D2F": "看来，是我这点小恶习保护了我。烟草的毒——若医生所言不假——会从我受污染的皮肤上驱除微生物……谁都知道，深林畏惧火焰。",
        "TAN-53586C09C3CF": "斯宾塞·霍布森曾被称为“[[防剿局]]里衣着最讲究的男人”。他喜欢量身裁制的衣服，不爱穿从柜子里临时拼凑出来的东西。你可以请裁缝制作新装束，再送到手上——也可以找回过去穿过的衣物。\n\n装束带有性相：有些适合特定气候，有些会让人物心生好感或反感。别穿轻薄装束进雪地。别穿不羁装束去见部委政委。也别穿睡袍吃早餐。\n\n大多数装束还会为[[技艺]]提供少量加成。与启用物品的加成不同，装束加成可以叠加——它总会加在其他加成之上。\n\n斯宾塞只能（或者说，也许是只肯）在可更衣区域换装——在那里，他能避开旁人脱衣，也可能存放替换衣物。凡是能睡觉的房间都算。",
        "TAN-538CFADF4B68": "准许一家“教育剧团”在柏林演出的许可证。它能让尘世蔷薇穿过封锁线，进入诸部委在德国的占领区。由全联盟艺术事务委员会（隶属樱桃部）签发。",
        "TAN-53EA97781BB9": "冰之神殿，琥珀闪耀的鹅卵石，锐利而无知觉的刀，一座珊瑚牢笼……浪涛之后的[[伊斯]]……他们把我在栅栏后拉展开来，痛苦的日子无休无止。伊斯，前所未有之城；海面之上若听见它迟缓的钟声，或许连[[司辰]]也会被敲响……活人不得去伊斯；我去时已非活人。他们从我体内割出[[蠕虫]]时，更不像。剜去我的心时，更不必说。",
        "TAN-55ECA5D62C1B": "不知为何，我总觉得，[q=alias.formal]，您比我更明白这些事？",
        "TAN-594896A54BD4": "痕迹达到 [q=trace] 点：追捕已经停止。",
        "TAN-720E0A3217E9": "[保守秘密] 她提到了你的名字。她真的很不喜欢你。",
        "TAN-7ADBA14EA834": "一个机会……？",
        "TAN-7EF58A488705": "[保守秘密] 她只是提到了你的名字。",
        "TAN-821BAA17053C": news_prefix + old_news[old_news_start:],
        "TAN-91D58F90E38B": "痕迹达到 [q=trace] 点：他们越来越近了。",
        "TAN-92AD32203F2A": "痕迹降到了 [q=trace] 点。我可以稍微松口气——但只能稍微。",
        "TAN-9938ECFEAB32": "智识、启示、金色清明的[[准则]]。灯若太盛，一切都会变得<i>过于</i>清晰。",
        "TAN-E7D224D81649": "<i>找到其中一件，即可了解详情。</i>",
        "TAN-EBB748D122B9": "[[漫宿]]与[[醒时]]从来都不容许伊斯合金存在。也许[[司辰]]当真惧怕它们。",
        "TAN-EEFB1338A830": "[q=trace] 点痕迹！该离开这座城市了……除非他们已经在车站布下眼线。",
        "TAN-EFCF0DBC270A": "[全盘托出] 她，呃，想委托我对你下咒。",
        "TAN-F0D3B0EB96DB": "启用物品只要备在手边，就会为一项[[技艺]]提供修正。你最多可同时启用四件物品，但修正不会叠加——只取最佳的一项。四把锤子不会比一把更好用。\n\n有些物品累赘、危险或拿不出手，会对技艺检定施加<i>负面</i>修正。好消息是，既然永远只取最佳修正，任何一项加成都能抵消任意数量的减益。因此，某件物品若给一项[[技艺]]带来负面修正，任意正面修正都可抵消全部负面效果。",
        "TAN-F26AA074C2CC": "那就太好了。",
    }

    if set(translations) != set(additions):
        missing = sorted(set(additions) - set(translations))
        extra = sorted(set(translations) - set(additions))
        raise SystemExit(f"j.66 supplement key mismatch; missing={missing}, extra={extra}")

    rows = []
    for row_id in sorted(additions):
        source = additions[row_id]["source"]
        target = translations[row_id]
        rows.append(
            {
                "id": row_id,
                "source": source,
                "translation": target,
                "status": "translated",
                "notes": "2026.8.j.66 增量：对照新版资产、上下文与相邻旧译人工复核。",
            }
        )
    OUTPUT.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(f"Wrote {len(rows)} reviewed j.66 additions: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
