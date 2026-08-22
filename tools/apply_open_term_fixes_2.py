#!/usr/bin/env python3
"""Apply the second, current-game open-set terminology tranche."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from apply_open_term_fixes import DATE, ROOT, TAN, BOH_HOME, CS_HOME, spec


SPECS = [
    spec("Advisor", "顾问", "设定存在称号", aliases={"Advisory Entity":"顾问实体"}, reference_label="《夜游漫记》东欧政治脚注", reference_url=TAN,
         evidence="Advisor/Advisory Entity 是 Steel 在部长会议与伊加利亚派政治体系中的公开职能称号，并非普通临时顾问。",
         rationale="译“顾问／顾问实体”，保留官僚宣传语气，并与 Steel“钢铁”本体称号分开。",
         alternatives="“参谋”偏军事；“咨询体”不符合政治机构用语。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-75A3463D3320","TAN:TAN-CAC1CEB21899"]),
    spec("Aprowl", "游猎", "状态", reference_label="《夜游漫记》夜间状态与条件标识", reference_url=TAN,
         evidence="Aprowl 是 a-prowl 的合写状态标签；触发后人物会在夜间外出四处行动。小写 aprowl 是逻辑条件键，不作玩家术语。",
         rationale="译“游猎”，兼具四处潜行与主动搜寻猎物的行动感。",
         alternatives="“在外闲逛”太口语；把小写逻辑键也翻译会破坏条件语义。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-0CF56DE6A703","TAN:TAN-94B1ADAD8BDF"]),
    spec("Change", "变易", "机制阶段", reference_label="《夜游漫记》介壳种变化机制", reference_url=TAN,
         evidence="大写 Change 是 Cross 个人晋升最终阶段与相关 UI 的独立机制标签，现有整字段稳定译“变易”。",
         rationale="定名“变易”，比普通“变化”更像秘术阶段，也能承接形体与身份的根本改造。",
         alternatives="“改变”过于日常；“蜕变”会与 Ecdysis 等既有脱壳意象撞词。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-4DF86A78A626"]),
    spec("Concede", "认输", "检定操作", reference_label="《夜游漫记》技艺检定按钮", reference_url=TAN,
         evidence="检定点数不足或玩家不愿继续投入时，Concede 按钮结束挽救流程并接受失败。",
         rationale="按钮译“认输”，短促且准确表达主动停止争取成功。",
         alternatives="“让步”像谈判行为；“放弃”未必包含承认本次失败。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-696320FB22DA"]),
    spec("Crafting", "制作", "机制", reference_label="《夜游漫记》制作教程与 HUD", reference_url=TAN,
         evidence="Crafting 统摄配方、场所、材料、收取成品与制作树，是完整游戏子系统。",
         rationale="机制名译“制作”，适用于教程、按钮和过程说明；具体 craft 动词再按句法处理。",
         alternatives="“合成”把手艺与仪式误成材料拼装；“工艺”更像知识门类。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-0A29453890CD"]),
    spec("Daffer", "达弗", "结局专名", reference_label="《夜游漫记》Daffer 结局与状态", reference_url=TAN,
         evidence="Daffer 同时出现在结局名、报告与内部状态中，游戏尚未解释其词源，但确定为跨地区复现的同一专名。",
         rationale="统一音译“达弗”，在设定未释义前不擅自意译身份或阵营。",
         alternatives="按 daffy 猜译“疯子”会提前坐实未公布设定；各处另译会破坏线索。", basis="editorial_transliteration", confidence="editorial", locators=["TAN:TAN-72AAA90324F2","TAN:TAN-91DC5325FF25"]),
    spec("Exhibits", "展品", "对话机制", reference_label="《夜游漫记》对话陈列机制", reference_url=TAN,
         evidence="Exhibits 是对话桌面上可展示、清除并触发回应的一组对象，不是普通博物馆展览。",
         rationale="译“展品”，保持可摆放对象的名词身份，并与 Dialogue Exhibit 一致。",
         alternatives="“展示”是动作；“陈列物”较生硬且不利于短 UI。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-CA7206ED7A9C"]),
    spec("Favour", "人情", "任务资源", aliases={"Favours":"人情"}, reference_label="《夜游漫记》奈尼娅任务线", reference_url=TAN,
         evidence="Favour/Favours 是可欠下、履行和累计的任务关系资源；奈尼娅会以引见交换一桩人情。",
         rationale="译“人情”，兼顾互惠债务与关系纽带；复数中文不变。",
         alternatives="“恩惠”偏单向施予；“好感”会与 Opinion 关系数值混淆。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-AE37A7A3BB08","TAN:TAN-CD2AA9BB345C"]),
    spec("Karlshorst Fleck", "卡尔斯霍斯特斑币", "架空货币", aliases={"Fleck":"斑币"}, reference_label="《夜游漫记》卡尔斯霍斯特身份章", reference_url=TAN,
         evidence="物品由部委卡尔斯霍斯特总部签发，把星辰金属薄片贴在黑卡上作为身份证章，并作为架空货币/信物命名。",
         rationale="定名“卡尔斯霍斯特斑币”，Fleck 译“斑币”，保留薄片、斑点和币状信物的复合观感。",
         alternatives="只译“碎片”丢失独立物品名；“弗莱克”无法传达金属斑片意象。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-555ED93E460D","TAN:TAN-99FD1ACDA339"]),
    spec("Hives", "蜂巢", "设定实体", reference_label="《夜游漫记》东欧异象", reference_url=TAN,
         evidence="大写 Hives 在银色天空与空隔都上方‘升起’，是政治—超自然异象，不是普通养蜂箱。",
         rationale="译“蜂巢”，保留群体结构和正在拔地而起的建筑/生物双重不安。",
         alternatives="“蜂群”没有巢体；音译会抹掉原文明确意象。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-28A1824C921B"]),
    spec("Lammastide", "收获节", "节期", reference_label="Lammas 节期与《夜游漫记》回忆", reference_url="https://www.britannica.com/topic/Lammas",
         evidence="Lammastide 是英国 Lammas 前后节期；文本出现祝福果实、保存受祝福面包皮等收获仪式。",
         rationale="译“收获节”，在标题中自然可读，并由仪式细节明确其节期功能。",
         alternatives="纯音译“拉玛斯节”需要额外解释；“面包弥撒节”只呈现词源一面。", basis="external_authority", confidence="strong", locators=["TAN:TAN-21C5591CD857","TAN:TAN-982D652FEADD"]),
    spec("Lantern-long", "灯之长生者", "设定位阶", origin="predecessor", reference_label="《密教模拟器》官中：灯之长生者", reference_url=CS_HOME,
         evidence="《密教模拟器》结局、招募与袭击提示把 Lantern-long 固定译为“灯之长生者”。",
         rationale="沿用“灯之长生者”，用准则“灯”限定 Long 位阶。",
         alternatives="“灯笼长生者”误解准则；“光明不死者”丢失精确位阶。", basis="predecessor_official_corpus", confidence="fixed", locators=["Cultist Simulator:recipes/apostle_lantern_greatwork.json#apostlelantern.recruitkleidouchos.teresa","TAN:TAN-271E33F47EC1"]),
    spec("Librairie des Heures", "司辰书店", "地点", reference_label="《夜游漫记》昂蒂布书店", reference_url=TAN,
         evidence="该法语店名在安德蕾、招牌与债务文本中反复出现；Heures 又有‘诸司辰/小时’双关。",
         rationale="译“司辰书店”，让玩家识别系列双关，同时保留它确为书店的功能。",
         alternatives="“时间书店”只取普通 heures；全保留法语不利于地图识别。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-092D30089982","TAN:TAN-8DD498F0B540"]),
    spec("Librarian", "司书", "职衔", aliases={"Librarians":"司书"}, origin="predecessor", reference_label="《司辰之书》官中职衔", reference_url=BOH_HOME,
         evidence="秘史系列将噤声居屋与守夜人之树的 Librarian 作为正式职衔；本作指瑟雷娜等同一传统的任职者。",
         rationale="职衔统一为“司书”，区别于普通公共图书馆工作人员的描述性“图书管理员”。",
         alternatives="同一角色混用“图书管理员／司书”会让正式位阶失焦。", basis="predecessor_official_corpus", confidence="fixed", locators=["TAN:TAN-E8A6548B61EA","TAN:TAN-55E881406ED1"]),
    spec("Limian", "利米亚", "设定形容词", origin="predecessor", reference_label="利米亚教团词形", reference_url="https://cultist.huijiwiki.com/wiki/利米亚教团",
         evidence="Limian 是 Ordo Limiae 的形容词，修饰其传统与教律；本作仍指同一教团体系。",
         rationale="译“利米亚”，与既定“利米亚教团”共享词根，具体名词由后接 tradition/Discipline 表达。",
         alternatives="“利米安”多添人名式尾音，破坏与 Limiae 的统一。", basis="predecessor_official_corpus", confidence="fixed", locators=["TAN:TAN-2F5338A6F0E9","TAN:TAN-4CA80B8A3F96"]),
    spec("Man of Mystery", "神秘人", "装束名", reference_label="《夜游漫记》装束与订单", reference_url=TAN,
         evidence="该名称在装束解锁、订单、包裹与标签四处稳定出现，是一套刻意营造神秘感的固定装束。",
         rationale="定名“神秘人”，简短如戏剧角色称号，也适合服装订单。",
         alternatives="“谜之男子”带日式语感；“神秘先生”擅加礼貌称谓。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-DD4EADE49EDD","TAN:TAN-F75869051BE4"]),
    spec("Milice", "民兵团", "历史组织", reference_label="维希法国 Milice 与本作昂蒂布对白", reference_url="https://www.britannica.com/topic/Milice",
         evidence="法语大写 Milice 指维希政权的准军事民兵组织；本作人物以其逮捕、盘查与威吓职能谈及。",
         rationale="译“民兵团”，既保留组织性质，也区别普通泛称 militia。",
         alternatives="只译“民兵”可能被看作零散人员；保留 Milice 不利于理解历史威胁。", basis="external_authority", confidence="strong", locators=["TAN:TAN-10584AC68CCB","TAN:TAN-6F9A16E302F4"]),
    spec("Nest", "巢", "设定倾向", reference_label="《夜游漫记》介壳种政治脚注", reference_url=TAN,
         evidence="大写 Nest 是介壳种的一种野性、绝不妥协的 tendency，并在并列异象中以 seething Nest 再现。",
         rationale="译“巢”，保持单字本体意象；句中可组合为“巢之倾向／沸腾的巢”。",
         alternatives="“巢穴派”过早坐实为组织；“筑巢性”只剩行为。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-570323D86B2E","TAN:TAN-31FB41158829"]),
    spec("Oath", "誓言", "设定异象", reference_label="《夜游漫记》战后东欧脚注", reference_url=TAN,
         evidence="大写 Oath 与 Nest、Stars 等异象并列，是受诅士兵从地下寻回的血腥誓约；另有库夫拉誓言作历史近邻。",
         rationale="译“誓言”，保持可被立下、履行又被寻回的抽象实体性。",
         alternatives="“盟约”会与 covenant 体系混淆；“誓物”擅加物质形态。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-570323D86B2E"]),
    spec("Ostiary", "司阍", "职衔", reference_label="教会 ostiary 职分与本作复合职衔", reference_url="https://www.newadvent.org/cathen/11344a.htm",
         evidence="Ostiary 是传统教会司门职分；本作 Detective-Ostiary 把侦探与门槛守卫职责复合。",
         rationale="译“司阍”，是中文现成的守门职称，也保留古老教会职分感。",
         alternatives="“门卫”过于现代日常；“奥斯提亚里”无语义信息。", basis="language_or_professional_reference", confidence="strong", locators=["TAN:TAN-1A1F7D58303D"]),
    spec("Passion slot", "心念栏位", "UI机制", reference_label="《夜游漫记》心念获取说明", reference_url=TAN,
         evidence="角色只能在空余 Passion slot 中取得或重新考虑心念；它是角色构筑的明确容量单位。",
         rationale="译“心念栏位”，与 Passion“心念”同词根，并用栏位表达 UI 容量。",
         alternatives="“激情槽”沿用错误旧名；“心念格”过于口语。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-09F54EE53147"]),
    spec("Possessed", "着魔", "心念状态标记", reference_label="《夜游漫记》潜在心念分支", reference_url=TAN,
         evidence="方括号 Possessed 标记已被某心念占据/附着的分支，八类心念获取对白共用。",
         rationale="译“着魔”，保留被心念占据的双关与角色不由自主感。",
         alternatives="旧读“已有”只说明持有状态，抹掉 possessed 的叙事语气；普通 possessed 仍按附身句法处理。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-1394F4CE2992","TAN:TAN-952EAFC4FBE3"]),
    spec("Pyx Jar", "圣体盒内罐", "宗教器物", reference_label="pyx 器物结构与《夜游漫记》物品标签", reference_url="https://www.britannica.com/topic/pyx",
         evidence="pyx 是盛放圣体的小盒；标签特加 Jar，表示盒中另置的罐状内胆。",
         rationale="译“圣体盒内罐”，明确它不是整只圣体盒，而是其中的罐。",
         alternatives="“圣体罐”可能误成独立礼仪器；“皮克斯罐”纯音译。", basis="language_or_professional_reference", confidence="strong", locators=["TAN:TAN-E9B04875DDC4"]),
    spec("Naenian Quittance", "挽歌解契", "秘术物品", aliases={"Quittance":"解契"}, reference_label="Naenia / quittance 构词与物品标签", reference_url="https://www.merriam-webster.com/dictionary/quittance",
         evidence="Naenia 指挽歌；quittance 指清偿、解除债务或义务。物品名把哀悼与解除契约结合。",
         rationale="译“挽歌解契”，既呈现 Naenia 的哀歌，也用“解契”表达解除义务。",
         alternatives="“奈尼娅收据”把拉丁词误作人物所有格与普通票据；“挽歌清偿”不像物品名。", basis="language_or_professional_reference", confidence="strong", locators=["TAN:TAN-5B54D525AE5A"]),
    spec("Reason", "理性", "魂质概念", reference_label="《夜游漫记》魂质说明", reference_url=TAN,
         evidence="大写 Reason 被定义为灵魂最上层、具有白昼理解能力的组成，不是句中的普通理由。",
         rationale="译“理性”，采用哲学与心理学通名，并对应 daylight understanding。",
         alternatives="“理由”误作论证原因；“智性”会抬高为特定经院哲学官能。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-04F557A4305C"]),
    spec("Sanitarium Aujourd'hui", "“今日”疗养院", "地点", reference_label="《夜游漫记》疗养院地点名", reference_url=TAN,
         evidence="全名在人物指路、地图与对话中反复出现；Aujourd'hui 是法语“今日”，构成刻意古怪的院名。",
         rationale="定名““今日”疗养院”，把法语词义显给玩家，同时用引号保留名称感。",
         alternatives="全音译“奥茹尔迪”无助理解；只写“疗养院”丢失专名。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-2D166A778158"]),
    spec("soul-complexus", "灵魂复合体", "设定构造", reference_label="《夜游漫记》蠕虫抽离对白", reference_url=TAN,
         evidence="蠕虫被从主角的 soul-complexus 中抽出；complexus 强调灵魂多部分交织成整体，而非单一灵魂。",
         rationale="译“灵魂复合体”，保留复合结构与近技术性秘术语气。",
         alternatives="“灵魂丛”过于生物化；“心灵情结”误借心理分析 complex。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-B4950570FAF4"]),
    spec("Sparkflake", "火花薄片", "秘术物品", reference_label="《夜游漫记》物品标签", reference_url=TAN,
         evidence="Sparkflake 是可持有、使用的单体物品名，构词把 spark 的火光与 flake 的薄片结合。",
         rationale="译“火花薄片”，逐项保留材料形态与发光意象。",
         alternatives="“火屑”易被理解为灰烬；音译无法说明可见物性。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-D61F82B7DB65"]),
    spec("spidermist", "蛛雾", "设定灾害", reference_label="《夜游漫记》夜间与军旅对白", reference_url=TAN,
         evidence="spidermist 会在沟渠、夜路与昂蒂布外袭击人，又可被特殊饮料驱退，是稳定的超自然环境威胁。",
         rationale="译“蛛雾”，紧缩 spider+mist，并保留雾中有捕食性存在的含混。",
         alternatives="“蜘蛛雾”口语笨重；“丝雾”抹掉危险来源。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-38D39AD92EEA","TAN:TAN-A7DB863C69F0"]),
    spec("Spontaneity", "随性", "选择类别", reference_label="《夜游漫记》心念选择标签", reference_url=TAN,
         evidence="[Spontaneity] 标记不为功利目的、临时起意的选择，形容词 spontaneous 在相邻回应中同义复现。",
         rationale="译“随性”，自然覆盖名词标签与‘真够随性的’派生句。",
         alternatives="“自发性”像学术概念；“冲动”强加负面失控。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-8690166785B9","TAN:TAN-BC3C06DCDB7F"]),
    spec("Stars", "群星", "设定集体", reference_label="《夜游漫记》东欧政治脚注", reference_url=TAN,
         evidence="大写 Stars 是来自天外、综合命运并担保多利亚币的集体存在，同时作为政权监视与星辰双关。",
         rationale="译“群星”，保持复数集体与天象表层；普通 stars 仍按繁星处理。",
         alternatives="“星辰”难显集体主语；“群星体”擅加实体类别。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-CAC1CEB21899","TAN:TAN-59D2C2CBB0A0"]),
    spec("Steel", "钢铁", "设定存在", reference_label="《夜游漫记》部长会议顾问实体", reference_url=TAN,
         evidence="大写 Steel 以强大而叔父般的 gaze 监督群星，被称为部长会议顾问实体；它不是句中的普通金属。",
         rationale="译“钢铁”，保留工业政治意象与不可数物质名的非人格压迫感。",
         alternatives="“钢铁者”擅自人格化；“斯蒂尔”会丢失宣传象征。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-CAC1CEB21899"]),
    spec("Succeed", "成功", "检定操作", reference_label="《夜游漫记》技艺检定按钮", reference_url=TAN,
         evidence="分配足够性相池点数后，Succeed 按钮确认强制成功，与 Concede 构成操作对。",
         rationale="按钮译“成功”，与结果标签 Success 同根且简洁。",
         alternatives="“通过”容易与门扉/旅行混淆；“获胜”把检定误作竞赛。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-2EA80F73C575","TAN:TAN-D4D15360B3B2"]),
    spec("Summer Frivolity", "夏日轻佻", "装束名", reference_label="《夜游漫记》衣柜装束", reference_url=TAN,
         evidence="该名称在解锁、包裹、订单和装束标签中稳定复现，是夏季轻薄社交装束。",
         rationale="定名“夏日轻佻”，保留季节、轻快与稍逾礼法的 frivolity 语气。",
         alternatives="“夏日轻浮”贬义过强；“夏日嬉游”丢失衣着观感。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-2D845BC8573A","TAN:TAN-628F0F0AAE86"]),
    spec("Surveillante", "督导", "女性职衔", reference_label="法语 surveillante 与疗养院职务", reference_url="https://www.collinsdictionary.com/dictionary/french-english/surveillant",
         evidence="Surveillante 是法语阴性监管职衔，Odette 在疗养院以此身份出现。",
         rationale="译“督导”，兼顾监管与护理机构职务，不在中文中强标性别。",
         alternatives="“女看守”过于监狱化；音译无法说明职能。", basis="language_or_professional_reference", confidence="strong", locators=["TAN:TAN-1FDF6E2379E2"]),
    spec("The Sheaf", "《禾捆》", "报刊名", aliases={"'The Sheaf'":"《禾捆》","THE SHEAF":"《禾捆》"}, reference_label="《夜游漫记》邦国报纸", reference_url=TAN,
         evidence="同一报纸在椅上实物、阅读标签和全大写报头三处出现；sheaf 指捆扎的禾秆，也暗合国家宣传。",
         rationale="定名《禾捆》，采用书报名号并保留农作物集束意象。",
         alternatives="旧 notes 的《麦束报》与实际三处《禾捆》不一致；“一捆”不像报刊名。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-4A06094155AF","TAN:TAN-F19FA8B1C2F1"]),
    spec("Trenchcoat Brigade", "风衣旅团", "戏称群体", reference_label="《夜游漫记》人物对白与标签", reference_url=TAN,
         evidence="该称呼在多段对白中指一群穿风衣行动的人，是带揶揄色彩的固定群体绰号。",
         rationale="译“风衣旅团”，保留 trenchcoat 的醒目服饰与 Brigade 的半军事夸张。",
         alternatives="“风衣帮”过于黑帮化；“堑壕外套旅”误拆 trench coat。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-1B76758FA35E"]),
    spec("Twin-visions", "双生异象", "设定现象", reference_label="《夜游漫记》修道院说明", reference_url=TAN,
         evidence="Twin-visions 与鲜活之书、流亡先知和有毒修女并列为修道院著名异象，采用连字符构成固定复数名。",
         rationale="译“双生异象”，保留 twin 的成对/孪生与 visions 的神视含义。",
         alternatives="“双重幻觉”预设为不真实病症；“孪生视觉”误成生理能力。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-1EBAB4B3CCE1"]),
    spec("Unworldly", "异世", "技艺类别形容词", reference_label="《夜游漫记》九艺与制作说明", reference_url=TAN,
         evidence="Unworldly 与 Worldly 技艺对举，专指需要准备、能制作秘术工具的九大异世技艺。",
         rationale="译“异世”，可自然组合“异世技艺”，也保留不属于日常世界之义。",
         alternatives="“超凡”偏褒义；“非世俗”只作否定，缺少另一世界感。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-649BC6B7E95F","TAN:TAN-D9360D54BB5A"]),
    spec("Welland", "韦兰", "人物", origin="predecessor", reference_label="《密教模拟器》官中：韦兰上尉", reference_url="https://cultist.huijiwiki.com/wiki/韦兰上尉",
         evidence="《密教模拟器》同一铸之长生者 Captain Welland 官中为“韦兰上尉”；本作提到同一组织、战争经历与人物。",
         rationale="沿用姓氏“韦兰”，撤销无依据多出的词尾“德”。",
         alternatives="旧译“韦兰德”会与同一前作人物形成异名。", basis="predecessor_official_same_id", confidence="fixed", locators=["Cultist Simulator:recipes/long_recipes.json#long.revealidentity.success","TAN:TAN-8FBE945D7B4E"]),
    spec("Zouche", "祖什", "专名", reference_label="《夜游漫记》单独标签", reference_url=TAN,
         evidence="Zouche 以独立玩家可见标签出现，资产没有给出可支持意译的定义或普通词义。",
         rationale="音译“祖什”，保留短促专名形态，等待后续剧情提供身份而不先行猜测。",
         alternatives="按法语 touche 等近形词意译没有文本依据。", basis="editorial_transliteration", confidence="editorial", locators=["TAN:TAN-22CCA687C806"]),
    spec("outer oceans", "外层诸海", "设定地理", reference_label="《夜游漫记》西农布尔对白", reference_url=TAN,
         evidence="说话者把 outer oceans 当作曾穿越的多重外层海域，并与非人旅行经历相连，不是普通近海。",
         rationale="译“外层诸海”，复数“诸海”保留多重海域，“外层”保留世界层级。",
         alternatives="“外海”会被理解为离岸海域；“外洋”丢失复数世界感。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-7CAF5FB7E9F2"]),
    spec("commedia della Sole", "太阳喜剧", "设定戏剧形式", reference_label="《夜游漫记》神圣剧本文稿", reference_url=TAN,
         evidence="该意大利语式短语标记一种有神圣 scenario 的设定戏剧形式，结构刻意仿 commedia dell'arte。",
         rationale="译“太阳喜剧”，让玩家读出太阳主题与喜剧形式；原文斜体仍保留异语感。",
         alternatives="全音译无法理解；“太阳即兴喜剧”擅加即兴表演属性。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-DDF11E194A78"]),
    spec("nightstalking", "夜间潜行", "夜间行动", reference_label="《夜游漫记》起夜教程", reference_url=TAN,
         evidence="玩家起夜后可完成 nightstalking 再回床睡余下几小时，指夜间隐秘外出的一组行动。",
         rationale="译“夜间潜行”，同时表达时间与隐秘移动，不把它误作狩猎专名。",
         alternatives="“夜猎”擅加猎物；“夜行”缺少 stealth/stalking 的谨慎感。", basis="current_asset_semantics", confidence="strong", locators=["TAN:TAN-A58B9173E5FC"]),
]

SOURCE_REPLACEMENTS = [
    ("Welland", "韦兰德", "韦兰"),
]

ROW_UPDATES = {
    "TAN-CE233C7BC3C9": "天国府邸；人们既将其作为整体崇拜，也分别崇拜构成它的诸位[[Hours]]。自从其诸要素间爆发大战以来，它日日显露不安——以征兆，以阴影，以一抹蜷曲的血色。",
    "TAN-C752DC49E97A": "原稿猎人，遗产搜刮人……雇佣兵？许多人会质疑他的道德操守；但少有人会否认他的洞察力。",
    "TAN-9C8D2D26BAB1": "每重选择皆有其影。",
    "TAN-A51D2FD45F4A": "手艺唯有通过指尖的触碰方能学习。",
    "TAN-CE86409E7ED8": "很难说得清——但我还是明白了。",
}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(raw) for raw in path.read_text(encoding="utf-8-sig").splitlines() if raw]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")


def main() -> int:
    glossary_path = ROOT / "glossary/glossary.csv"
    with glossary_path.open("r", encoding="utf-8-sig", newline="") as handle:
        glossary_rows = list(csv.DictReader(handle)); fields = list(glossary_rows[0])
    glossary = {row["source_en"]: row for row in glossary_rows}
    prov_paths = {o: ROOT / f"glossary/provenance/{o}.jsonl" for o in ("predecessor","travelling_new","real_world","editorial")}
    prov = {o: load_jsonl(p) for o,p in prov_paths.items()}
    canonicals = {row["canonical"] for rows in prov.values() for row in rows}
    ledger_path = ROOT / "glossary/final_term_audit.jsonl"; ledger = load_jsonl(ledger_path); audited = {r["canonical"] for r in ledger}

    for item in SPECS:
        if item["canonical"] in glossary or item["canonical"] in canonicals or item["canonical"] in audited:
            raise SystemExit(f"new concept collision: {item['canonical']}")
        for term,target in {item["canonical"]:item["target"], **item["aliases"]}.items():
            if term in glossary and glossary[term]["target_zh"] != target: raise SystemExit(f"term collision: {term}")
            if term not in glossary:
                row={"source_en":term,"target_zh":target,"type":item["type"],"case_sensitive":"true","confidence":"high" if item["confidence"]!="editorial" else "medium","notes":f"开放终审：{item['rationale']}"}
                glossary_rows.append(row); glossary[term]=row
        prov[item["origin"]].append({"canonical":item["canonical"],"aliases":sorted(item["aliases"],key=str.casefold),"reference_label":item["reference_label"],"reference_url":item["reference_url"],"evidence":item["evidence"],"rationale":item["rationale"],"alternatives":item["alternatives"],"status":"verified"})
        ledger.append({"canonical":item["canonical"],"origin":item["origin"],"type":item["type"],"target_before":None,"target_final":item["target"],"alias_targets_final":item["aliases"],"decision":"add","basis":item["basis"],"confidence":item["confidence"],"evidence_locators":item["locators"]+[item["reference_url"]],"audit_note":item["rationale"],"reviewed_at":DATE})
        canonicals.add(item["canonical"]); audited.add(item["canonical"])

    glossary_rows.sort(key=lambda r:(r["source_en"].casefold(),r["source_en"]))
    with glossary_path.open("w",encoding="utf-8",newline="") as handle:
        w=csv.DictWriter(handle,fieldnames=fields,lineterminator="\n");w.writeheader();w.writerows(glossary_rows)
    for origin,path in prov_paths.items():
        prov[origin].sort(key=lambda r:(r["canonical"].casefold(),r["canonical"]));write_jsonl(path,prov[origin])
    ledger.sort(key=lambda r:(r["canonical"].casefold(),r["canonical"]));write_jsonl(ledger_path,ledger)

    counts={}
    for directory in (ROOT/"translations_k97",ROOT/"translations_k83"):
        changed=0; seen=set()
        for path in sorted(directory.glob("chunk_*.jsonl")):
            rows=load_jsonl(path);dirty=False
            for row in rows:
                before=row["translation"]
                if row["id"] in ROW_UPDATES: row["translation"]=ROW_UPDATES[row["id"]];seen.add(row["id"])
                for source_term,old,new in SOURCE_REPLACEMENTS:
                    if source_term in row["source"] and old in row["translation"]: row["translation"]=row["translation"].replace(old,new)
                if row["translation"]!=before:
                    dirty=True;changed+=1;row["notes"]=(row.get("notes","").rstrip("； ")+"；开放终审：按新发现的固定词形统一。" ).lstrip("；")
            if dirty: write_jsonl(path,rows)
        if set(ROW_UPDATES)-seen: raise SystemExit(f"missing ids in {directory}: {set(ROW_UPDATES)-seen}")
        counts[directory.name]=changed
    print(json.dumps({"new_concepts":len(SPECS),"translation_changes":counts,"glossary_terms":len(glossary_rows),"audit_verdicts":len(ledger)},ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__": raise SystemExit(main())
