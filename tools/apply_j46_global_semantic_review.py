#!/usr/bin/env python3
"""Apply the globally reviewed j.46 terminology and option-context fixes.

Every edit is guarded by its exact previous value.  This makes the review
repeatable and prevents a later source update from being silently overwritten.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


FIXES = {
    # Core Trouble / Passion / Experience mechanism terminology.
    "TAN-AECEF4454428": (
        "纷杂思绪……纷杂思绪。[拥有一点倦意、疼痛、恐惧或着迷后即可入睡——某些更反常的情况下也可以。]",
        "纷杂思绪……纷杂思绪。[拥有一点疲惫、痛苦、恐惧或入迷后即可入睡——某些更反常的情况下也可以。]",
    ),
    "TAN-AD6CF3B17502": (
        "疼痛搅扰我的睡眠，但伤势正在痊愈。[睡眠时，[[Pain]] 会转化为 [[Weariness]]。]",
        "痛苦搅扰我的睡眠，但伤势正在痊愈。[睡眠时，[[Pain]] 会转化为 [[Weariness]]。]",
    ),
    "TAN-E25AF64C3F26": (
        "恐惧与迷恋交战，此消彼长。[[Dread]]与[[Fascination]]会相互抵消。若其中一方多于另一方，它也许会在消退前引发梦境。",
        "恐惧与入迷交战，此消彼长。[[Dread]]与[[Fascination]]会相互抵消。若其中一方多于另一方，它也许会在消退前引发梦境。",
    ),
    "TAN-D96DBEE009A9": (
        " 回忆在回声穹顶下窃窃私语……",
        " 记忆在回声穹顶下窃窃私语……",
    ),
    "TAN-B62D1DCC1209": (
        "花费 [q=cyn:evolveCost] 点冬之经验。",
        "花费 [q=cyn:evolveCost] 份冬之经历。",
    ),
    "TAN-77CD358ADEBF": (
        "对人性的信念已然死去？还是白昼寒意使然？愤世嫉俗的选择总是孤独、谨慎而务实。\n\n[将此心念演化为愤世嫉俗；它会为你的性相池提供启与冬。]\n",
        "对人性的信念已然死去？还是白昼寒意使然？犬儒之选总是孤独、谨慎而务实。\n\n[将此心念演化为犬儒；它会为你的性相池提供启与冬。]\n",
    ),
    "TAN-8C648456E862": (
        "[想来这表示你是个愤世者。虽说人是会变的。就连斯宾塞·霍布森也会。]",
        "[想来这表示你是个犬儒主义者。虽说人是会变的。就连斯宾塞·霍布森也会。]",
    ),
    "TAN-F5DE0E77D6D7": ("愤世嫉俗？", "犬儒？"),
    "TAN-F2C1CB0E38CB": (
        "若说每个修习者与每个学者都有一处相同……好奇之选未必明智。\n\n[将这份心念演化为好奇，为你的性相池贡献灯与启。]\n\n\n",
        "若说每个修习者与每个学者都有一处相同……好奇之选未必明智。\n\n[将这份心念演化为好奇心，为你的性相池贡献灯与启。]\n\n\n",
    ),
    "TAN-00518A3891EB": (
        "[现在，你心怀慈悲。尽管人总会变。斯宾塞·霍布森尤其如此。]",
        "[现在，你心怀同情。尽管人总会变。斯宾塞·霍布森尤其如此。]",
    ),

    # Player choices whose real incoming edge changes the intended action.
    "TAN-2B5F13FB5E90": ("不是吗？", "不行？"),
    "TAN-B42A524F0C82": ("[出去。]", "[起身出浴。]"),
    "TAN-5469721A67C3": ("[告退。]", "[退开。]"),
    "TAN-72A62978AB8D": ("[退出]我不参加。", "[退出] 我不参加。"),
    "TAN-09746E5EAE79": ("[冬]安宁。", "[冬] 安宁。"),
    "TAN-CEF9C350D69A": ("袜子汁？", "洗袜水？"),
    "TAN-1DEEDDE42112": ("甘菊。", "甘菊茶。"),
    "TAN-5F3595CEE64C": (
        "[结束] 暂时没别的事了，医生。",
        "[END] 暂时没别的事了，医生。",
    ),
    "TAN-90AA951048A1": ("[TEST] 直达疗养院", "[测试] 直达疗养院"),
    "TAN-74BF319435C4": (
        "[制作] 旧日技艺，新式工具。",
        "[Craft] 旧日技艺，新式工具。",
    ),
    "TAN-B5686861B043": (
        "[制作] 对赶时间的人来说，已经够神圣了。 ",
        "[Craft] 对赶时间的人来说，已经够神圣了。 ",
    ),
    "TAN-3D5380CD8E2D": ("[制作] 使用它。", "[Craft] 使用它。"),
    "TAN-E9A89E5E0818": ("[制作] 干活。", "[Craft] 干活。"),

    # Identical authored lines must retain identical bodies across state tags.
    "TAN-5E2F46203987": (
        "[潜在] 对我的口味来说，这里有点太轻狂、太放纵了。我更中意安静些的地方。",
        "[潜在] 这地方有点太轻浮、太放纵，不合我的口味。我更喜欢安静些的去处。",
    ),
    "TAN-F3F27DA1E47C": (
        "[已有] 依我的品味，未免太轻佻、太放纵了。我本会更喜欢安静些的地方。",
        "[已有] 这地方有点太轻浮、太放纵，不合我的口味。我更喜欢安静些的去处。",
    ),
    "TAN-625518153F4B": (
        "[潜在] 那些年满是机遇。我本可以留下自己的印记。",
        "[潜在] 那些年满是机遇。我本可以留下自己的印记。",
    ),
    "TAN-E8EF886DEF6D": (
        "[已有] 那些年机会正好。我本可以留下自己的印记。",
        "[已有] 那些年满是机遇。我本可以留下自己的印记。",
    ),
    "TAN-823BEB3E8A28": (
        "[已有] 那股兴奋劲儿本来就维持不了多久。",
        "[已有] 那本就不可能长久。",
    ),
    "TAN-8BE91AC2B47E": (
        "[潜在] 后来战争爆发。如此多人死去、被驱逐、失踪。我无力相助。",
        "[潜在] 后来战争爆发。如此多人死去、被驱逐、失踪。我无力相助。",
    ),
    "TAN-C911E25C78BC": (
        "[已有] 后来战争来了。死的、被流放的、失踪的人太多。我无能为力。",
        "[已有] 后来战争爆发。如此多人死去、被驱逐、失踪。我无力相助。",
    ),
    "TAN-B75A197DABD1": (
        "[已有] 可我从没机会享受黄金时代的里维埃拉。我被困在某个更古老、更寒冷的地方。",
        "[已有] 可我从没机会享受蔚蓝海岸的黄金年代。那时我困在一个更古老、更寒冷的地方。",
    ),
    "TAN-CE1CF5947773": (
        "[潜在] 可我从没机会享受蔚蓝海岸的黄金年代。那时我困在一个更古老、更寒冷的地方。",
        "[潜在] 可我从没机会享受蔚蓝海岸的黄金年代。那时我困在一个更古老、更寒冷的地方。",
    ),
    "TAN-02866E306BC3": (
        "[奉承]我来这里，本来只为一桩小事。如今见到了你，我有了一个好得多的理由。",
        "[奉承] 我来这里只为一桩小事。如今遇见了你，我有了一个好得多的理由。",
    ),
    "TAN-8690166785B9": (
        "[随性] 我来这里，本是为了一个无关紧要的理由。如今遇见了你，我有了一个好得多的理由。",
        "[随性] 我来这里只为一桩小事。如今遇见了你，我有了一个好得多的理由。",
    ),
    "TAN-8CBB8B50F138": (
        "[真心] 而你还得在外面值勤？对不起。",
        "[真心] 而你还得在外面执勤？真遗憾。",
    ),
    "TAN-C0DDDE301A49": (
        "[假意] 你还得在这种天气里执勤？真遗憾。",
        "[假意] 而你还得在外面执勤？真遗憾。",
    ),
    "TAN-E7936849086E": (
        "[真话] 不如说是友好的篝火，阿里斯蒂德。[朝他的烟斗点点头。] 再会。",
        "[真话] 不如说，是一簇友善的篝火，阿里斯蒂德。[朝他的烟斗点点头。] 我们会再见。",
    ),
    "TAN-EEEDFB025249": (
        "[说谎] 倒不如说是一堆友好的篝火，阿里斯蒂德。[朝他的烟斗点头。] 我们会再见。",
        "[说谎] 不如说，是一簇友善的篝火，阿里斯蒂德。[朝他的烟斗点点头。] 我们会再见。",
    ),
    "TAN-081E34F71FAD": (
        "等我得到它，既可留给自己，也可转交别人。",
        "等我得到它，既可留给自己，也可转交别人。",
    ),
    "TAN-B34CA399248A": (
        "等我取得它，可以留给自己，也可以交给别人。",
        "等我得到它，既可留给自己，也可转交别人。",
    ),
    "TAN-4853BE23C64A": (
        "……我不记得了。梦里的文字有时很难看懂。",
        "……我不记得了。梦里的文字有时很难看懂。",
    ),
    "TAN-632DDC46D57A": (
        "……我不记得了。梦里的文字本就难懂。\r",
        "……我不记得了。梦里的文字有时很难看懂。\r",
    ),

    # Cross-domain names and labels.
    "TAN-76FFDF739788": (
        "车站大厅几乎空无一人。这种年头，来里维埃拉的游客已经不多了。",
        "车站大厅几乎空无一人。这种年头，来蔚蓝海岸的游客已经不多了。",
    ),
    "TAN-993755C16816": (
        "昂蒂布。战争降临世界之前，这里曾是里维埃拉甜美的蓝眼睛。游艇、宴会、电影明星的别墅。毕加索曾在这片海边画下他的丑角。 ",
        "昂蒂布。战争降临世界之前，这里曾是蔚蓝海岸甜美的蓝眼睛。游艇、宴会、电影明星的别墅。毕加索曾在这片海边画下他的丑角。 ",
    ),
    "TAN-00F478475335": ("乌布", "乌布"),
    "TAN-7A0E132B3C00": ("于布。", "乌布。"),
    "TAN-222D878513CC": ("脚注隐微度", "脚注显隐程度"),
    "TAN-E3B23235A2B8": ("脚注显隐程度", "脚注显隐程度"),
    "TAN-F4DC389C93BC": ("叶之\n瘟疫", "叶疫"),
    "TAN-C57F4FE24EE8": ("展示过秘术知识", "展示过秘学知识"),
    "TAN-AA8948D6FC24": ("我已抵达米玛塔，也找到了罗莎·蒙迪。", "我已抵达米马塔，也找到了罗莎·蒙迪。"),
    "TAN-CD8AE21A77BD": ("喝洋甘菊茶", "喝甘菊茶"),
    "TAN-96438CB20557": (
        "[支付一千弗朗西斯克，让文森特坐三等车] 我们米马塔见。",
        "[支付一千弗朗西斯克，让文森特乘三等座] 米马塔见。",
    ),
    "TAN-1591FE7C7824": (
        "我们正在和 Edouarde 交谈，所以若检定 Charm，rel_ed 应作为修正值出现；若检定 Bosk，则不应出现",
        "我们正在和埃杜阿尔德交谈，所以若检定魅力，rel_ed 应作为修正值出现；若检定丛林学，则不应出现",
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--translations",
        type=Path,
        default=Path("build/translations_j46_candidate"),
    )
    args = parser.parse_args()

    found: dict[str, tuple[Path, dict]] = {}
    for path in sorted(args.translations.glob("*.jsonl")):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
        for row in rows:
            if row.get("id") in FIXES:
                found[row["id"]] = (path, row)

    missing = sorted(set(FIXES) - set(found))
    if missing:
        raise SystemExit("missing translation IDs: " + ", ".join(missing))

    touched: set[Path] = set()
    changed = 0
    for translation_id, (path, row) in found.items():
        expected, replacement = FIXES[translation_id]
        current = row.get("translation")
        if current == replacement:
            continue
        if current != expected:
            raise SystemExit(
                f"{translation_id}: expected {expected!r}, found {current!r}"
            )
        row["translation"] = replacement
        touched.add(path)
        changed += 1

    # Rewrite only chunks that contain an affected row, retaining row order.
    for path in touched:
        rows = []
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            row = json.loads(line)
            if row.get("id") in found:
                row = found[row["id"]][1]
            rows.append(row)
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    print(f"reviewed={len(FIXES)} changed={changed} chunks={len(touched)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
