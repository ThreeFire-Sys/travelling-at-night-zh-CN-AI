#!/usr/bin/env python3
"""Apply the explicitly reviewed terminology final-audit verdicts.

This is intentionally assertion-heavy and site-aware.  It never performs a
blind global Chinese replacement: ordinary ``honour`` and culinary ``louche``
remain untouched while their mechanism labels change.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORIGINS = ("predecessor", "travelling_new", "real_world", "editorial")

PROVENANCE_RESEARCH = {
    "bisclavret": {
        "reference_label": "《司辰之书》现行官中：狼骑结印",
        "reference_url": "https://boh.huijiwiki.com/wiki/狼骑结印",
        "evidence": "本机《司辰之书》core/loc_zh-hans 同 ID `bisclavrets.knot` 对照：Bisclavret's Knot 定名“狼骑结印”，说明又把 bisclavret 释为“狼骑”。",
        "rationale": "本作同一物品与称谓统一为“狼骑／狼骑结印”，服从现行前作官中，不再沿用旧 Wiki 音译。",
    },
    "Sisterhood of the Triple Knot": {
        "evidence": "本机《司辰之书》官中在对应组织全称处稳定使用“三重绳结姐妹会”，语境简称则为“绳结姐妹会”。",
        "rationale": "全称译“三重绳结姐妹会”，逐项保留 Triple、Knot、Sisterhood；撤销省略“绳结”的“三结姐妹会”。",
    },
    "St Melancthe": {
        "evidence": "本机《司辰之书》官中《圣梅兰瑟》、圣物与书目同一人物均使用“梅兰瑟”。",
        "rationale": "沿用现行官中“圣梅兰瑟”，撤销旧稿“圣梅兰克忒”。",
    },
    "Honour": {
        "evidence": "试玩版专属说明将 Honour 界定为无人注视时仍选择正确而非容易之事，关联自律、诚实与礼节。",
        "rationale": "心念名定为“操守”，突出内在伦理准则；普通 honour 的“荣幸／荣誉／尊崇”仍按句法翻译。",
        "alternatives": "“荣誉”偏外在名誉，也与门槛军团格言 Honneur 重叠；“气节”范围较窄且语体过古。",
    },
    "Louche": {
        "evidence": "装束专属说明称它只适合床笫等极放松场合，多数人物会反感，少数人物会欣赏。",
        "rationale": "装束性相译“轻佻”，自然描述衣着逾越体面规范；普通法语烹饪词 louche 仍按“乳浊”处理。",
        "alternatives": "“放荡”更常评判人的生活方式，用来直接修饰装束生硬；“邋遢”误成不整洁。",
    },
    "Quicken": {
        "evidence": "专属说明以 enliven、invigorate、awaken 界定 Quicken；同一界面已有 Quicken Item“活化物品”。",
        "rationale": "统一译“活化”，采用现成中文并保持标签、物品类型与说明同词根。",
        "alternatives": "旧译“催活”是无必要生造；“加速”取错常用义；“复苏”预设对象曾经死亡。",
    },
    "retenebration": {
        "evidence": "原文明确称 retenebration 为须由罗马批准、使神父重归世俗身份的 formal process；作者自造词以 re- 与 tenebrae（幽暗）构成。",
        "rationale": "定名“复晦”，保留复归幽暗的教会隐喻，同时服从“程序”而非仪式的语义。",
        "alternatives": "旧译“复晦礼”无据添加 rite；“还俗”虽明白，却抹掉作者刻意自造的光暗术语。",
    },
    "scrine": {
        "reference_label": "Collins / Wiktionary：scrine",
        "reference_url": "https://www.collinsdictionary.com/dictionary/english/scrine",
        "evidence": "scrine 是古语 shrine/chest，可指神龛、圣物匣或珍物箱；本作中它是无形灵体在醒时寄居显现的容器，scrineway 是连接该容器的通道。",
        "rationale": "译“灵龛／龛道”：前者是现成中文且兼具灵体与容器义，后者保留同一“龛”词根并表达通路。",
        "alternatives": "旧译“龛壳”属于无必要生造；“圣龛”过早断言其神圣性；纯音译无词义信息。",
    },
    "Weariness Collapse": {
        "evidence": "状态说明明确写疲惫达到 10 时斯宾塞会倒下，降低疲惫并增加痛苦；它不是死亡或昏厥判定。",
        "rationale": "状态名定为“累倒”，是自然、短促的中文结果标签；上位机制“疲惫”已在数值栏显示。",
        "alternatives": "“疲惫倒下”是为机械保留词根而拼出的生硬短语；“疲惫崩溃”是英语名词堆叠；“昏厥”擅加失去意识。",
    },
}

TRANSLATION_UPDATES = {
    "TAN-218D1B640B80": (
        "名为<i>狼骑</i>的半人山童之印。印记带着疟疾般的生命力微微颤抖。",
        "终审：沿用现行《司辰之书》官中 bisclavret“狼骑”。",
    ),
    "TAN-F058FA20CA49": ("狼骑结印", "终审：沿用现行《司辰之书》同一物品定名“狼骑结印”。"),
    "TAN-56ECD27ECD8C": (
        "出于操守的选择，是努力去做正确的事，而不是容易的事——它未必明智，也未必温和。\n\n[将这份心念演化为操守，为你的性相池贡献心与灯。]\n\n",
        "终审：Honour 心念依据内在伦理说明定名“操守”；保留段落。",
    ),
    "TAN-05CCE0DDC1A0": (None, "终审：机制心念 Honour 定名“操守”；普通 honour 不受影响。"),
    "TAN-9FF19AE48E25": ("操守", "终审：心念说明强调无人注视时的内在伦理，定名“操守”。"),
    "TAN-1907D25168D6": (
        "只适合最放松的场合。比如床上。\n\n大多数人会对轻佻装束作出负面反应，不过少数人会喜欢。",
        "终审：Louche 作为装束观感译“轻佻”；保留两段。",
    ),
    "TAN-3AB8685C7326": ("轻佻", "终审：装束性相 Louche 定名“轻佻”。"),
    "TAN-631428921E7C": ("活化", "终审：与 Quicken Item“活化物品”及专属说明统一。"),
    "TAN-042B762DE54F": (
        "不。我的意思是，有一道正式程序——复晦——能让我重归世俗身份。那得由罗马批准。我想手续从未真正办妥。只要我不以神父自居，他们大概也懒得追究。",
        "终审：retenebration 是正式程序而非仪式，定名“复晦”。",
    ),
    "TAN-19D5E052C6AF": (
        "早先，你想让我窥看灵龛。是为了认识我，对吧？我愿意让你如愿。",
        "终审：scrine 依古语 shrine/chest 及灵体容器语境定名“灵龛”。",
    ),
    "TAN-4B25024CB741": (
        "被困在这座灵龛里，你一定很无聊。希望这能给你解解闷。",
        "终审：scrine 定名“灵龛”。",
    ),
    "TAN-8B99CDC46B55": (
        "……而你被困在醒时的一座灵龛里，因为漫宿那边有人毁掉了你的龛道。任何辉耀者都不会冒险在冰这样无常之物的灵龛里停留这么久。",
        "终审：scrine／scrineway 定名“灵龛／龛道”，保留共同词根。",
    ),
    "TAN-A276791A17BA": (
        "你小心提防是明智的，我那摇曳的微光。但西农布尔已非昔日。靠近些，靠近些，望进灵龛……西农布尔会把她的光赐给你。",
        "终审：scrine 定名“灵龛”；保留重复召唤节奏。",
    ),
    "TAN-BA492A4464F3": ("[走近，望入灵龛。]", "终审：scrine 定名“灵龛”。"),
    "TAN-E38AE0D71891": ("……在这里显现于一座……冰制灵龛里？", "终审：scrine 定名“灵龛”。"),
    "TAN-1460CB152CE9": ("累倒", "终审：采用自然结果标签；不为机械词根检查保留生硬的“疲惫倒下”。"),
}


def main() -> int:
    ledger_path = ROOT / "glossary/final_term_audit.jsonl"
    ledger = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8-sig").splitlines() if line]
    by_term = {row["canonical"]: row for row in ledger}

    glossary_path = ROOT / "glossary/glossary.csv"
    with glossary_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0])
    original = {row["source_en"]: row for row in rows}
    retired = {row["canonical"] for row in ledger if row["decision"] == "retire"}
    rows = [row for row in rows if row["source_en"] not in retired]
    current = {row["source_en"]: row for row in rows}

    for verdict in ledger:
        if verdict["decision"] == "retire":
            continue
        canonical = verdict["canonical"]
        if canonical not in current:
            raise SystemExit(f"missing glossary canonical {canonical}")
        current[canonical]["target_zh"] = verdict["target_final"]
        current[canonical]["notes"] = "终审：" + verdict["audit_note"]
        for alias, target in verdict.get("alias_targets_final", {}).items():
            if alias in current:
                current[alias]["target_zh"] = target
                current[alias]["notes"] = f"终审：{canonical} 的词形变体"
            else:
                row = {
                    "source_en": alias,
                    "target_zh": target,
                    "type": current[canonical]["type"],
                    "case_sensitive": current[canonical]["case_sensitive"],
                    "confidence": current[canonical]["confidence"],
                    "notes": f"终审：{canonical} 的词形变体",
                }
                rows.append(row)
                current[alias] = row

    with glossary_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    for origin in ORIGINS:
        path = ROOT / f"glossary/provenance/{origin}.jsonl"
        records = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
        updated = []
        for record in records:
            canonical = record["canonical"]
            verdict = by_term[canonical]
            if verdict["decision"] == "retire":
                continue
            record["aliases"] = list(verdict.get("alias_targets_final", {}))
            if canonical in PROVENANCE_RESEARCH:
                record.update(PROVENANCE_RESEARCH[canonical])
            updated.append(record)
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in updated),
            encoding="utf-8",
        )

    seen = set()
    for path in sorted((ROOT / "translations_k83").glob("chunk_*.jsonl")):
        translation_rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
        changed = False
        for row in translation_rows:
            update = TRANSLATION_UPDATES.get(row["id"])
            if update is None:
                continue
            target, notes = update
            if row["id"] == "TAN-05CCE0DDC1A0":
                old = "愤怒可以演化为荣誉或野心"
                if old not in row["translation"]:
                    raise SystemExit(f"{row['id']}: expected mechanism wording changed")
                row["translation"] = row["translation"].replace(old, "愤怒可以演化为操守或野心")
            else:
                row["translation"] = target
            row["notes"] = notes
            seen.add(row["id"])
            changed = True
        if changed:
            path.write_text(
                "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in translation_rows),
                encoding="utf-8",
            )
    missing = sorted(set(TRANSLATION_UPDATES) - seen)
    if missing:
        raise SystemExit(f"translation ids missing: {missing}")

    print(
        f"applied {sum(row['decision']=='change' for row in ledger)} target changes; "
        f"retired {len(retired)} concepts; updated {len(seen)} translation rows"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
