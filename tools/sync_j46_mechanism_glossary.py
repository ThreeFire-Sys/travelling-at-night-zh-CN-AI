#!/usr/bin/env python3
"""Audit every player-facing mechanism label against the curated glossary.

The scope is deliberately taxonomic: parallel rule labels are included; item,
recipe, person and place names are not treated as mechanism terminology merely
because their assets also have a ``_label`` field.  This tool deliberately does
not invent provenance for newly discovered labels: every new concept needs its
own asset evidence, naming argument and rejected alternatives before admission.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


FAMILY_SPECS = {
    "ExperienceQuality": {
        "category": "经历",
        "reference_label": "Weather Factory：角色成长与心念",
        "reference_url": "https://weatherfactory.biz/who-are-you-hollow-man/",
        "evidence": "j.46 将九种准则经历列为同一 ExperienceQuality 标签族；官方开发日志确认心念、技艺与性相池共同构成角色成长系统。",
        "rationale": "保留前作单字准则译名，以“X之经历”形成可扫读的九项并列结构。",
        "alternatives": "“经验”偏数值；“阅历”过于人生化；省略“之”会破坏与准则名的边界。",
        "comparison_label": "秘史 Wiki：准则",
        "comparison_url": "https://mansus.huijiwiki.com/wiki/准则",
    },
    "Travelling.Opportunities.Venue": {
        "category": "场所",
        "reference_label": "Weather Factory：Turn This Opportunity Yes",
        "reference_url": "https://weatherfactory.biz/turn-this-opportunity-yes/",
        "evidence": "官方开发日志说明制作必须在特定物理地点进行，并以 Holy Place 为例；j.46 资产列出完整 Venue 标签族。",
        "rationale": "译名同时反映空间性质和制作门槛，并保持“X之地／炉边／门槛”等界面短标签风格。",
        "alternatives": "不统一机械添加“场所”；逐项依空间意象命名，避免“神圣场所”等冗长直译。",
    },
    "Travelling.PCQualities.Aspect": {
        "category": "性相",
        "reference_label": "Weather Factory：Who are you, Hollow Man?",
        "reference_url": "https://weatherfactory.biz/who-are-you-hollow-man/",
        "evidence": "官方开发日志确认 Aspect Pool 及装束、技艺、心念对性相的共同使用；j.46 资产给出完整并列标签。",
        "rationale": "前作准则与既有性相沿用 Wiki 译名；本作新性相依据用途说明定名并保持短标签。",
        "alternatives": "不把 Aspect 误作“准则”；不以脱离资产说明的字典首义覆盖机制义。",
    },
    "Travelling.PCQualities.Career": {
        "category": "职业",
        "reference_label": "Weather Factory：Who are you, Hollow Man?",
        "reference_url": "https://weatherfactory.biz/who-are-you-hollow-man/",
        "evidence": "官方开发日志说明开局先选 Career，再由其影响可用心念和技艺；j.46 资产列出四个可玩职业。",
        "rationale": "职业名按人物身份而非抽象路线翻译；前作确有同一职业者时沿用 Wiki 定名。",
        "alternatives": "不机械套用总机制名“职涯”到具体身份；避免无设定依据的职业扩写。",
    },
    "Travelling.PCQualities.ConditionQuality": {
        "category": "状态",
        "reference_label": "Weather Factory：Chrysophoria",
        "reference_url": "https://weatherfactory.biz/chrysophoria/",
        "evidence": "官方开发日志确认装束与麻烦会施加状态，并点名 Agonies、Despair、Chrysolepsis；j.46 资产列出完整状态阶梯。",
        "rationale": "同一冷热、痕迹和危险阶梯按强度递进命名，标签与进入／退出提示保持同词根。",
        "alternatives": "不按孤立字面翻译而破坏强度序列；不把状态写成完整句子。",
    },
    "Travelling.PCQualities.Passion": {
        "category": "心念",
        "reference_label": "Weather Factory：Who are you, Hollow Man?",
        "reference_url": "https://weatherfactory.biz/who-are-you-hollow-man/",
        "evidence": "官方开发日志把 Passions 定义为可由选择和游玩风格取得、最多持有三项的角色驱动力；j.46 给出完整心念族。",
        "rationale": "各项译作人格驱力名词，与前作单张能力卡 Passion“激情”明确区分。",
        "alternatives": "不统称“激情”；不把各项改写成长句或道德评价。",
        "comparison_label": "《密教模拟器》Wiki：激情",
        "comparison_url": "https://cultist.huijiwiki.com/wiki/激情",
    },
    "Travelling.PCQualities.Sign": {
        "category": "征象",
        "reference_label": "Weather Factory：Scapin’s Sickness",
        "reference_url": "https://weatherfactory.biz/scapins-sickness/",
        "evidence": "官方开发日志说明征象关联太阳即兴喜剧，并确认 Fracasse、Cassandro、Metaphraste 等角色原型；j.46 列出九项同构病名。",
        "rationale": "保留角色名，以“之患／疾／苦”等近义病痛词重现英文头韵式并列命名。",
        "alternatives": "不把人名意译；不强求中文首字押韵而牺牲辨识度。",
    },
    "Travelling.PCQualities.Skill": {
        "category": "技艺",
        "reference_label": "Weather Factory：INCREASE WITH 40 HEART",
        "reference_url": "https://weatherfactory.biz/increase-with-40-heart/",
        "evidence": "官方开发日志明确区分从《司辰之书》回归的技艺与本作新增技艺，并列出本作专属项；j.46 给出试玩版完整技艺族。",
        "rationale": "回归的伟大之术严格沿用 Wiki 译名；新技艺按角色能力说明定名。",
        "alternatives": "不把回归术名改成普通技能；不因 Steam 总称“技能”而覆盖已确认的项目裁决“技艺”。",
        "comparison_label": "《司辰之书》Wiki：伟大之术",
        "comparison_url": "https://boh.huijiwiki.com/wiki/伟大之术",
    },
    "Travelling.PCQualities.SkillCheckDifficulty": {
        "category": "检定难度",
        "reference_label": "Weather Factory：INCREASE WITH 40 HEART",
        "reference_url": "https://weatherfactory.biz/increase-with-40-heart/",
        "evidence": "官方开发日志说明技艺检定、失败与性相池挽救；j.46 资产提供十一档正式难度标签。",
        "rationale": "按实际阈值从“微不足道”到“难以置信”递进，兼顾 UI 长度和语气。",
        "alternatives": "不强制每档都以“困难”结尾；不把内部测试项 Semi 纳入正式阶梯。",
    },
    "Travelling.PCQualities.SkillCheckResultQuality": {
        "category": "检定结果",
        "reference_label": "Weather Factory：INCREASE WITH 40 HEART",
        "reference_url": "https://weatherfactory.biz/increase-with-40-heart/",
        "evidence": "官方开发日志讨论技艺检定的 success、fail 与挽救机制；j.46 结果族由 Success、Failure 两项构成。",
        "rationale": "采用界面最直接的“成功／失败”，与相关提示保持一致。",
        "alternatives": "“胜利／落败”会误成战斗结果；“通过／未通过”弱化叙事语气。",
    },
}

EXCLUSIONS = {
    ("Travelling.PCQualities.Career", "NullCareer"): "内部空职业哨兵，不向玩家呈现",
    ("Travelling.PCQualities.Passion", "NullPassion"): "内部空心念哨兵，不向玩家呈现",
    ("Travelling.PCQualities.Skill", "NullSkill"): "内部空技艺哨兵，不向玩家呈现",
    ("Travelling.PCQualities.SkillCheckDifficulty", "Semi"): "描述仅为 test 的开发测试占位，不属于正式难度阶梯",
}

CORE_TERMS = {
    "Experience": ("经历", "经历", "Experiences"),
    "Venue": ("场所", "场所", "Venues"),
    "Difficulty": ("难度", "检定难度", None),
    "Pain": ("痛苦", "麻烦", None),
    "Weariness": ("疲惫", "麻烦", None),
}

PREDECESSOR_RECORDS = {
    "Dread": {
        "aliases": [], "target": "恐惧", "category": "麻烦",
        "reference_label": "《密教模拟器》Wiki：恐惧", "reference_url": "https://cultist.huijiwiki.com/wiki/恐惧",
        "evidence": "Wiki 词条以卡牌 id dread 对列“恐惧”。", "rationale": "本作沿用同一危险机制词，不另造译名。",
    },
    "Fascination": {
        "aliases": [], "target": "入迷", "category": "麻烦",
        "reference_label": "《密教模拟器》Wiki：入迷", "reference_url": "https://cultist.huijiwiki.com/wiki/入迷",
        "evidence": "Wiki 的恐惧、事件等页面把 fascination 机制稳定译为“入迷”。", "rationale": "本作继续让它与 Dread 相互抵消，机制连续，故撤销早期“迷狂”。",
    },
    "Influence": {
        "aliases": [], "target": "影响", "category": "性相",
        "reference_label": "《密教模拟器》Wiki：影响", "reference_url": "https://cultist.huijiwiki.com/wiki/影响",
        "evidence": "Wiki 以性相 id influence 对列“影响”，描述亦与本作的反响、共鸣、调和相承。", "rationale": "机制和措辞连续，沿用前作。",
    },
    "Memory": {
        "aliases": ["Memories"], "target": "记忆", "category": "机制",
        "reference_label": "《司辰之书》Wiki：回忆分类", "reference_url": "https://boh.huijiwiki.com/wiki/分类:性相：回忆",
        "evidence": "Wiki 分类列出大量“回忆：X”卡牌，并将 Memory 作为既有资源类别；本作沿用“记忆”作为可结晶、可制作的总称。", "rationale": "不再误列为本作新词；单复数同译“记忆”。",
    },
    "Trace": {
        "aliases": ["Traces"], "target": "痕迹", "category": "麻烦",
        "reference_label": "《密教模拟器》Wiki：流亡者／痕迹", "reference_url": "https://cultist.huijiwiki.com/wiki/流亡者/痕迹",
        "evidence": "《流亡者》Wiki 机制页以“痕迹”记录追兵定位资源；本作官方开发日志也明确说明 Traces 来自 EXILE。", "rationale": "机制直接回归，单复数沿用“痕迹”。",
    },
    "Physician": {
        "aliases": [], "target": "医师", "category": "职业",
        "reference_label": "《密教模拟器》Wiki：职业", "reference_url": "https://cultist.huijiwiki.com/wiki/职业",
        "evidence": "《密教模拟器》职业页明确列出 Physician“医师”。", "rationale": "本作可选职业与前作同名，沿用既定身份名。",
    },
}


def base_script(value: str) -> str:
    return value.split(",", 1)[0]


def load_translations(directory: Path) -> dict[str, str]:
    result = {}
    for path in sorted(directory.glob("*.jsonl")):
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            if raw:
                row = json.loads(raw)
                result[row["id"]] = row["translation"]
    return result


def load_label_rows(worklist: Path, translations: dict[str, str]) -> list[dict]:
    result = []
    for raw in worklist.read_text(encoding="utf-8-sig").splitlines():
        if not raw:
            continue
        row = json.loads(raw)
        for context in row.get("contexts", []):
            script = base_script(context.get("script", ""))
            if script in FAMILY_SPECS and context.get("field_path") == "_label":
                result.append({"id": row["id"], "source": row["source"], "target": translations[row["id"]], "script": script})
                break
    return result


def load_provenance(directory: Path) -> dict[str, list[dict]]:
    result = {}
    for name in ("predecessor", "travelling_new", "real_world", "editorial"):
        path = directory / f"{name}.jsonl"
        result[name] = [json.loads(raw) for raw in path.read_text(encoding="utf-8-sig").splitlines() if raw.strip()]
    return result


def covered_terms(records: dict[str, list[dict]]) -> set[str]:
    return {term for rows in records.values() for row in rows for term in [row["canonical"], *row.get("aliases", [])]}


def new_record(source: str, target: str, spec: dict) -> dict:
    raise SystemExit(
        f"{source!r} -> {target!r} lacks curated one-term-one-research provenance; "
        "add a term-specific record to glossary/provenance before rerunning"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worklist", type=Path, default=Path("build/worklist_k97/worklist.jsonl"))
    parser.add_argument("--translations", type=Path, default=Path("translations_k97"))
    parser.add_argument("--glossary", type=Path, default=Path("glossary/glossary.csv"))
    parser.add_argument("--provenance-dir", type=Path, default=Path("glossary/provenance"))
    args = parser.parse_args()

    translations = load_translations(args.translations)
    labels = load_label_rows(args.worklist, translations)
    records = load_provenance(args.provenance_dir)

    # Memories was previously misclassified as a Travelling-new mechanism.
    records["travelling_new"] = [row for row in records["travelling_new"] if row["canonical"] != "Memories"]

    # Record semantic redefinitions explicitly, with the predecessor homograph
    # available for reviewers without misclassifying the new mechanism.
    for row in records["travelling_new"]:
        if row["canonical"] == "Passion":
            row["evidence"] = "同作官方简中把角色驱动力 Passions 定名为“心念”；官方开发日志说明它可多选、可随选择演化。前作同形 Passion 是单张基础能力卡“激情”，并非本作这一机制。"
            row["comparison_label"] = "《密教模拟器》Wiki：激情"
            row["comparison_url"] = "https://cultist.huijiwiki.com/wiki/激情"
        elif row["canonical"] == "Career":
            row["evidence"] = "同作官方简中把角色出身／职业路线 Career 定名为“职涯”；本作以它统摄过去经历和开局技艺。前作已有“职业”类别，但不是同一角色创建机制。"
            row["comparison_label"] = "《密教模拟器》Wiki：职业"
            row["comparison_url"] = "https://cultist.huijiwiki.com/wiki/职业"

    # Replace this script's managed predecessor records so reruns are
    # idempotent while still rejecting overlap with unrelated records.
    managed_predecessors = set(PREDECESSOR_RECORDS)
    records["predecessor"] = [
        row for row in records["predecessor"] if row["canonical"] not in managed_predecessors
    ]
    covered = covered_terms(records)
    for canonical, data in PREDECESSOR_RECORDS.items():
        for term in [canonical, *data["aliases"]]:
            if term in covered:
                raise SystemExit(f"predecessor migration would duplicate provenance: {term}")
        records["predecessor"].append({
            "canonical": canonical, "aliases": data["aliases"],
            "reference_label": data["reference_label"], "reference_url": data["reference_url"],
            "evidence": data["evidence"], "rationale": data["rationale"], "status": "verified",
        })
    covered = covered_terms(records)

    # Read the existing flat glossary once, then add only absent exact terms.
    with args.glossary.open("r", encoding="utf-8-sig", newline="") as handle:
        glossary_rows = list(csv.DictReader(handle))
        fieldnames = list(glossary_rows[0])
    glossary = {row["source_en"]: row for row in glossary_rows}

    def add_glossary(source: str, target: str, category: str, notes: str) -> None:
        if source in glossary:
            if glossary[source]["target_zh"] != target:
                raise SystemExit(f"glossary conflict for {source}: {glossary[source]['target_zh']} != {target}")
            return
        row = {"source_en": source, "target_zh": target, "type": category, "case_sensitive": "true", "confidence": "high", "notes": notes}
        glossary[source] = row
        glossary_rows.append(row)

    for canonical, data in PREDECESSOR_RECORDS.items():
        add_glossary(canonical, data["target"], data["category"], "前作 Wiki 既有译名；见 USER_GLOSSARY 考据")
        for alias in data["aliases"]:
            add_glossary(alias, data["target"], data["category"], "前作 Wiki 既有译名；单复数同译")

    for canonical, (target, category, alias) in CORE_TERMS.items():
        add_glossary(canonical, target, category, "本作玩家可见机制总称")
        if alias:
            add_glossary(alias, target, category, "本作玩家可见机制总称；单复数同译")
        if canonical not in covered:
            if canonical == "Venue":
                spec = FAMILY_SPECS["Travelling.Opportunities.Venue"]
            elif canonical in {"Pain", "Weariness"}:
                spec = {
                    **FAMILY_SPECS["Travelling.PCQualities.ConditionQuality"],
                    "reference_label": "Weather Factory：Turn This Opportunity Yes",
                    "reference_url": "https://weatherfactory.biz/turn-this-opportunity-yes/",
                    "evidence": "官方开发日志把 Pain、Weariness 列为本作 Troubles；其中明确说明 Weariness 是在 EXILE 式系统上新增的麻烦。",
                }
            else:
                spec = FAMILY_SPECS["ExperienceQuality"] if canonical == "Experience" else FAMILY_SPECS["Travelling.PCQualities.SkillCheckDifficulty"]
            record = new_record(canonical, target, spec)
            if alias:
                record["aliases"] = [alias]
            records["travelling_new"].append(record)
            covered.update([canonical, *([alias] if alias else [])])

    added_labels = 0
    unprovenanced_labels = []
    for label in labels:
        key = (label["script"], label["source"])
        if key in EXCLUSIONS:
            continue
        if label["source"] not in covered:
            unprovenanced_labels.append(f"{label['script']}::{label['source']} -> {label['target']}")
            continue
        add_glossary(
            label["source"], label["target"], FAMILY_SPECS[label["script"]]["category"],
            "逐词证据见 glossary/provenance 与 USER_GLOSSARY",
        )

    if unprovenanced_labels:
        raise SystemExit(
            "new mechanism labels require manual one-term-one-research provenance:\n- "
            + "\n- ".join(unprovenanced_labels)
        )

    glossary_rows.sort(key=lambda row: row["source_en"].casefold())
    with args.glossary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(glossary_rows)

    for origin, rows in records.items():
        rows.sort(key=lambda row: row["canonical"].casefold())
        path = args.provenance_dir / f"{origin}.jsonl"
        path.write_text("\n".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in rows) + "\n", encoding="utf-8", newline="\n")

    print(f"mechanism labels: {len(labels)}; exclusions: {len(EXCLUSIONS)}; newly provenanced labels: {added_labels}; glossary rows: {len(glossary_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
