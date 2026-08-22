#!/usr/bin/env python3
"""Apply open-set terminology additions and evidence-backed corrections.

Every mutation asserts its predecessor value.  Longer prose is changed only by
row id; recurring proper terms are changed only in rows whose English source
contains the exact case-sensitive term.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATE = "2026-08-22"


def spec(
    canonical: str,
    target: str,
    term_type: str,
    *,
    aliases: dict[str, str] | None = None,
    origin: str = "travelling_new",
    reference_label: str,
    reference_url: str,
    evidence: str,
    rationale: str,
    alternatives: str,
    basis: str,
    confidence: str,
    locators: list[str],
) -> dict:
    return {
        "canonical": canonical,
        "target": target,
        "type": term_type,
        "aliases": aliases or {},
        "origin": origin,
        "reference_label": reference_label,
        "reference_url": reference_url,
        "evidence": evidence,
        "rationale": rationale,
        "alternatives": alternatives,
        "basis": basis,
        "confidence": confidence,
        "locators": locators,
    }


CS_NOON = "https://cultist.huijiwiki.com/wiki/《兰花变容·卷三：午时》"
BOH_HOME = "https://boh.huijiwiki.com/wiki/首页"
CS_HOME = "https://cultist.huijiwiki.com/wiki/首页"
TAN = "https://weatherfactory.biz/travelling-at-night/"

NEW_SPECS = [
    spec("Amiral", "海军上将", "职衔", reference_label="《夜游漫记》达尔朗脚注", reference_url=TAN,
         evidence="大写 Amiral 出现在 Darlan 的法语国家元首职衔 Amiral de France 中，并作为可展开链接单独出现。",
         rationale="译“海军上将”，采用现代法语 amiral 的标准军衔义；在完整法语职衔中仍按句法组合。",
         alternatives="“海军元帅”擅自提高军衔；纯音译不能让玩家理解其政治身份。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-D86F89B4864C"]),
    spec("Aspect Pool", "性相池", "机制", reference_label="《夜游漫记》技艺检定与心念说明", reference_url=TAN,
         evidence="试玩版把 Aspect Pool 作为储存并消耗各性相点数的独立机制，心念又持续向该池贡献性相。",
         rationale="译“性相池”，严格沿用 Aspect“性相”，并用“池”表现可积累、消耗与恢复。",
         alternatives="“属性池”丢失系列术语；“性相点”只指池内单位而非容器。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-D4D15360B3B2"]),
    spec("Bonanza Cigarettes", "博南扎牌香烟", "物品名", aliases={"Bonanza Cigarette":"博南扎牌香烟"}, reference_label="《夜游漫记》博南扎牌香烟物品", reference_url=TAN,
         evidence="物品标签与对话把 Bonanza 当作香烟品牌而非普通 bonanza；单复数指同一品牌产品。",
         rationale="定名“博南扎牌香烟”：品牌音译“博南扎”，补“牌香烟”说明物类；单数不另造名称。",
         alternatives="“富矿香烟”误把品牌按普通词意译；只写“博南扎”缺少物类。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-E7D8E1EC7B26"]),
    spec("Gladwyn Lake", "格拉德温湖", "地点", origin="predecessor", reference_label="《密教模拟器》官中：格拉德温湖", reference_url="https://cultist.huijiwiki.com/wiki/格拉德温湖",
         evidence="本机《密教模拟器》同一藏宝地 Gladwyn Lake 官中标签为“格拉德温湖”；本作回忆指向同一地点。",
         rationale="沿用前作地点名“格拉德温湖”，不重新按现代人名习惯转写 Gladwyn。",
         alternatives="“格莱德温湖”会造成同一地点跨作品异名。", basis="predecessor_official_same_id", confidence="fixed", locators=["Cultist Simulator:elements/vaults.json#vaultshires1","TAN:TAN-AE832BE57CCC"]),
    spec("History", "历史", "设定概念", aliases={"Histories":"诸史"}, origin="predecessor", reference_label="秘史系列：History / Histories", reference_url="https://mansus.huijiwiki.com/wiki/秘史",
         evidence="系列文本用大写 History 指一重可被改写的历史，复数 Histories 指并存诸史；本作继续讨论五史与书写历史。",
         rationale="单数译“历史”，复数专名译“诸史”，既保留数的差异，也不与固定合称 Secret Histories“秘史”混为一词。",
         alternatives="把所有 History 都译“秘史”会误加 Secret；复数仍写“历史”会丢失集合语气。", basis="predecessor_official_corpus", confidence="fixed", locators=["TAN:TAN-E389B851F62E"]),
    spec("Invisible Bag", "隐形袋", "UI机制", reference_label="《夜游漫记》物品栏说明", reference_url=TAN,
         evidence="开发补丁说明与物品栏 tooltip 都把 invisible bag 当作隐藏溢出物品的固定 UI 容器。",
         rationale="译“隐形袋”，直观说明不可见但实际承载物品的界面容器。",
         alternatives="“隐藏背包”易被理解为可切换的普通背包栏；“无形囊”语体过玄。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-560B3D164FC3"]),
    spec("Ivory Dove", "骨白鸽", "设定存在", origin="predecessor", reference_label="《密教模拟器》官中：骨白鸽", reference_url=CS_HOME,
         evidence="本机《密教模拟器》多条同一存在祷文稳定把 Ivory Dove 译为“骨白鸽”，并非材质为象牙的鸽子。",
         rationale="沿用官中“骨白鸽”，保留死亡、遗骸与冬准则的意象。",
         alternatives="旧译“象牙鸽”把 ivory 误收窄为工艺材料，割裂其死亡神学。", basis="predecessor_official_corpus", confidence="fixed", locators=["Cultist Simulator:recipes/explore_obstacles_guardians.json#explorevaultguardian_dead_highwinter","TAN:TAN-0927F42204C8"]),
    spec("Lark", "百灵鸟", "设定造物", origin="predecessor", reference_label="《司辰之书》官中：未完工的百灵鸟", reference_url=BOH_HOME,
         evidence="《司辰之书》同一 Unfinished Lark 项目与事件统一为“未完工的百灵鸟”；本作所说零件、事故与未完成造物是同一 Lark。",
         rationale="专名 Lark 译“百灵鸟”，沿用前作造物名；普通小写 lark 作鸟类时仍可随句法处理。",
         alternatives="旧译“云雀”虽是词典义，却会让同一秘史造物跨作品异名。", basis="predecessor_official_corpus", confidence="fixed", locators=["BOOK OF HOURS:achievements/a_affair.json#A_AFFAIR_LARK","TAN:TAN-F1C6383ECFB9"]),
    spec("little joys of night", "夜中微小的欢愉", "脚注短语", reference_label="《夜游漫记》脚注链接", reference_url=TAN,
         evidence="该小写短语被双括号标成可独立展开的脚注目标，不是普通正文片段。",
         rationale="译“夜中微小的欢愉”，保留 joys 的复数积累感与 night 的时间、秘术双关。",
         alternatives="“夜生活小乐趣”过度现代口语；“夜之喜悦”抬高强度。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-AAB4A35E7431"]),
    spec("Outfit", "装束", "机制", aliases={"Outfits":"装束"}, reference_label="《夜游漫记》衣柜与装束说明", reference_url=TAN,
         evidence="Outfit 是可在衣柜切换、带性相并影响人物反应的装备类别；复数仍指同一机制。",
         rationale="译“装束”，比“衣服”更能涵盖整套搭配与社交观感。",
         alternatives="“服装”偏物品门类；“套装”容易暗示固定成套装备奖励。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-19D3705FCF5A"]),
    spec("Pilgrim", "朝圣者", "设定位阶", aliases={"Pilgrims":"朝圣者"}, origin="predecessor", reference_label="秘史系列鸟形司辰朝圣者", reference_url="https://mansus.huijiwiki.com/wiki/司辰",
         evidence="本作把七位 Pilgrims 与鸟形司辰、晋升道路并列，大小写与复数都指同一设定位阶。",
         rationale="译“朝圣者”，保留追随司辰而上升的宗教旅途义。",
         alternatives="“旅行者”丢失宗教目的；“巡礼者”与现有中文系列用语不一致。", basis="predecessor_official_corpus", confidence="fixed", locators=["TAN:TAN-E8E462F52243"]),
    spec("Republic", "共和国", "政治概念", reference_label="《夜游漫记》架空欧洲脚注", reference_url=TAN,
         evidence="大写 Republic 在多国脚注中表示具体共和政体或政权阶段，并可作为链接目标解释架空政治。",
         rationale="译“共和国”，采用现代政治通名；具体国家名仍在句中补足。",
         alternatives="“共和派”把政体误成人群；“民国”带入特定中文历史语境。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-8508BDC857D2"]),
    spec("Sleep", "睡眠", "机制", reference_label="《夜游漫记》睡眠与恢复机制", reference_url=TAN,
         evidence="Sleep 是在床铺、睡袍、疲惫与麻烦恢复规则中反复链接的独立机制。",
         rationale="机制名译“睡眠”，动词句中可按中文写“入睡”，链接标签保持名词。",
         alternatives="统一写“睡觉”过于口语且不能自然充当机制分类名。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-16244CD55138"]),
    spec("The Barber's Tower", "理发师之塔", "地点", reference_label="《夜游漫记》米马塔相关脚注", reference_url=TAN,
         evidence="该大写专名是地图与脚注中可独立指向的塔楼地点；Barber 在此为称号所有格。",
         rationale="译“理发师之塔”，保留人物称号与建筑物从属关系。",
         alternatives="“理发塔”像现代设施；音译 Barber 丢失有意可读称号。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-560B3D164FC3"]),
    spec("Travelling", "旅行", "机制", reference_label="《夜游漫记》旅行界面", reference_url=TAN,
         evidence="Travelling 是地图、许可、路线收益与痕迹消退共同使用的行动机制名。",
         rationale="译“旅行”，名词和进行时界面均自然；作品名 Travelling at Night 仍另按《夜游漫记》处理。",
         alternatives="“出行”削弱跨国长途感；“移动”误成普通走路。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-0A87906BB46C"]),
    spec("Watchman's Tree", "守夜人之树", "设定盟约", origin="predecessor", reference_label="《司辰之书》官中：守夜人之树", reference_url=BOH_HOME,
         evidence="《司辰之书》官中多条决断说明把 Watchman's Tree 固定译为“守夜人之树”，定义为限制禁忌知识的盟约。",
         rationale="沿用“守夜人之树”，保留司辰称号和树状盟约的双层意义。",
         alternatives="“守望者之树”会把同一司辰改名；“守夜树”丢失所有格。", basis="predecessor_official_corpus", confidence="fixed", locators=["BOOK OF HOURS:elements/_resolutionaspects.json#de.forge","TAN:TAN-A08DDD3DD75"]),
    spec("Worm", "蠕虫", "设定实体", aliases={"Worms":"蠕虫"}, origin="predecessor", reference_label="《司辰之书》官中：蠕虫", reference_url=BOH_HOME,
         evidence="前作官中把大写 Worm/Worms 稳定译为“蠕虫”；本作仍指寄居灵魂、吞食能力的同类存在。",
         rationale="沿用“蠕虫”，单复数由中文上下文表达，不另造集合名。",
         alternatives="“虫”过泛；“蛆虫”擅加生物形态。", basis="predecessor_official_corpus", confidence="fixed", locators=["BOOK OF HOURS:achievements/a_affair.json#A_AFFAIR_GUEST","TAN:TAN-3F11F541B09B"]),
    spec("Lion-Throned One", "以狮背为王座者", "设定称谓", origin="predecessor", reference_label="《兰花变容·卷三：午时》官中", reference_url=CS_NOON,
         evidence="《密教模拟器》与《司辰之书》对完全相同引文均译“以狮背为王座者”，是现成官中称谓。",
         rationale="逐字沿用官中，保留‘以狮背作王座’的异常具体意象，不压缩为信息不足的称号。",
         alternatives="旧译“狮座者”既非官中，又可能被误解为狮子座或坐狮之人。", basis="predecessor_official_same_id", confidence="fixed", locators=["Cultist Simulator:recipes/study_1_books.json#studyorchidtransfigurations3","BOOK OF HOURS:elements/tomes.json#t.theorchidtransfigurationsnoon","TAN:TAN-7200F34A125D"]),
    spec("Waking Word", "唤醒之语", "设定术语", origin="predecessor", reference_label="《兰花变容·卷三：午时》官中", reference_url=CS_NOON,
         evidence="两部前作官中在同一引文中都把 Waking Word 加粗并译“唤醒之语”。",
         rationale="沿用“唤醒之语”，保留 Word 的话语/秘言属性以及 Waking 的施动义。",
         alternatives="旧译“醒时之言”把 waking 误作时间状态，也偏离双重官中。", basis="predecessor_official_same_id", confidence="fixed", locators=["Cultist Simulator:recipes/study_1_books.json#studyorchidtransfigurations3","TAN:TAN-7200F34A125D"]),
    spec("Three-Valved Door", "三膜之门", "设定门扉", origin="predecessor", reference_label="《兰花变容·卷三：午时》官中", reference_url=CS_NOON,
         evidence="《密教模拟器》与《司辰之书》相同引文均把 Three-Valved Door 译“三膜之门”。",
         rationale="沿用官中“三膜之门”；valve 在此取隔膜/瓣膜义，而非花瓣。",
         alternatives="旧译“三瓣之门”容易误成花瓣门，也违背既定官中。", basis="predecessor_official_same_id", confidence="fixed", locators=["Cultist Simulator:recipes/study_1_books.json#studyorchidtransfigurations3","TAN:TAN-7200F34A125D"]),
    spec("Moon's House", "月亮的居屋", "设定地点", origin="predecessor", reference_label="《司辰之书》官中：月亮的居屋", reference_url="https://boh.huijiwiki.com/wiki/结局",
         evidence="《司辰之书》官中在织机、闰识与月相结局中反复固定为“月亮的居屋”。",
         rationale="沿用“月亮的居屋”，与 House of the Moon 同指一处漫宿倒影地点。",
         alternatives="旧译“月之居屋”表面雅化，却造成同地异名。", basis="predecessor_official_corpus", confidence="fixed", locators=["BOOK OF HOURS:verbs/workstations_library_world.json#library.loom","TAN:TAN-36E63E553D45"]),
    spec("Society of the Noble Endeavour", "高贵之举社团", "组织", origin="predecessor", reference_label="《密教模拟器》官中：高贵之举社团", reference_url="https://cultist.huijiwiki.com/wiki/受控之火的君王",
         evidence="前作同一组织的书目、说明与韦兰条目都使用“高贵之举社团”。",
         rationale="沿用官中组织名；Endeavour 在既定专名中取“之举”，Society 明写“社团”。",
         alternatives="旧译“崇高事业会”逐词另造，切断韦兰与前作组织的关系。", basis="predecessor_official_corpus", confidence="fixed", locators=["Cultist Simulator:elements/books_lore.json#irreproachabletraditionssocietynobleendeavour","TAN:TAN-8FBE945D7B4E"]),
    spec("Orchard of Lights", "光之果园", "设定地点", origin="predecessor", reference_label="《密教模拟器》官中：光之果园", reference_url=CS_HOME,
         evidence="前作长生者梦袭文本直接把 Orchard of Lights 译作“光之果园”；本作指同一漫宿地点。",
         rationale="沿用“光之果园”，Lights 是园中发光果实与辉光的复数，不是灯具。",
         alternatives="旧译“灯之果园”误把 lights 机械对应准则 Lantern。", basis="predecessor_official_corpus", confidence="fixed", locators=["Cultist Simulator:recipes/long_recipes_attacks.json#long.executestrategy.dreams.dreadtofascination.poisoned.begin","TAN:TAN-EEDC1C29B47C"]),
    spec("Knotwingknot", "异结翼", "设定存在", origin="predecessor", reference_label="《密教模拟器》官中：异结翼", reference_url=CS_HOME,
         evidence="前作同一存在的 Knotwingknot Nest 官中为“异结翼的巢穴”。",
         rationale="沿用“异结翼”，视 knot-wing-knot 为设定生物名，不机械复刻两个 knot。",
         alternatives="旧译“结翼结”生硬且与前作同一存在异名。", basis="predecessor_official_same_id", confidence="fixed", locators=["Cultist Simulator:elements/DLC_EXILE_exile_elements.json#vault.barber","TAN:TAN-1B548D29526B"]),
    spec("Ichor Auroral", "曙光灵液", "秘术物品", origin="predecessor", reference_label="《司辰之书》官中：曙光灵液", reference_url=BOH_HOME,
         evidence="《司辰之书》多项制作配方把 Ichor Auroral 固定译为“曙光灵液”。",
         rationale="沿用官中“曙光灵液”；ichor 取神性液体而非普通血液。",
         alternatives="“曙光脓液”强加病理感；纯音译丢失物质属性。", basis="predecessor_official_same_id", confidence="fixed", locators=["BOOK OF HOURS:recipes/crafting_2_keeper.json#craft.keeper.inks.revelation_rose_ichor.auroral_porphyrine","TAN:TAN-BFF40BD63A8C"]),
    spec("Bischoff", "比舒夫", "人物姓氏", origin="predecessor", reference_label="《司辰之书》官中：伊尔莎·比舒夫", reference_url=BOH_HOME,
         evidence="《司辰之书》电影研习提示以同一 Ilse Bischoff 署名并译“伊尔莎·比舒夫”。",
         rationale="本作省略名字时仍沿用姓氏“比舒夫”，与前作伊尔莎·比舒夫保持同一人名。",
         alternatives="旧译“比肖夫”与同一人物前作官中不一致。", basis="predecessor_official_same_id", confidence="fixed", locators=["BOOK OF HOURS:recipes/1_consider_books.json#study.film.ability.hint","TAN:TAN-04A795A236D0"]),
    spec("Sweet Bones", "甜美的骨头", "地点", origin="predecessor", reference_label="《司辰之书》官中：甜美的骨头", reference_url=BOH_HOME,
         evidence="《司辰之书》聊天、雇佣与餐食文本稳定把 Sweet Bones 译为“甜美的骨头”。",
         rationale="沿用前作地点名，保留 sweet 与 bones 并置的古怪酒馆感。",
         alternatives="旧译“甜骨头”压掉形容词语气，也造成同店异名。", basis="predecessor_official_corpus", confidence="fixed", locators=["BOOK OF HOURS:decks/chats.json#d.chat.sweetbones","TAN:TAN-C1064A0C0F3E"]),
    spec("Torgue", "图格", "人物", aliases={"Captain Torgue":"图格上尉"}, origin="predecessor", reference_label="《司辰之书》官中：图格的净化术", reference_url=BOH_HOME,
         evidence="《司辰之书》同名 Torgue's Cleansing 官中稳定使用“图格”；本作 Captain Torgue 延续该姓氏。",
         rationale="沿用前作姓氏“图格”，军衔组合为“图格上尉”，避免同一专名跨作品漂移。",
         alternatives="旧译“托格”没有系列依据，并造成同一专名词根漂移。", basis="predecessor_official_corpus", confidence="fixed", locators=["BOOK OF HOURS:recipes/_legacy_crafting_4a_prenticeplus_ambittable_unfriendly.json#craft.auroralcontemplations_torgues.cleansing_edge_preview_s","TAN:TAN-ACD79842D623"]),
    spec("Daymare", "日魇", "人物别号", origin="predecessor", reference_label="《司辰之书》官中：日魇", reference_url=BOH_HOME,
         evidence="《司辰之书》访客与地址文本把 Dagmar 的自选别号 Daymare 固定译“日魇”。",
         rationale="沿用“日魇”，用“日”与 nightmare 的“夜魇”构成反转双关。",
         alternatives="旧译“昼魇”虽可解释，却偏离同一人物官中别号。", basis="predecessor_official_same_id", confidence="fixed", locators=["BOOK OF HOURS:elements/_visitreadaspects.json#tx.dagmar","TAN:TAN-290B743D7D1D"]),
    spec("Dappled Rose", "斑驳玫瑰", "结局专名", aliases={"The Dappled Rose":"斑驳玫瑰"}, origin="predecessor", reference_label="《司辰之书》官中：斑驳玫瑰事件", reference_url=BOH_HOME,
         evidence="《司辰之书》同一 Dappled Rose 事件及访客事务均译“斑驳玫瑰”。",
         rationale="沿用“斑驳玫瑰”，Rose 在此是专名意象而非准则“引”的普通替换。",
         alternatives="“杂色之引”误把完整结局专名拆成机制词。", basis="predecessor_official_same_id", confidence="fixed", locators=["BOOK OF HOURS:achievements/a_affair.json#A_AFFAIR_ROSE","TAN:TAN-ABF154F9281F"]),
    spec("Plague of Leaves", "叶疫", "疫病", aliases={"Plague of Flowers":"花疫"}, reference_label="《夜游漫记》罗迪娅与伊庇鲁斯对白", reference_url=TAN,
         evidence="多段对白把该疫病与孢子、人体发芽、开花和结果连成一条病理意象；Flowers 是同一疫病的别称。",
         rationale="主名译“叶疫”、别名译“花疫”，短促如疾病俗称，并保留 leaves/flowers 的阶段意象。",
         alternatives="“树叶瘟疫”过于说明性；“绿疫”丢失叶与花的明确对照。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-354F6EAA516B","TAN:TAN-60E58C59F123"]),
    spec("Mansion of Heaven", "天国府邸", "设定存在", reference_label="《夜游漫记》司辰集体脚注", reference_url=TAN,
         evidence="脚注把 Mansion of Heaven 同时作为由诸司辰构成、又可整体受崇拜的复合存在，并描述其内部战争。",
         rationale="定名“天国府邸”，压缩成可反复指称的专名，同时保留 mansion 的宏大居所义。",
         alternatives="旧译“天国的府邸”是句内描述而非专名；“天堂宫殿”带入基督教固定想象。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-CE233C7BC3C9"]),
    spec("Mark of Necessity", "必然之印", "秘术物品", reference_label="《夜游漫记》制作与货币说明", reference_url=TAN,
         evidence="物品说明称其象征世界根本的 necessity，并可代替部委多利亚币施展夜之技艺。",
         rationale="译“必然之印”，与机制 Necessity“必然”同词根，Mark 作为成品名译“印”。",
         alternatives="旧 notes 的“必需之印”把宇宙必然性降为需求条件；“必要印记”像系统校验。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-9FC0A946E297","TAN:TAN-321A2B039831"]),
    spec("Repurposed Names", "转作他用的具名者", "设定分类", aliases={"List of Repurposed Names":"转作他用的具名者清单"}, reference_label="《夜游漫记》具名者清单资产", reference_url=TAN,
         evidence="大写 Names 在同一宇宙指司辰麾下的具名者；该列表登记被重新用于其他职能或身份的具名者。",
         rationale="译“转作他用的具名者”，恢复 Names 的位阶义；完整标签补“清单”。",
         alternatives="旧译“改作他用的姓名”把超自然存在误成姓名字符串。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-0172B2C5E1B8"]),
    spec("Rung Ma", "鬼林", "地点", reference_label="越南语 rừng ma 与军团回忆语境", reference_url="https://vdict.com/r%E1%BB%ABng,3,0,0.html",
         evidence="源文 Rung Ma 与 Khorasan 并列为军团服役的凶险地点；拼写对应被游戏省略声调的越南语 rừng ma，字面为鬼魂之林。",
         rationale="译“鬼林”，恢复越南语可读义，并统一此前互相冲突的“隆马／龙马”。",
         alternatives="“隆马”“龙马”都把越南语误当汉语式音译，且两处不一致。", basis="language_or_professional_reference", confidence="strong", locators=["TAN:TAN-09B66232562E","TAN:TAN-9407B804783B"]),
    spec("Herpetic Implex", "蛇行缠结", "秘术物品", reference_label="Implex 词源与《夜游漫记》物品说明", reference_url="https://www.etymonline.com/word/implex",
         evidence="implex 源自 interwoven/entwined；物品说明又称它是潜在蠕虫或虫痕仿照灵魂伤疤形成的 horrible tangle。",
         rationale="译“蛇行缠结”：蛇行承接 herpetic 的爬行词根与蠕虫形态，缠结对应 implex 和 tangle。",
         alternatives="“疱疹复结”误落到现代病名；纯音译无法呈现物品的纠缠形态。", basis="language_or_professional_reference", confidence="strong", locators=["TAN:TAN-D5184161BC02"]),
    spec("Twilit Votum", "暮光愿契", "秘术物品", aliases={"Votum":"愿契"}, reference_label="Latin votum 与《夜游漫记》物品说明", reference_url="https://atlas.perseus.tufts.edu/dictionaries/entry/urn%3Acite2%3Ascaife-viewer%3Adictionary-entries.atlas_v1%3Alat.ls.perseus-eng2-n51403/",
         evidence="拉丁 votum 可指向神明所立的庄严誓愿或奉献；物品说明把它定义为沉默旅行的 covenant。",
         rationale="译“暮光愿契”，以“愿”保留誓愿、祈愿，以“契”对应 covenant 的约束。",
         alternatives="“暮光投票”误取现代 vote；“暮誓”丢失契约与奉献物双重物性。", basis="language_or_professional_reference", confidence="strong", locators=["TAN:TAN-784E4017228D"]),
    spec("Tesserate Eye", "方格之眼", "秘术物品", aliases={"Tesserate":"方格化"}, reference_label="tesserate 构词与《夜游漫记》物品说明", reference_url="https://goong.com/word/tesserate-meaning/",
         evidence="tesserate 源于 tessera“小方块”，表示按无隙方格/镶嵌划分；物品是教会认可司辰之具名者向官员传递权威的眼形征记。",
         rationale="译“方格之眼”，让几何镶嵌形态成为可见专名，同时保留 Eye“眼”的权威象征。",
         alternatives="“四维之眼”会与 tesseract 混淆；“镶嵌眼”像工艺描述而非征记名。", basis="language_or_professional_reference", confidence="strong", locators=["TAN:TAN-189931B4EC10"]),
    spec("St Kalliste", "圣卡利斯忒", "虚构圣名", reference_label="Greek Kallistē 人名与《夜游漫记》回忆标题", reference_url="https://www.theoi.com/Nymphe/NympheKalliste.html",
         evidence="Kalliste 对应希腊语 Καλλίστη / Kallistê，亦作女性名；本作把它用作 Ecdysis Club 相关前夜的虚构圣名。",
         rationale="音译“圣卡利斯忒”，保留词尾长元音的女性名形态，不把潜在“至美者”含义直接意译。",
         alternatives="旧译“圣卡利斯特”截掉词尾元音，易误作男性 Callistus；“至美圣女”过度释义。", basis="language_or_professional_reference", confidence="strong", locators=["TAN:TAN-63B60BD74E4A"]),
    spec("St Robigo", "圣罗比戈", "虚构圣名", reference_label="罗马 Robigo 神祇与 Robigalia", reference_url="https://penelope.uchicago.edu/encyclopaedia_romana/calendar/robigalia.html",
         evidence="Robigo/Robigus 是掌谷物锈病与霉枯的罗马神祇；本作将其基督教化为 St Robigo 并用于回忆日期。",
         rationale="译“圣罗比戈”，保留罗马神名音形，让异教神被封圣的错位感留给设定。",
         alternatives="“圣锈病”把人名/神名粗暴意译；“罗比古斯”擅自改用另一性别异体。", basis="external_authority", confidence="strong", locators=["TAN:TAN-E31E8916260E"]),
    spec("Salt-Skein", "盐绞", "设定物", reference_label="《夜游漫记》利米亚传统说明", reference_url=TAN,
         evidence="文本明确说 Salt-Skein 是姊妹用来把双生女巫缚在一起的线绞；skein 指成绞的纱线，也呼应 Knot 体系。",
         rationale="定名“盐绞”，以“绞”保留成束纱线和缠缚动作，盐则对应海岸与盐白法衣。",
         alternatives="“盐纱”只剩材料；“盐之线团”过于日常且丢失仪式名的紧缩感。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-4465077590CF","TAN:TAN-2F5338A6F0E9"]),
    spec("Mimis", "米米斯", "人物昵称", reference_label="《夜游漫记》罗迪娅对白", reference_url=TAN,
         evidence="罗迪娅用 My Mimis 指已葬于伊庇鲁斯的丈夫，是专属亲昵称呼；资产未给更完整姓名。",
         rationale="音译“米米斯”，保留昵称而不擅自补全希腊姓名或亲属称谓。",
         alternatives="直接译“丈夫”会抹掉称呼；“咪咪”中文儿语感过强。", basis="editorial_transliteration", confidence="editorial", locators=["TAN:TAN-EE4435E29FA0"]),
]

ALIAS_ADDITIONS = {
    "Aspect": {"Aspects": "性相"},
    "Hour": {"Hours": "司辰", "Horae": "司辰"},
    "Influence": {"Influences": "影响"},
    "Name": {"Names": "具名者"},
    "the Ministries": {"Ministries": "部委"},
    "Office of Onteiric Coordination": {"OOC": "本体梦理协调办公室"},
    "Principle": {"Principles": "准则"},
    "The Watchman": {"Watchman": "守夜人"},
    "Bewitch": {"Bewitching": "惑心", "bewitchment": "惑心术"},
    "Chrysolagnia": {"Chrysolagnic": "嗜金"},
    "Chrysolepsis": {"Chrysoleptic": "金痫"},
    "Despair": {"Despairing": "绝望"},
    "Despondency": {"Despondent": "消沉"},
    "Exhaustion": {"Exhausted": "精疲力竭"},
    "Languor": {"Languorous": "倦怠"},
}

EXISTING_CHANGES = {
    "The Chandler's Tale": {
        "target": "《制烛人的传说》",
        "reference_label": "《司辰之书》官中：制烛人的传说",
        "reference_url": BOH_HOME,
        "evidence": "本机《司辰之书》同一英文题名 The Chandler's Tale 在多项呈递中固定译为“制烛人的传说”。",
        "rationale": "定名《制烛人的传说》，沿用前作同名文献；本作署名是引用同一宇宙题名，不能因 Tale 可直译 story 就另造异名。",
        "alternatives": "旧译《制烛人的故事》忽略了前作完全相同题名的官中证据。",
        "basis": "predecessor_official_same_id",
        "confidence": "fixed",
        "locators": ["BOOK OF HOURS:recipes/wisdom_commitments.json#commit.ith.s.mandaic", "TAN:TAN-360C30A29EA2"],
    }
}

ROW_UPDATES = {
    "TAN-7200F34A125D": "“但我们必须动用刀刃，”以狮背为王座者说，“动用绞索、火焰、唤醒之语，去对付那些穿过三膜之门的人。因此，谁也不得通过：这就是我们的律法，也是太阳的律法。”",
    "TAN-360C30A29EA2": "《制烛人的传说》",
    "TAN-0172B2C5E1B8": "转作他用的具名者清单",
    "TAN-5A43BBE284B0": "装束",
}

SOURCE_REPLACEMENTS = [
    ("Moon's House", "月之居屋", "月亮的居屋"),
    ("Society of the Noble Endeavour", "崇高事业会", "高贵之举社团"),
    ("Orchard of Lights", "灯之果园", "光之果园"),
    ("Knotwingknot", "结翼结", "异结翼"),
    ("Bischoff", "比肖夫", "比舒夫"),
    ("Sweet Bones", "甜骨头", "甜美的骨头"),
    ("Torgue", "托格", "图格"),
    ("Daymare", "昼魇", "日魇"),
    ("Rung Ma", "隆马", "鬼林"),
    ("Rung Ma", "龙马", "鬼林"),
    ("St Kalliste", "圣卡利斯特", "圣卡利斯忒"),
    ("Ivory Dove", "象牙鸽", "骨白鸽"),
    ("Lark", "云雀", "百灵鸟"),
]


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(raw) for raw in path.read_text(encoding="utf-8-sig").splitlines() if raw]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def apply_translations(directory: Path) -> tuple[int, set[str]]:
    changed = 0
    seen_ids: set[str] = set()
    for path in sorted(directory.glob("chunk_*.jsonl")):
        rows = load_jsonl(path)
        dirty = False
        for row in rows:
            before = row["translation"]
            if row["id"] in ROW_UPDATES:
                row["translation"] = ROW_UPDATES[row["id"]]
                seen_ids.add(row["id"])
            for source_term, old, new in SOURCE_REPLACEMENTS:
                if source_term in row["source"] and old in row["translation"]:
                    row["translation"] = row["translation"].replace(old, new)
            if row["translation"] != before:
                changed += 1
                dirty = True
                row["notes"] = re.sub(
                    r"(?:暂译|暂音译|暂沿|待设定复核|待人物/文化指涉核查|待全局设定术语复核)[^；。]*[；。]?",
                    "",
                    row.get("notes", ""),
                ).strip("； ")
                suffix = "开放终审：服从前作官中或逐词证据链，修正设定称谓。"
                row["notes"] = f"{row['notes']}；{suffix}" if row["notes"] else suffix
        if dirty:
            write_jsonl(path, rows)
    missing = set(ROW_UPDATES) - seen_ids
    if missing:
        raise SystemExit(f"targeted translation ids missing in {directory}: {sorted(missing)}")
    return changed, seen_ids


def main() -> int:
    glossary_path = ROOT / "glossary/glossary.csv"
    with glossary_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0].keys())
    by_term = {row["source_en"]: row for row in rows}

    provenance_paths = {
        origin: ROOT / f"glossary/provenance/{origin}.jsonl"
        for origin in ("predecessor", "travelling_new", "real_world", "editorial")
    }
    provenance = {origin: load_jsonl(path) for origin, path in provenance_paths.items()}
    provenance_by_canonical = {
        row["canonical"]: (origin, row)
        for origin, origin_rows in provenance.items()
        for row in origin_rows
    }
    ledger_path = ROOT / "glossary/final_term_audit.jsonl"
    ledger = load_jsonl(ledger_path)
    ledger_by_canonical = {row["canonical"]: row for row in ledger}

    for canonical, aliases in ALIAS_ADDITIONS.items():
        if canonical not in provenance_by_canonical or canonical not in by_term:
            raise SystemExit(f"alias canonical missing: {canonical}")
        _origin, record = provenance_by_canonical[canonical]
        record["aliases"] = sorted(set(record.get("aliases", [])) | set(aliases), key=str.casefold)
        for alias, target in aliases.items():
            if alias in by_term and by_term[alias]["target_zh"] != target:
                raise SystemExit(f"alias collision: {alias}")
            if alias not in by_term:
                new_row = {
                    "source_en": alias,
                    "target_zh": target,
                    "type": by_term[canonical]["type"],
                    "case_sensitive": "true",
                    "confidence": "high",
                    "notes": f"开放终审：{canonical} 的词形变体",
                }
                rows.append(new_row)
                by_term[alias] = new_row
        audit = ledger_by_canonical[canonical]
        audit["alias_targets_final"].update(aliases)

    for canonical, change in EXISTING_CHANGES.items():
        if canonical not in by_term or canonical not in provenance_by_canonical:
            raise SystemExit(f"change canonical missing: {canonical}")
        old = by_term[canonical]["target_zh"]
        if old == change["target"]:
            raise SystemExit(f"change already applied unexpectedly: {canonical}")
        by_term[canonical]["target_zh"] = change["target"]
        by_term[canonical]["notes"] = f"开放终审：{change['rationale']}"
        _origin, record = provenance_by_canonical[canonical]
        for key in ("reference_label", "reference_url", "evidence", "rationale", "alternatives"):
            record[key] = change[key]
        audit = ledger_by_canonical[canonical]
        audit["target_before"] = old
        audit["target_final"] = change["target"]
        audit["decision"] = "change"
        audit["basis"] = change["basis"]
        audit["confidence"] = change["confidence"]
        audit["evidence_locators"] = change["locators"] + [change["reference_url"]]
        audit["audit_note"] = change["rationale"]

    for item in NEW_SPECS:
        canonical = item["canonical"]
        if canonical in by_term or canonical in provenance_by_canonical or canonical in ledger_by_canonical:
            raise SystemExit(f"new canonical already exists: {canonical}")
        alias_targets = dict(item["aliases"])
        term_rows = {canonical: item["target"], **alias_targets}
        for term, target in term_rows.items():
            if term in by_term and by_term[term]["target_zh"] != target:
                raise SystemExit(f"new term collision: {term}")
            if term not in by_term:
                row = {
                    "source_en": term,
                    "target_zh": target,
                    "type": item["type"],
                    "case_sensitive": "true",
                    "confidence": "high" if item["confidence"] != "editorial" else "medium",
                    "notes": f"开放终审：{item['rationale']}",
                }
                rows.append(row)
                by_term[term] = row
        record = {
            "canonical": canonical,
            "aliases": sorted(alias_targets, key=str.casefold),
            "reference_label": item["reference_label"],
            "reference_url": item["reference_url"],
            "evidence": item["evidence"],
            "rationale": item["rationale"],
            "alternatives": item["alternatives"],
            "status": "verified",
        }
        provenance[item["origin"]].append(record)
        provenance_by_canonical[canonical] = (item["origin"], record)
        audit = {
            "canonical": canonical,
            "origin": item["origin"],
            "type": item["type"],
            "target_before": None,
            "target_final": item["target"],
            "alias_targets_final": alias_targets,
            "decision": "add",
            "basis": item["basis"],
            "confidence": item["confidence"],
            "evidence_locators": item["locators"] + [item["reference_url"]],
            "audit_note": item["rationale"],
            "reviewed_at": DATE,
        }
        ledger.append(audit)
        ledger_by_canonical[canonical] = audit

    rows.sort(key=lambda row: (row["source_en"].casefold(), row["source_en"]))
    with glossary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    for origin, path in provenance_paths.items():
        provenance[origin].sort(key=lambda row: (row["canonical"].casefold(), row["canonical"]))
        write_jsonl(path, provenance[origin])
    ledger.sort(key=lambda row: (row["canonical"].casefold(), row["canonical"]))
    write_jsonl(ledger_path, ledger)

    changed_k97, _ = apply_translations(ROOT / "translations_k97")
    changed_k83, _ = apply_translations(ROOT / "translations_k83")

    link_path = ROOT / "glossary/link_targets.csv"
    with link_path.open("r", encoding="utf-8-sig", newline="") as handle:
        link_rows = list(csv.DictReader(handle))
        link_fields = list(link_rows[0].keys())
    for row in link_rows:
        if row["source_en"] == "Ivory Dove":
            row["target_zh"] = "骨白鸽"
        if row["source_en"] in {"Lark", "lark"}:
            row["target_zh"] = "百灵鸟"
    with link_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=link_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(link_rows)

    quote_path = ROOT / "glossary/quote_provenance.jsonl"
    quotes = load_jsonl(quote_path)
    quote = next(row for row in quotes if row["path_id"] == 12)
    quote.update(
        {
            "source_zh": "《兰花变容》",
            "reference_label": "《密教模拟器》Wiki：《兰花变容·卷三：午时》",
            "reference_url": CS_NOON,
            "evidence": "本作可见题签只写系列名《兰花变容》；引文内容可精确定位到第三卷《午时》，且《密教模拟器》与《司辰之书》官中均固定使用“以狮背为王座者／唤醒之语／三膜之门”。",
        }
    )
    chandler_quote = next(row for row in quotes if row["path_id"] == 21)
    chandler_quote.update(
        {
            "source_zh": "《制烛人的传说》",
            "reference_label": "《司辰之书》现行官中：制烛人的传说",
            "reference_url": BOH_HOME,
            "evidence": "本机《司辰之书》对完全相同题名 The Chandler's Tale 使用“制烛人的传说”；本作引文沿用该题名并署 J. N. Sinombre。",
        }
    )
    write_jsonl(quote_path, quotes)

    print(
        json.dumps(
            {
                "new_concepts": len(NEW_SPECS),
                "alias_families": len(ALIAS_ADDITIONS),
                "changed_existing": len(EXISTING_CHANGES),
                "translation_rows_k97": changed_k97,
                "translation_rows_k83": changed_k83,
                "active_glossary_terms": len(rows),
                "audit_verdicts": len(ledger),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
