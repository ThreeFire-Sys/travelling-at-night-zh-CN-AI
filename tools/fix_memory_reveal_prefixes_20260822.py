#!/usr/bin/env python3
"""Unify the visible prefix shared by each My Past item and its revealed footnote."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRANSLATION_ROOTS = (ROOT / "translations_k83", ROOT / "translations_k97")

# link id -> (short row, full row, short visible body, old full prefix, final full prefix)
MEMORIES = {
    "mypasteveofstdahutys1942": (
        "TAN-08A0A31BC6B2", "TAN-53EA97781BB9",
        "冰之神殿，琥珀闪耀的鹅卵石，锐利而无知觉的刀，一座珊瑚牢笼……",
        "冰之神殿，琥珀闪耀的鹅卵石，锐利而无知觉的刀，一座珊瑚牢笼",
        "冰之神殿，琥珀闪耀的鹅卵石，锐利而无知觉的刀，一座珊瑚牢笼",
    ),
    "mypaststbrazenseve": (
        "TAN-296088A7CB15", "TAN-79333F52D60A",
        "我喜欢舞台上画出来的夜：喜欢观众的惊叹，也喜欢那里没有任何不确定。",
        "我喜欢舞台上画出来的夜：喜欢观众的惊叹，也喜欢那里没有任何不确定。",
        "我喜欢舞台上画出来的夜：喜欢观众的惊叹，也喜欢那里没有任何不确定。",
    ),
    "mypaststcatherineseve": (
        "TAN-2C5977F6C6C8", "TAN-5030B3789C6F",
        "我在[[Alexandria]]睁开新的双眼时，最先看见的是斯坦尼斯拉夫的脸。",
        "我在[[Alexandria]]睁开新眼睛时，首先看见的是斯坦尼斯拉夫的脸。",
        "我在[[Alexandria]]睁开新的双眼时，最先看见的是斯坦尼斯拉夫的脸。",
    ),
    "mypastanastasis": (
        "TAN-4C0AAC562F08", "TAN-C1064A0C0F3E",
        "太阳复活节来到布兰库格时，教区长宅仍旧寒冷——那些古老石墙厚得像城堡——而我又没有管家，只得亲自生火……",
        "太阳复活节来到布兰库格时，教区长宅仍旧寒冷——那些古老石墙厚得像城堡——而我又没有管家，只得亲自生火",
        "太阳复活节来到布兰库格时，教区长宅仍旧寒冷——那些古老石墙厚得像城堡——而我又没有管家，只得亲自生火",
    ),
    "mypaststreparataseve": (
        "TAN-583876B9CFF5", "TAN-EEE71F628DEC",
        "战前最后一年，[[Brancrug]]的十月。暮紫的石楠，灰沉低吼的海……",
        "大战前最后一年的十月，[[Brancrug]]。石南呈暮色般的紫，海灰沉沉地低吼。",
        "战前最后一年，[[Brancrug]]的十月。暮紫的石楠，灰沉低吼的海。",
    ),
    "mypaststkallisteseve": (
        "TAN-7A0D0DF57DD3", "TAN-FE0B08BD5BBF",
        "有时，在新月之夜，我会发现自己又回到了蜕衣俱乐部……",
        "有时，在新月之夜，我会发现自己又回到了蜕衣俱乐部",
        "有时，在新月之夜，我会发现自己又回到了蜕衣俱乐部",
    ),
    "mypaststtheophrastuseve": (
        "TAN-816675F0AAB0", "TAN-6BC99E618D6A",
        "我们一行人跺着脚，从巴兹医院冰冷的房间和那座大水池走出来，走进肉市；在那里，我们再次看见那些被体面地藏在皮肤下的东西……",
        "我们跺着脚，从巴兹医院冰冷的房间和那座大水池走进肉市；在那里，再次看见那些被体面地藏在皮肤下的东西。",
        "我们一行人跺着脚，从巴兹医院冰冷的房间和那座大水池走出来，走进肉市；在那里，我们再次看见那些被体面地藏在皮肤下的东西。",
    ),
    "mypaststmelanctheseve": (
        "TAN-85C029F0D8AE", "TAN-855EDB0A9467",
        "我担任本堂神父的第一年，有一个夏日的星期六……",
        "我担任本堂神父的第一年，有一个夏日的星期六",
        "我担任本堂神父的第一年，有一个夏日的星期六",
    ),
    "mypaststrobigoseve": (
        "TAN-9407B804783B", "TAN-09B66232562E",
        "五年服役期满，我离开了军团。我原以为，世上不可能有比鬼林或呼罗珊更糟的地方……",
        "五年服役期满，我离开了军团。我原以为，世上不可能有比鬼林或呼罗珊更糟的地方。",
        "五年服役期满，我离开了军团。我原以为，世上不可能有比鬼林或呼罗珊更糟的地方。",
    ),
    "mypaststagneseve": (
        "TAN-9885F1012D2C", "TAN-B71DA24DCC7F",
        "蠕虫还在我体内时是什么情形，我已记不得多少……",
        "蠕虫还在我体内时是什么情形，我已记不得多少。",
        "蠕虫还在我体内时是什么情形，我已记不得多少。",
    ),
    "mypastststephenseve": (
        "TAN-B591213A99E8", "TAN-220ED2511619",
        "我从孤儿院恶臭的湿冷，走进了小修院洁净、狭窄的寒意……",
        "我从孤儿院恶臭的湿冷，走进了小修院洁净、狭窄的寒意。",
        "我从孤儿院恶臭的湿冷，走进了小修院洁净、狭窄的寒意。",
    ),
    "mypasteveofstjamesthegreater": (
        "TAN-CA705C549DD0", "TAN-EFF08CE225CC",
        "我们与狮之军交战的前一夜，篝火亮得像发带，月亮则是一柄伤痕累累、赤裸的刀……",
        "我们[[Légion]]与狮之军交战的前一夜，篝火亮得像发带，月亮则是一柄伤痕累累、赤裸的刀。",
        "我们[[Légion]]与狮之军交战的前一夜，篝火亮得像发带，月亮则是一柄伤痕累累、赤裸的刀。",
    ),
    "mypaststdjangoseve": (
        "TAN-DD9735BE15C9", "TAN-B8CBC579432C",
        "布里克托普夜总会：可口可乐，热爵士五重奏把世界的心跳奏得砰砰作响……",
        "布里克托普夜总会：可口可乐，热爵士五重奏把世界的心跳奏得砰砰作响",
        "布里克托普夜总会：可口可乐，热爵士五重奏把世界的心跳奏得砰砰作响",
    ),
    "mypastlammastide": (
        "TAN-E12E3B0F24AA", "TAN-D3190771D0DC",
        "我刚和特蕾莎、克里斯托弗喝完酒；回到住处时，[[Bureau]]那些沉默的男人正在等我……",
        "我刚和特蕾莎、克里斯托弗喝完酒；回到住处时，[[Bureau]]那些沉默寡言的男人正在等我。",
        "我刚和特蕾莎、克里斯托弗喝完酒；回到住处时，[[Bureau]]那些沉默的男人正在等我。",
    ),
    "mypastmichaelmas": (
        "TAN-EE2934547E4E", "TAN-982D652FEADD",
        "我在布兰库格度过的第三个、也是最后一个秋天，白昼渐短，风暴拍打海岸……",
        "那是我在布兰库格度过的第三个、也是最后一个秋天。白昼渐短，风暴拍打海岸。",
        "我在布兰库格度过的第三个、也是最后一个秋天，白昼渐短，风暴拍打海岸。",
    ),
    "mypaststoulioseve": (
        "TAN-F3B43EDD649F", "TAN-6B4BC831990F",
        "我是团里最年轻的随军神父，好在沙勒神父一直照应我……",
        "我是团里最年轻的随军神父，但沙勒神父将我收在羽翼之下；",
        "我是团里最年轻的随军神父，好在沙勒神父一直照应我；",
    ),
    "mypastviaticum": (
        "TAN-F8EF2EE3C8AD", "TAN-48E6E8048F00",
        "那些年里，我没有血肉，在边境漂流；薄如雨丝，空如皂泡……",
        "那些年里，我没有血肉，漂流在边境之中；薄如雨丝，空如肥皂泡。",
        "那些年里，我没有血肉，在边境漂流；薄如雨丝，空如皂泡。",
    ),
}


def main() -> None:
    for translation_root in TRANSLATION_ROOTS:
        remaining = {row_id for values in MEMORIES.values() for row_id in values[:2]}
        for path in sorted(translation_root.glob("*.jsonl")):
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
            changed = False
            by_id = {row["id"]: row for row in rows}
            for link_id, (short_id, full_id, short_body, old_full, new_full) in MEMORIES.items():
                short = by_id.get(short_id)
                if short is not None:
                    parts = short["translation"].split("\n\n", 1)
                    if len(parts) != 2:
                        raise SystemExit(f"{path}: {short_id} has no Recall paragraph")
                    short["translation"] = short_body + "\n\n" + parts[1].lstrip()
                    short["notes"] = (
                        "回忆显隐终审：未揭示正文与已揭示回忆共用逐字前缀；"
                        "显隐只能把省略号替换为后续内容，不得改写已显示文字。"
                    )
                    remaining.discard(short_id)
                    changed = True
                full = by_id.get(full_id)
                if full is not None:
                    current = full["translation"]
                    if current.startswith(old_full):
                        full["translation"] = new_full + current[len(old_full) :]
                    elif not current.startswith(new_full):
                        raise SystemExit(f"{path}: unexpected full prefix for {full_id}: {current[:80]!r}")
                    if link_id == "mypasteveofstjamesthegreater":
                        full["notes"] = (
                            "回忆显隐终审：此一英文长版唯一额外插入 of the [[Légion]]；"
                            "中文只相应插入[[Légion]]，其余可见前缀与短版逐字一致。"
                        )
                    else:
                        full["notes"] = (
                            "回忆显隐终审：与未揭示态共用逐字可见前缀；"
                            "揭示效果只追加原本隐藏的后续内容。"
                        )
                    remaining.discard(full_id)
                    changed = True
            if changed:
                path.write_text(
                    "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
                    encoding="utf-8",
                )
                print(f"updated {path.relative_to(ROOT)}")
        if remaining:
            raise SystemExit(
                f"{translation_root.relative_to(ROOT)} memory rows not found: {sorted(remaining)}"
            )
        print(
            f"unified {len(MEMORIES)} memory reveal pairs in "
            f"{translation_root.relative_to(ROOT)}"
        )


if __name__ == "__main__":
    main()
