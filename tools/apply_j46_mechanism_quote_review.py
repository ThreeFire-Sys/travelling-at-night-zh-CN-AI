#!/usr/bin/env python3
"""Apply the reviewed j.46 mechanism-label and quotation corrections.

All direct edits are guarded by their exact previous translation.  The one
source-aware family rewrite (Fascination) is restricted to rows whose English
source actually contains the mechanism name.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


FIXES = {
    # Predecessor terminology and parallel mechanism labels.
    "TAN-E9B82286FE29": ("迷狂", "入迷"),
    "TAN-1F7987721D0A": ("死于迷狂", "死于入迷"),
    "TAN-A09C75101D29": ("负伤之地", "受创之地"),
    "TAN-FC48CF36E94F": ("短暂", "易逝"),
    "TAN-3AB8685C7326": ("浪荡", "放荡"),
    "TAN-828570C06CA9": ("浪荡", "不羁"),
    "TAN-155562844567": ("必要", "必然"),
    "TAN-F810B6687741": ("新鲜", "清爽"),
    "TAN-0D265B4D96C4": ("汗流不止", "微微冒汗"),
    "TAN-386E53F86C60": ("滴水", "汗流浃背"),
    "TAN-2660022C74D5": ("追寻", "追捕"),

    # Explanations and messages belonging to those same mechanisms.
    "TAN-1907D25168D6": (
        "只适合最放松的场合。比如床上。\n\n大多数人会对浪荡装束作出负面反应，不过少数人会喜欢。",
        "只适合最放松的场合。比如床上。\n\n大多数人会对放荡装束作出负面反应，不过少数人会喜欢。",
    ),
    "TAN-E226DB00821D": (
        "斯宾塞·霍布森曾被称为“防剿局里衣着最讲究的男人”。他喜欢量身裁制的衣服，不爱穿从柜子里临时拼凑出来的东西。你可以请裁缝制作新装束，再送到手上——也可以找回过去穿过的衣物。\n\n装束带有性相：有些适合特定气候，有些会让人物心生好感或反感。别穿轻薄装束进雪地。别穿浪荡装束去见部委政委。也别穿睡袍吃早餐。\n\n大多数装束还会为[[Skills]]提供少量加成。与活动物品的加成不同，装束加成可以叠加——它总会加在其他加成之上。\n\n斯宾塞只能（或者说，也许是只肯）在可更衣区域换装——在那里，他能避开旁人脱衣，也可能存放替换衣物。凡是能睡觉的房间都算。",
        "斯宾塞·霍布森曾被称为“防剿局里衣着最讲究的男人”。他喜欢量身裁制的衣服，不爱穿从柜子里临时拼凑出来的东西。你可以请裁缝制作新装束，再送到手上——也可以找回过去穿过的衣物。\n\n装束带有性相：有些适合特定气候，有些会让人物心生好感或反感。别穿轻薄装束进雪地。别穿不羁装束去见部委政委。也别穿睡袍吃早餐。\n\n大多数装束还会为[[Skills]]提供少量加成。与活动物品的加成不同，装束加成可以叠加——它总会加在其他加成之上。\n\n斯宾塞只能（或者说，也许是只肯）在可更衣区域换装——在那里，他能避开旁人脱衣，也可能存放替换衣物。凡是能睡觉的房间都算。",
    ),
    "TAN-FCD3BEA3B3D7": (
        "套装选得合宜，会不动声色地大幅影响 NPC 的反应。欣赏浪荡打扮的人，通常瞧不上体面装束。",
        "套装选得合宜，会不动声色地大幅影响 NPC 的反应。欣赏不羁打扮的人，通常瞧不上体面装束。",
    ),
    "TAN-95453FB68DA8": ("回到微笑的阳光中。我神清气爽。", "回到微笑的阳光中。我感到清爽。"),
    "TAN-3B2609C755F0": ("热浪像友善的拳头一样击中我。我现在开始出汗了。", "热浪像友善的拳头一样击中我。我开始微微冒汗。"),
    "TAN-81E0F8ED2E52": ("荫凉处遮住了太阳。我已经不再出汗。", "荫凉处遮住了太阳。我不再冒汗。"),
    "TAN-B71900678584": ("热气像友善的一拳迎面打来。我现在湿淋淋的了。", "热气像友善的一拳迎面打来。我已汗流浃背。"),
    "TAN-951D1D1D477E": ("阴凉处遮蔽烈日。我不再湿淋淋的了。", "阴凉处遮蔽烈日。我不再汗流浃背。"),
    "TAN-26972CCCF5C0": ("追寻：部委", "追捕：部委"),
    "TAN-1D01CE51294F": (
        "我需要两样东西：一道带蛾性相的影响，以及一枚必要性信物（一张部委<i>多利</i>券即可）。\n夜游术达到 5 级时，我可以在伤口或门槛制作。\n蠕虫学达到 5 级时，我可以在伤口或暗影之地制作。\n静默术达到 5 级时，我可以在暗影之地或静谧之地制作。\n",
        "我需要两样东西：一道带蛾性相的影响，以及一枚必然信物（一张部委<i>多利</i>券即可）。\n夜游术达到 5 级时，我可以在伤口或门槛制作。\n蠕虫学达到 5 级时，我可以在伤口或暗影之地制作。\n静默术达到 5 级时，我可以在暗影之地或静谧之地制作。\n",
    ),
    "TAN-9FC0A946E297": ("必需之印", "必然之印"),
    "TAN-D25DD717F835": ("承认必需", "承认必然"),

    # Quotation titles, predecessor spellings, and verse layout.
    "TAN-8EF41E6F4B07": ("西班牙", "《西班牙》"),
    "TAN-0259DB9DB890": ("《暗星旅行记》", "《暗星萨伐旅》"),
    "TAN-F831EC9D1508": (
        "《我的事迹、我的力量、我的成就，以及施加于我的种种不公》",
        "《我的事迹、我的力量、我的成就和我所面临的不公》",
    ),
    "TAN-5921A13A9726": ("托名罗伯特·弗拉德", "罗伯特·福路德（？）"),
    "TAN-FEC0210B2239": (
        "\t\t战争已经失败\r\n\t\t条约已经签订\r\n\t\t我没有被捕\r\n\t\t我越过界线\r\n\t\t我没有被捕\r\n\t\t尽管许多人试过\r\n\t\t我活在你们中间，伪装得很好",
        "\t\t战争已经失败\r\n\t\t条约已经签订\r\n\t\t我没有被捕\r\n\t\t我越过界线\r\n\t\t我没有被捕\r\n\t\t尽管许多人试过\r\n\t\t我活在你们中间\r\n\t\t伪装得很好",
    ),
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

    missing = sorted(set(FIXES) - set(by_id))
    if missing:
        raise SystemExit("missing translation IDs: " + ", ".join(missing))

    changed = 0
    touched: set[Path] = set()
    for row_id, (expected, replacement) in FIXES.items():
        path, row = by_id[row_id]
        current = row["translation"]
        if current == replacement:
            continue
        if current != expected:
            raise SystemExit(f"{row_id}: expected {expected!r}, found {current!r}")
        row["translation"] = replacement
        touched.add(path)
        changed += 1

    # Fascination is a predecessor mechanism name.  Cover every authored row
    # that names it, including tooltips and patch notes, without touching the
    # ordinary Chinese words in unrelated English sources.
    family_changed = 0
    note_changed = 0
    for path, rows in chunks.items():
        for row in rows:
            if "fascination" not in row.get("source", "").casefold():
                continue
            current = row.get("translation", "")
            replacement = current.replace("迷狂", "入迷")
            if replacement != current:
                row["translation"] = replacement
                touched.add(path)
                family_changed += 1
            current_note = row.get("notes", "")
            replacement_note = current_note.replace("迷狂", "入迷")
            if replacement_note != current_note:
                row["notes"] = replacement_note
                touched.add(path)
                note_changed += 1

    for path in sorted(touched):
        path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in chunks[path]) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    print(f"direct fixes: {changed}; Fascination-family fixes: {family_changed}; note fixes: {note_changed}; chunks: {len(touched)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
