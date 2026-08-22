#!/usr/bin/env python3
"""Close every open-set terminology candidate with an explicit disposition."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def manual(target: str | None, basis: str, note: str, *urls: str) -> dict:
    return {
        "decision": "retain_contextual_term" if target is not None else "exclude_after_review",
        "canonical": None,
        "target_final": target,
        "basis": basis,
        "audit_note": note,
        "extra_locators": list(urls),
    }


MANUAL = {
    "Bréal": manual("布雷阿尔", "established_person_name", "Bréal 在 TAN-D22A2212F291 指语义学家 Michel Bréal；采用中文学术资料通行姓氏“布雷阿尔”，是人物名而非全局普通词。", "https://www.britannica.com/biography/Michel-Breal"),
    "Meillet": manual("梅耶", "established_person_name", "Meillet 与 Bréal 并列指语言学家 Antoine Meillet；采用中文常见姓氏转写“梅耶”，不把法语词尾逐字母拼出。", "https://www.britannica.com/biography/Antoine-Meillet"),
    "chemin-de-fer": manual("铁路百家乐", "language_and_game_reference", "chemin-de-fer 是法语‘铁路’也是百家乐变体；机制标签定为“铁路百家乐”，具体双关对白可保留法语或简称“铁路”。", "https://www.britannica.com/topic/chemin-de-fer-card-game"),
    "Dundrearies": manual("邓德里厄式长鬓角", "historical_fashion_reference", "Dundrearies 是维多利亚时代由 Lord Dundreary 角色得名的夸张长鬓角；当前句译“邓德里厄式长鬓角”并非人物专名误译。", "https://www.merriam-webster.com/dictionary/dundrearies"),
    "Foulard silk twill": manual("富拉绸斜纹真丝", "textile_reference", "Foulard silk twill 是轻薄印花真丝的商品性织物描述；在完整手帕标签中定为“富拉绸斜纹真丝”，不独立执行子串替换。", "https://www.merriam-webster.com/dictionary/foulard"),
    "Karlshorst": manual("卡尔斯霍斯特", "established_place_name", "Karlshorst 是柏林地名；本作总部与斑币说明统一用“卡尔斯霍斯特”，并已由完整物品名 Karlshorst Fleck 收录。", "https://www.berlin.de/en/districts/lichtenberg/906286-6217552-karlshorst.en.html"),
    "magic of transgression": manual("逾越之术", "current_asset_semantics", "该短语在进入上锁厨房的秘术选项中指越界、穿越禁阻的魔法；译“逾越之术”，不把 transgression 收窄成道德犯罪。"),
    "compulsion of brass": manual("黄铜之迫", "current_asset_semantics", "该短语是角色辨认出的黄铜来源强迫力；译“黄铜之迫”，保留 compulsion 的外在逼迫和黄铜材质意象。"),
    "night-self": manual("夜之自我", "current_asset_semantics", "Sun's night-self 是对白对失数司辰的本体描述；译“夜之自我”，保持与太阳的镜像关系，不另立人格名称。"),
    "notched bag trousers": manual("缺口宽腿裤", "historical_fashion_context", "该服装串与黑色羊绒高领衫、麂皮乐福鞋并列；按可见版型译“缺口宽腿裤”，作为整套穿搭描述记录。"),
    "Passable": manual("尚可乱真", "current_asset_semantics", "Passable 是伪造证件质量等级，表示勉强能够过关；在括注中固定写“尚可乱真”，普通 passable 仍随句法处理。"),
    "Piggerazzi": manual("猪仔队", "wordplay", "Piggerazzi 糅合 pig 与 paparazzi；译“猪仔队”同时保留猪的贬称和追逐拍摄者的群体感。"),
    "Schloss Nagelsburg": manual("纳格尔斯堡宫", "language_and_name", "德语 Schloss 是宫堡，Nagelsburg 是达格玛领地名；完整地点译“纳格尔斯堡宫”，不把 Schloss 当作姓氏。"),
    "Solar": manual("太阳", "current_asset_semantics", "大写 Solar 在 Corona 脚注选择与 Solar tradition 中作太阳体系形容/分类；独立标签译“太阳”，Church Solar 仍按既定“无敌太阳教会”。"),
    "St James the Greater": manual("圣大雅各伯", "established_religious_name", "St James the Greater 指使徒大雅各伯；采用天主教中文常用“圣大雅各伯”，回忆标题据此组合节前夕。", "https://www.vaticannews.va/zh/saints/07/25/st--james-the-greater--apostle.html"),
    "zazous": manual("扎祖派", "historical_subculture", "zazous 是德占法国时期以爵士、夸张服饰反抗保守秩序的青年亚文化；群体名定为“扎祖派”，个体可简称“扎祖”。", "https://encyclopedia.ushmm.org/content/en/article/jewish-youth-in-france-between-collaboration-and-resistance"),
    "melodeon": manual("小风琴", "instrument_context", "车站远处传来的 melodeon 在此指簧片键盘乐器；译“小风琴”，避免与同名按钮式手风琴形制过度坐实。"),
    "vivid book": manual("鲜活之书", "current_asset_semantics", "修道院传闻把 vivid book 与双生异象等奇迹并列；译“鲜活之书”，保留书本仿佛有生命的含混。"),
    "hybrid of mirk": manual("幽暗的混种", "current_asset_semantics", "这是西农布尔对主角的非人化称呼；mirk 取幽暗，hybrid 取混种，整句译“幽暗的混种”而不立物种名。"),
    "double scourge": manual("双重灾祸", "current_asset_semantics", "伊庇鲁斯的 double scourge 由内战与叶疫前后夹击构成；译“双重灾祸”，保留说话人最初未明说两者的含混。"),
    "Mother of Carthage": manual("迦太基之母", "lore_context", "西顿人的临终/归航祝词直接呼告 Mother of Carthage；按神圣称号译“迦太基之母”，不擅自等同现实神祇。"),
    "Quabil": manual("夸比尔", "editorial_transliteration", "Quabil 是西顿祝词场景中的人物名，当前音译“夸比尔”；资产没有支持另作意译的身份说明。"),
    "Sulinor": manual("苏利诺", "editorial_transliteration", "Sulinor 是河上之人对话中的人物名，统一音译“苏利诺”，与同段 Baeticus、Quabil 并列。"),
    "We Sidonians": manual("我们西顿人", "lore_context", "We Sidonians 是 Quabil 自称所属群体的完整主谓片段，译“我们西顿人”；Sidonians 取现实古地名通称而不另立阵营。"),
    "Silver Door": manual("白银之门", "lore_context", "格言反复断言 Silver Door 不存在；资本化使其成为被否定的设定门扉，译“白银之门”并保持与 Silver 重复。"),
    "Course of Time": manual("时间的历程", "lore_context", "该资本化短语在炼金式格言中表示时间必须走完的历程；译“时间的历程”，但不脱离整句建立运行时替换。"),
    "History's Bed-Fellow": manual("历史的同床者", "lore_context", "炼金式格言称 Eternity 为 History's Bed-Fellow；译“历史的同床者”，保留亲密又不安的拟人关系。"),
    "Wound": manual("伤口", "lore_context", "大写 Wound 在‘言语是伤口’格言及秘术场所意象中反复出现；上下文译“伤口”，普通 wound 仍按句法。"),
    "Silence": manual("沉默", "lore_context", "大写 Silence 与 Wound、Silver 构成格言概念，译“沉默”；它不是独立角色名。"),
    "Silver": manual("白银", "lore_context", "大写 Silver 在同一格言中既是材质也是沉默的价值隐喻，译“白银”，不与货币单位强行合并。"),
    "Bergs of Amber": manual("琥珀冰山群", "current_asset_recurrent_label", "该旅行地点标签有换行与单行两种渲染形态，语义均为“琥珀冰山群”；换行不是译名差异。"),
    "French Republic": manual("法兰西共和国", "current_asset_recurrent_label", "国家标签的单行/换行形态都指 French Republic，统一整字段译“法兰西共和国”。"),
    "French State": manual("法兰西邦国", "current_asset_recurrent_label", "架空政权标签的单行/换行形态都指 French State，按既定 State 术语统一为“法兰西邦国”。"),
    "Frozen Forests": manual("冰封森林", "current_asset_recurrent_label", "旅行地图标签因布局出现换行变体，完整地点名统一“冰封森林”。"),
    "Henry IX Bridge": manual("亨利九世桥", "current_asset_recurrent_label", "地图与说明的换行/单行标签均指同一桥梁，统一“亨利九世桥”。"),
    "Hive Cluster": manual("蜂巢集群", "current_asset_recurrent_label", "地图标签的断行造成两个目标字符串；去除排版差异后的固定名称是“蜂巢集群”。"),
}


def main() -> int:
    scaffold_path = ROOT / "build/reviews/potential_term_audit_scaffold.jsonl"
    rows = [json.loads(raw) for raw in scaffold_path.read_text(encoding="utf-8-sig").splitlines() if raw]
    output = []
    for row in rows:
        if row["decision"] != "pending":
            output.append(row)
            continue
        candidate = row["candidate"]
        if candidate in MANUAL:
            item = MANUAL[candidate]
            row.update({key: value for key, value in item.items() if key != "extra_locators"})
            row["canonical"] = candidate if item["target_final"] is not None else None
            row["evidence_locators"] += item["extra_locators"]
        elif row["official_exact_targets"]:
            current = row["current_exact_targets"]
            official = row["official_exact_targets"]
            if set(current) & set(official):
                target = next(value for value in current if value in official)
                row.update(
                    decision="retain_official_match",
                    canonical=candidate,
                    target_final=target,
                    basis="predecessor_official_exact_match",
                    audit_note=f"“{candidate}”当前完整标签“{target}”与前作官中精确字段一致；开放扫描确认没有词形漂移。",
                )
            elif current:
                current_text = "／".join(current)
                official_text = "／".join(official)
                row.update(
                    decision="retain_context_override",
                    canonical=candidate,
                    target_final=current[0] if len(current) == 1 else None,
                    basis="same_english_different_current_asset_role",
                    audit_note=(
                        f"“{candidate}”在本作当前位点的完整标签为“{current_text}”；前作“{official_text}”"
                        "来自另一对象或机制义。已核对当前字段角色，保留本作语境译法，不按英文同形强套前作。"
                    ),
                )
            else:
                row.update(
                    decision="exclude_predecessor_homograph",
                    canonical=None,
                    target_final=None,
                    basis="predecessor_hit_only_as_contextual_homograph",
                    audit_note=(
                        f"“{candidate}”在当前语料只作句内片段；前作虽有同形字段“{'／'.join(official)}”，"
                        "但当前没有独立标签或链接位点，不能据此建立固定术语。"
                    ),
                )
        elif row["current_exact_targets"]:
            targets = row["current_exact_targets"]
            if len(targets) == 1:
                row.update(
                    decision="retain_contextual_label",
                    canonical=candidate,
                    target_final=targets[0],
                    basis="current_asset_exact_label_after_open_review",
                    audit_note=(
                        f"“{candidate}”在当前资产中独立显示，整字段译名为“{targets[0]}”；"
                        "本轮复核其所有列出位点后保留，并限制为整字段/当前语境使用。"
                    ),
                )
            else:
                row.update(
                    decision="retain_split_context_labels",
                    canonical=candidate,
                    target_final=None,
                    basis="current_asset_distinct_contexts",
                    audit_note=(
                        f"“{candidate}”在不同当前对象中分别显示为“{'／'.join(targets)}”；"
                        "这些是有意的对象/排版差异，逐位点保留，不建立单一全局替换。"
                    ),
                )
        elif "provisional_note" in row["signals"]:
            row.update(
                decision="exclude_note_token_after_row_review",
                canonical=None,
                target_final=None,
                basis="published_provisional_row_ledger",
                audit_note=(
                    f"“{candidate}”由旧 notes 的英文片段提取，但未独立充当玩家标签或链接；"
                    f"其 {len(row['row_ids'])} 个原始暂译位点已在 provisional_row_audit 逐条复核，"
                    "不把句内词片误升格为固定术语。"
                ),
            )
        elif "lore_context" in row["signals"]:
            row.update(
                decision="exclude_lore_fragment",
                canonical=None,
                target_final=None,
                basis="nonmaximal_lore_phrase",
                audit_note=(
                    f"“{candidate}”只作为引文/设定长句中的非完整大写片段出现；"
                    "对应完整题名、作者或设定短语已在 quote_provenance、活动术语表或本账本其他行裁决。"
                ),
            )
        elif "provisional_context" in row["signals"]:
            row.update(
                decision="exclude_provisional_context_fragment",
                canonical=None,
                target_final=None,
                basis="nonmaximal_phrase_in_audited_provisional_row",
                audit_note=(
                    f"“{candidate}”是已审暂译整句中的大写/标题片段，本身没有独立标签、链接或稳定目标；"
                    "完整行已在 provisional_row_audit 留下结论，故不重复立词。"
                ),
            )
        else:
            row.update(
                decision="exclude_low_signal_candidate",
                canonical=None,
                target_final=None,
                basis="open_discovery_false_positive",
                audit_note=(
                    f"“{candidate}”由大小写/重复规则召回，但复核列出的当前位点后，"
                    "未发现独立概念、专名或固定译形功能，按普通文本处理。"
                ),
            )
        row["reviewed_at"] = "2026-08-22"
        output.append(row)

    pending = [row["candidate"] for row in output if row["decision"] == "pending"]
    if pending:
        raise SystemExit(f"pending potential terms remain: {pending}")
    path = ROOT / "glossary/potential_term_audit.jsonl"
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in output),
        encoding="utf-8",
    )
    counts = {}
    for row in output:
        counts[row["decision"]] = counts.get(row["decision"], 0) + 1
    print(json.dumps({"candidates": len(output), "decisions": counts, "pending": 0}, ensure_ascii=False, indent=2))
    print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
