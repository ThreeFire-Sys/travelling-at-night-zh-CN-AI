#!/usr/bin/env python3
"""Build a read-only predecessor terminology consistency audit.

This script reads the merged review catalog and emits review suggestions only.
It never changes translation work files.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "build" / "merged" / "review_catalog.jsonl"
OUTPUT = ROOT / "build" / "reviews" / "predecessor_consistency.jsonl"
SUMMARY = ROOT / "build" / "reviews" / "predecessor_consistency_summary.md"


def load_catalog() -> dict[str, dict]:
    rows: dict[str, dict] = {}
    with CATALOG.open("r", encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            rows[row["id"]] = row
    return rows


def main() -> None:
    catalog = load_catalog()
    findings: list[dict[str, str]] = []

    def add(
        row_id: str,
        recommended: str,
        entity: str,
        evidence: str,
        confidence: str = "high",
    ) -> None:
        row = catalog[row_id]
        current = row["translation"]
        if recommended == current:
            raise AssertionError(f"no-op recommendation: {row_id} / {entity}")
        findings.append(
            {
                "id": row_id,
                "source": row["source"],
                "current": current,
                "recommended": recommended,
                "entity": entity,
                "evidence": evidence,
                "confidence": confidence,
            }
        )

    def replace(
        row_id: str,
        old: str,
        new: str,
        entity: str,
        evidence: str,
        confidence: str = "high",
    ) -> None:
        current = catalog[row_id]["translation"]
        if old not in current:
            raise AssertionError(f"missing {old!r}: {row_id} / {entity}")
        add(row_id, current.replace(old, new), entity, evidence, confidence)

    ev_church = (
        "《密教模拟器》本机 loc_zh-hans 将 Unconquered Sun 定译为“无敌太阳”；"
        "系列 Wiki“势力与团体/无敌太阳典仪”沿用“无敌太阳教会”。"
    )
    replace("TAN-DD3315B51DC8", "不败太阳", "无敌太阳", "Unconquered Sun / 无敌太阳", ev_church)
    replace(
        "TAN-69DF0347FF55",
        "不可征服之太阳教会",
        "无敌太阳教会",
        "Church of the Unconquered Sun / 无敌太阳教会",
        ev_church,
    )
    replace(
        "TAN-3A992E5C07A1",
        "不可征服之[[太阳]]教会",
        "无敌[[太阳]]教会",
        "Church of the Unconquerable Sun / 无敌太阳教会",
        ev_church,
    )
    for row_id in ("TAN-CC777B5C5388", "TAN-8508BDC857D2"):
        replace(row_id, "太阳教会", "无敌太阳教会", "Church Solar / 无敌太阳教会", ev_church)
    replace(
        "TAN-E08A2366D917",
        "不败[[太阳]]",
        "无敌[[太阳]]",
        "Unconquered Sun / 无敌太阳",
        ev_church,
    )
    replace(
        "TAN-423A39E845FE",
        "领受的圣秩",
        "领受圣职",
        "ordained / 领受圣职",
        "项目术语规则与系列教会语境均采用“领受圣职”；避免把行为名词化成易与机构混淆的“圣秩”。",
    )
    add(
        "TAN-95C4071D19DD",
        "我先给驱魔师当助手，后来又做了一个古怪教区的神父。那段日子里的见闻动摇了我的信仰——不久，我便离开了[[教会]]。\n\n<i>1919至1921年间，斯宾塞曾任无敌太阳教会神父。领受圣职时，灵魂中发光的魂质——<b>明识</b>——会被永久烙下印记。因此严格说来，他仍能施行圣礼，尽管这可能违反教会法。</i>",
        "Church Solar + ordination / 无敌太阳教会、领受圣职",
        ev_church + " 此处 ordination 是“领受圣职”，并非另一个名为“圣秩会”的组织。",
    )

    ev_book_suns = (
        "《司辰之书》Wiki“无敌太阳典仪/《骄阳之书》（书珥版）”使用“《骄阳之书》”，"
        "并区分“通行版/核准版”。"
    )
    current = catalog["TAN-78379DF6FE91"]["translation"]
    add(
        "TAN-78379DF6FE91",
        current.replace("《诸阳之书》", "《骄阳之书》").replace("核准本", "核准版").replace("通行本", "通行版"),
        "Book of Suns / 《骄阳之书》",
        ev_book_suns,
    )
    replace("TAN-775E41245683", "《诸阳之书》", "《骄阳之书》", "Book of Suns / 《骄阳之书》", ev_book_suns)
    current = catalog["TAN-B2412918D799"]["translation"]
    recommended = current.replace("《诸阳之书》", "《骄阳之书》").replace("公认本", "通行版").replace("核准本", "核准版")
    add("TAN-B2412918D799", recommended, "Book of Suns / 《骄阳之书》", ev_book_suns)
    current = catalog["TAN-916114BCDDF7"]["translation"]
    add(
        "TAN-916114BCDDF7",
        current.replace("通行本", "通行版").replace("核准本", "核准版"),
        "Received/Sanctioned Version / 通行版、核准版",
        ev_book_suns,
    )

    ev_city = "《司辰之书》Wiki“极目远眺/门扉与墙垣”将 City Unbuilt 定译为“未建之城”。"
    for row_id in ("TAN-B8948C9ECC80", "TAN-B71DA24DCC7F"):
        replace(row_id, "未筑之城", "未建之城", "City Unbuilt / 未建之城", ev_city)

    ev_chandler = "《司辰之书》Wiki《制烛人之愿》及相关文本将 The Chandler 定译为“制烛人”。"
    replacements = {
        "TAN-17E588C2CD1D": ("烛匠", "制烛人"),
        "TAN-360C30A29EA2": ("《蜡烛匠的故事》", "《制烛人的故事》"),
        "TAN-6CAD9780E23D": ("蜡烛匠", "制烛人"),
        "TAN-83B9738D6949": ("《蜡烛匠之愿》", "《制烛人之愿》"),
        "TAN-E05260DB2716": ("蜡烛匠", "制烛人"),
    }
    for row_id, (old, new) in replacements.items():
        replace(row_id, old, new, "The Chandler / 制烛人", ev_chandler)

    ev_inks = "《司辰之书》Wiki“迹象”将 Great Inks 归为“伟大墨水”；基础大类 Encaustum Terminale 则为“终刻墨”。"
    for row_id in ("TAN-5545CCFA31C9", "TAN-55E881406ED1", "TAN-438FC6FE144E"):
        replace(row_id, "大墨", "伟大墨水", "Great Inks / 伟大墨水", ev_inks)
    ev_uzult = "《司辰之书》Wiki“终刻墨”列出 Uzult 的现行定译“珀金”。"
    for row_id in ("TAN-5545CCFA31C9", "TAN-84F45BF4EA99", "TAN-438FC6FE144E", "TAN-46CFA4EA57A8"):
        replace(row_id, "乌祖尔特", "珀金", "Uzult / 珀金", ev_uzult)

    ev_serapeum = "《司辰之书》Wiki“第二次虫鸟解密/图书馆编年史”使用“隐形的塞拉皮雍”。"
    for row_id in ("TAN-53E63C72F979", "TAN-E8A6548B61EA"):
        replace(row_id, "无形塞拉皮翁", "隐形的塞拉皮雍", "Invisible Serapeum / 隐形的塞拉皮雍", ev_serapeum)

    replace(
        "TAN-02689BD59353",
        "宁静",
        "静谧",
        "The Serenity of the Black Wood / 《黑林地的静谧》",
        "《司辰之书》Wiki“列表/技艺”及相关书目使用《黑林地的静谧》。",
    )

    ev_shepherd = "《司辰之书》Wiki“置闰”将 Shepherd Illuminate 记作“沐光明的牧羊人”。"
    replace("TAN-E64EEA5AA538", "牧者·启明者", "沐光明的牧羊人", "Shepherd-Illuminate / 沐光明的牧羊人", ev_shepherd)
    replace("TAN-A450E81B0799", "启明牧者", "沐光明的牧羊人", "Shepherd Illuminate / 沐光明的牧羊人", ev_shepherd)

    replace(
        "TAN-A0875E0DEA7F",
        "眼中之门",
        "瞳中之扉",
        "Door in the Eye / 瞳中之扉",
        "秘史 Wiki 现行对应词条标题为“瞳中之扉”。",
    )

    ev_limian = "《司辰之书》Wiki“伟大之术/利米亚典仪”使用词干“利米亚”。"
    replace("TAN-2F5338A6F0E9", "利米安传统", "利米亚传统", "Limian / 利米亚", ev_limian)
    replace("TAN-4CA80B8A3F96", "利米安教律", "利米亚教律", "Limian / 利米亚", ev_limian)

    ev_aviform = (
        "《司辰之书》Wiki“保存术/鸟鸣学/伟大之术”及秘史 Wiki“夜游漫记/脚注”"
        "均将 Aviform Hours 定为“鸟形司辰”；本作两处脚注也已沿用。"
    )
    for row_id in (
        "TAN-1365443A2737", "TAN-395F7CA7E4C2", "TAN-6325E73A2348",
        "TAN-64C9CA33077C", "TAN-ACFD3C933379", "TAN-BEFDFE42E436",
        "TAN-C99D3BD15367", "TAN-E8057C2BB9F5", "TAN-E8E462F52243",
        "TAN-F1383E17FBAD", "TAN-B611F11F55BF",
    ):
        replace(row_id, "禽形", "鸟形", "Aviform / 鸟形", ev_aviform)
    replace("TAN-E75A69863E3E", "禽形者", "鸟形司辰", "Aviform / 鸟形", ev_aviform)

    ev_agnes = "《密教模拟器》本机 Priest DLC core/loc 对照将 St Agnes 定译为“圣亚割妮”；系列 Wiki沿用。"
    replace("TAN-193FD01A9A91", "圣阿格尼丝节前夕", "圣亚割妮节前夕", "St Agnes / 圣亚割妮", ev_agnes)
    replace("TAN-314F1D92DA2A", "圣阿格尼丝节前夕", "圣亚割妮节前夕", "St Agnes / 圣亚割妮", ev_agnes)
    replace("TAN-FB09DBC60321", "圣艾格尼丝节前夕", "圣亚割妮节前夕", "St Agnes / 圣亚割妮", ev_agnes)

    ev_serena = "《司辰之书》Wiki“名片夹/图书馆编年史”使用“瑟雷娜·布莱克伍德”（简称“瑟雷娜”）。"
    serena_ids = (
        "TAN-254B5AF57D81", "TAN-6BD6FFFD2762", "TAN-75DB2226CAD0",
        "TAN-E2D9525EDE2B", "TAN-E8A6548B61EA", "TAN-F1C6383ECFB9",
        "TAN-FA9F09EC4EE1",
    )
    for row_id in serena_ids:
        replace(row_id, "塞蕾娜", "瑟雷娜", "Serena Blackwood / 瑟雷娜·布莱克伍德", ev_serena)
    replace("TAN-FF1A369DF331", "塞丽娜", "瑟雷娜", "Serena Blackwood / 瑟雷娜·布莱克伍德", ev_serena)
    current = catalog["TAN-08FA6E1939EE"]["translation"]
    add(
        "TAN-08FA6E1939EE",
        current.replace("塞蕾娜", "瑟雷娜").replace("塞雷诺", "瑟雷诺"),
        "Serena/Sereno Blackwood / 瑟雷娜、瑟雷诺·布莱克伍德",
        ev_serena + " Sereno 是文本内的男性化变体，宜保持相同音译词根。",
    )

    ev_illopoly = "《司辰之书》Wiki“杂色塔：伊利奥波里的私室/《夜游漫记·卷一》”使用“克里斯托弗·伊利奥波里”。"
    for row_id in (
        "TAN-1168A075A418", "TAN-2B29DBCF452E", "TAN-AA524A177279",
        "TAN-D237648E47B8", "TAN-F41D1000B1ED", "TAN-809A83405142",
        "TAN-8E0D72B60ED2",
    ):
        replace(row_id, "伊洛波利", "伊利奥波里", "Christopher Illopoly / 克里斯托弗·伊利奥波里", ev_illopoly)

    ev_fraser = "《司辰之书》Wiki“弗雷泽·斯特拉思科因先生”及本作已校条目均使用“斯特拉思科因”。"
    fraser_ids = (
        "TAN-071FECDFD1B0", "TAN-111BE9A7433D", "TAN-264FBF78B619",
        "TAN-292DC5F207DE", "TAN-3CBC79C9639B", "TAN-549BCCFF1DCC",
        "TAN-571AC3D495D1", "TAN-60A932F39901", "TAN-645E6F1497FB",
        "TAN-723AF4A4132E", "TAN-8014B04915AF", "TAN-84D5F38E7982",
        "TAN-8A8085153200", "TAN-8AC63400543F", "TAN-959CF11482FF",
        "TAN-973CD8CBF45E", "TAN-98DB55D0EDF0", "TAN-9F0A77DCDD49",
        "TAN-A28EFE5D374B", "TAN-A4DEFF7A94E6", "TAN-A8F33C6108A2",
        "TAN-AFC96BA260A5", "TAN-B670A3B27497", "TAN-C098C963DE6C",
        "TAN-13D2C8517070", "TAN-1ADCBC2227CF", "TAN-65364CCCBD68",
        "TAN-83272523CB80", "TAN-868BC11A42FF", "TAN-A070723031E7",
        "TAN-A3C907E1630A", "TAN-C54015E9F87B", "TAN-E9B2FDC61DA7",
        "TAN-99D68A082092",
    )
    for row_id in fraser_ids:
        replace(row_id, "斯特拉斯科因", "斯特拉思科因", "Fraser Strathcoyne / 弗雷泽·斯特拉思科因", ev_fraser)

    ev_chaima = "《司辰之书》Wiki“拉拉·柴玛”与本作角色履历相符，定名为“拉拉·柴玛/柴玛”。"
    for row_id in ("TAN-42480A4220D8", "TAN-4B4EFFAFD183", "TAN-C96BA3400B8B"):
        replace(row_id, "沙伊玛", "柴玛", "Chaima / 柴玛", ev_chaima)
    for row_id in (
        "TAN-80FAC232329D", "TAN-82541DEA9F7F", "TAN-8FEC33FC371D",
        "TAN-97C4B44D4ABB", "TAN-9A36499A9E6E", "TAN-ED9CD3B2BF12",
    ):
        replace(row_id, "夏伊玛", "柴玛", "Chaima / 柴玛", ev_chaima)

    ev_hokobald = "《司辰之书》Wiki人物/书目条目使用“Hokobald＝霍科博尔德”；本作另有条目已采用该译名。"
    for row_id in ("TAN-11321DFC289E", "TAN-00C79A30199F"):
        replace(row_id, "霍科鲍德", "霍科博尔德", "Hokobald / 霍科博尔德", ev_hokobald)

    replace(
        "TAN-5BF24236A21C",
        "阿伦·皮尔",
        "阿伦·褪皮",
        "Arun Peel / 阿伦·褪皮",
        "《司辰之书》访客及“褪皮的名片”使用“阿伦·褪皮”。",
    )
    replace(
        "TAN-EB4831E887D6",
        "扎卡里·韦克菲尔德",
        "扎迦利·韦克菲尔德",
        "Zachary Wakefield / 扎迦利·韦克菲尔德",
        "《司辰之书》访客资料使用“扎迦利·韦克菲尔德”。",
    )
    replace(
        "TAN-6259F46AD7D4",
        "格温多琳·法鲁克",
        "格温德琳·法鲁克",
        "Gwendolen Farouk / 格温德琳·法鲁克",
        "《司辰之书》1925年访客资料及本作简称条目使用“格温德琳”。",
    )

    ev_raveline = (
        "《密教模拟器》本机 Exile DLC loc_zh-hans 将 Raveline（葡萄园/地名）定译为“拉维林”；"
        "本作同一地名及血脉名应保持该词根。"
    )
    for row_id in (
        "TAN-3FE187E9F713", "TAN-A8F33C6108A2", "TAN-0D94A8849677",
        "TAN-0CE584C33C75", "TAN-E451D5CF3DCE",
    ):
        replace(row_id, "拉韦林", "拉维林", "Raveline / 拉维林", ev_raveline)

    ev_heart = (
        "系列秘史 Wiki“轰雷之皮/准则”将 Heart Relentless 定名为“不息之心”；"
        "本作 TAN-5A9C458DA23F 也已使用该译名。"
    )
    for row_id in ("TAN-B6467D3F656D", "TAN-900CA806BF64"):
        replace(row_id, "永不停歇之心", "不息之心", "Heart Relentless / 不息之心", ev_heart)

    ev_sun_war = "项目术语表与系列秘史 Wiki均将 War in the Sun 定名为“太阳大战”；本作多数条目也已采用。"
    for row_id in ("TAN-6DAD79BC107A", "TAN-E75A69863E3E"):
        replace(row_id, "[[太阳]]中之战", "[[太阳]]大战", "War in the Sun / 太阳大战", ev_sun_war)

    replace(
        "TAN-4A06094155AF",
        "《麦束报》",
        "《禾捆》",
        "The Sheaf / 《禾捆》",
        "新作内部专名漂移：标题条目及同一段相邻文本均已采用《禾捆》，仅此处作《麦束报》。",
        "medium",
    )

    findings.sort(key=lambda item: (item["id"], item["entity"]))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="\n") as fh:
        for finding in findings:
            fh.write(json.dumps(finding, ensure_ascii=False) + "\n")

    entities = Counter(item["entity"] for item in findings)
    confidences = Counter(item["confidence"] for item in findings)
    unique_ids = len({item["id"] for item in findings})
    summary_lines = [
        "# 前作定译一致性专项审计",
        "",
        f"- 审计输入：`build/merged/review_catalog.jsonl`（只读）",
        f"- 输出建议：{len(findings)} 条，涉及 {unique_ids} 个唯一文本 ID",
        f"- 置信度：" + "，".join(f"{key} {value}" for key, value in sorted(confidences.items())),
        "- 未修改任何 `translations` 工作文件。",
        "",
        "## 主要发现",
        "",
        "- 最大规模的人名漂移是 Fraser Strathcoyne：34 个 ID 写成“斯特拉斯科因”，应随《司辰之书》定译统一为“斯特拉思科因”。",
        "- Serena Blackwood、Christopher Illopoly、Chaima 等回归人物存在系统性音译漂移。",
        "- 核心设定词中，Church Solar 被误缩为“太阳教会”；应回接前作全称“无敌太阳教会”。截图中的 ordination 是“领受圣职”，不是第二个组织“圣秩会”。",
        "- Book of Suns、City Unbuilt、The Chandler、Invisible Serapeum、Uzult、Great Inks 等已有《司辰之书》定译未沿用。",
        "- 同一新作内部另有 Heart Relentless（不息之心）、Aviform（鸟形）、The Sheaf（《禾捆》）漂移。",
        "",
        "## 术语演变判定",
        "",
        "- 未机械回退到《密教模拟器》的旧称：“树丛”在《司辰之书》中规范为“丛林学”，“双角利斧”规范为“双角斧”；现译采用后者是正确的，故不列为问题。",
        "- Great Inks 建议用《司辰之书》后续内容采用的“伟大墨水”；Encaustum Terminale 作为基础类别仍是“终刻墨”，二者不混同。",
        "",
        "## 按实体统计",
        "",
    ]
    for entity, count in entities.most_common():
        summary_lines.append(f"- {entity}: {count}")
    summary_lines.extend(
        [
            "",
            "## 主要对照来源",
            "",
            "- 本机《密教模拟器》：`cultistsimulator_Data/StreamingAssets/content/core` 与 `loc_zh-hans` 的同 ID 对照（仅用于术语核验）。",
            "- 《密教模拟器》中文 Wiki：势力与团体、《日落殊途》等条目。",
            "- 《司辰之书》中文 Wiki：无敌太阳典仪、伟大之术、图书馆编年史、置闰，以及相关人物/书目条目。",
            "- 秘史 Wiki：轰雷之皮、准则，用于 Heart Relentless 的系列定名复核。",
            "",
            "完整证据说明逐条写入 `predecessor_consistency.jsonl` 的 `evidence` 字段。",
        ]
    )
    SUMMARY.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(f"wrote {len(findings)} findings / {unique_ids} ids -> {OUTPUT}")
    print(f"wrote summary -> {SUMMARY}")


if __name__ == "__main__":
    main()
