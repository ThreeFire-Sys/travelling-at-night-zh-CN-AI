#!/usr/bin/env python3
"""Apply the vetted j.18 delta and pre-rebase editorial corrections."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADDED = ROOT / "build" / "reviews" / "j18_v2_added.json"
SUPPLEMENT = ROOT / "build" / "reviews" / "j18_v2_supplement.jsonl"


NEW_ZH = {
    "TAN-021ACF68EDBA": "斯宾塞经历过许多职涯，但其中有一份，令他觉得自己属于那里。在黑暗中被掏空的漫长岁月里，他所有的[[Skills]]都已衰退——但源自那份职涯的技艺，衰退得最慢。\n\n以后，其他任何[[Skill]]都可以用[[Experiences]]习得或提升——但提升职涯技艺只需花费一半。",
    "TAN-0323CE515625": "试玩版无法从结局重新载入 :(",
    "TAN-0428D3D60967": "扎迦利·韦克菲尔德。沉静，谦和，坚韧。那时他是无神论者，我不是；可每逢秋日风暴撼动[[Hush House]]，他都会请我陪他坐一会儿。那声音太像炮火。\n\n后来，我们一同进了防剿[[Bureau]]。又过了很久，我才知道，有某种东西侵入了他；也才知道，他将它压制得比我曾做到的好得多。\n\n韦克菲尔德从来不是个快乐的人。夜常常兴高采烈地提醒我：韦克菲尔德和我有多少相似之处。",
    "TAN-134FD5B013D2": "我答应了泽莉娅的请求。可以照办——也可以试着骗她",
    "TAN-23C6F42550E6": "事情差一点便走向另一边。一年前，[[Icarians]]还与现实主义者联合执政，国家也准备接受艾奇逊使团的重建援助。顾问实体对此极为不满，伊加利亚派随即开始清洗。\n\n现实主义者试图抵抗。可是垂死的现实主义领袖贝奈什为恢复健康，走上了介壳种之途；而布拉格的[[Cross]]都是优秀的[[Icarians]]。如今，这里除了名字以外，已俨然是捷克斯洛伐克人民共和国。",
    "TAN-2E53BAAA4053": "日志里的一项计划提示了该怎么做。",
    "TAN-32216945D543": "卡住了？",
    "TAN-45D260388486": "此处得名于五百年前的雷根斯堡人纳坦；他曾来这里寻求庇护，以施行外科秘术。[[Great War]]令英国的医院挤满负伤的青年。来到[[Brancrug]]的那些人，身负不同寻常的伤势——常规医术对它们毫无办法。我记得……",
    "TAN-54CFC99F5471": "一知半解是件危险的事。漫无目的地胡乱使用秘术工具，往往只会令情况更糟。动手之前，务必先弄清楚自己在应付什么。 ",
    "TAN-578A613FA720": "不只是雷声，夜幸灾乐祸地说。你冒犯了栖居于此的力量。",
    "TAN-646EB496611C": "奥比耶医生声称，只要我在疗养院住上几天，他就会告诉我该去哪里找宁娜·拉格斯。",
    "TAN-7BF3D65A6212": "谨慎选择",
    "TAN-94255807CD4A": "这份煎蛋卷已经一点不剩，不过迟早还会再有。",
    "TAN-96A867A79CE5": "我叫奥比耶收回了他的提议。不过，这里多半还有别人能帮我找到宁娜·拉格斯。",
    "TAN-96CD21B9ED7D": "启用物品只要备在手边，就会为一项[[Skill]]提供修正。你最多可同时启用四件物品，但修正不会叠加——只取最佳的一项。四把锤子不会比一把更好用。\n\n有些物品累赘、危险或拿不出手，会施加负面修正。好消息是，既然永远只取最佳修正，任何一项加成都能抵消任意数量的减益。因此，某件物品若给一项[[Skill]]带来负面修正，任意正面修正都可抵消全部负面效果。",
    "TAN-A22CC4AFA9F0": "反复点击，似乎意味着你掉进了某种小小的寻路遗忘坑里？如果确是如此，可以试试选项菜单里紫色的“脱困！”按钮——它也许能把你解救出来。\n\n如果你只是点得兴起、点得恼火，或是渴望踏上禁地，那就抱歉打扰了，请继续。",
    "TAN-B04222F07610": "我本想在结尾放烟火。舞台监督否决了我。或许这样更好。",
    "TAN-CE3745EE7898": "通往白昼的门……",
    "TAN-DFD8E7203138": "还不行。我还有地方要探查。",
    "TAN-E2AF4E0D7000": "宁娜·拉格斯随一个名为“罗莎·蒙迪”的马戏团巡游。他们原定要去米马塔演出。",
    "TAN-EF869779A6A5": "我还没离开修院时，克里斯托弗·[[Illopoly]]便已放弃佩鲁贾的神学学位，出版了两部关于无形之术、成功得令人担忧的地下著作，还在索姆河战役中负过伤。伤愈之后，他非正式地替居屋办事。彼时的他，显得比我年长、睿智得多。我们常争论神学，也争论他对牛蒡茶那份荒唐的偏爱。",
    "TAN-F872ECBD3A23": "<i>虽有许多尚存……也已有许多被夺走。</i>\n\n一项[[Passion]]。\n\n[承认悔恨的选择属于悲恸之选。通常，选择沉默也是。]",
    "TAN-FACC9EBBBCB1": "我得知宁娜·拉格斯已经离开“今日”疗养院。这里一定有人知道她去了哪里。",
}


FIXES = {
    "TAN-792F429CD716": ("那还是算了。", "吸烟对话：Best not, then 指没有火便作罢，并非劝对方别去。"),
    "TAN-DE0D92F7DFED": ("驱灵师", "Steam 官方简中职涯名。"),
    "TAN-CC93F932FC0E": ("一名驱灵师", "Steam 官方简中职涯名。"),
    "TAN-B4016B177A90": ("一名\n魔术师", "Steam 官方简中职涯名；保留换行。"),
    "TAN-026039646FFB": ("魔术师", "Steam 官方简中职涯名；此处为职涯标签。"),
    "TAN-356AAB072F02": ("我把自己视作驱灵师……", "与 Steam 官方职涯名统一。"),
    "TAN-6507DE4D4FC6": ("把自己视作神父／驱灵师", "与 Steam 官方职涯名统一。"),
    "TAN-C42668E11016": ("我再也没法把这一切当回事。一个小小的驱灵师助手，守在序链末端，像追蝴蝶似的撵着灵体四处跑。", "seiral terminus 依普罗克洛斯神学语境译‘序链末端’。"),
    "TAN-6B4BC831990F": ("我是团里最年轻的随军神父，但沙勒神父将我收在羽翼之下；而沙勒神父是常任驱灵师。因此，我成了他的助手。在[[Cambray]]的灰烬与翻烂泥土中，在那些病入膏肓、支离破碎的地方，人们会叫我去为垂死者送上<i>临终圣体</i>——尤其当他们害怕死者随后会挣扎着再度爬起、骨头磨响如玻璃时。", "Exorcist 依官方职涯名统一；保留链接与斜体。"),
    "TAN-ABE9B286D3F9": ("斯坦尼斯拉夫·约翰·沙勒神父，不守陈规，却很仁厚。[[Great War]]期间，他担任多塞特郡团的常任驱灵师，我则做他的助手。他因我擅长“更隐微的工作”而将我举荐给主教，使我获任为[[Brancrug]]的本堂神父。也是他帮助我重返世间。", "Exorcist 依官方职涯名统一；保留链接。"),
    "TAN-FA29D06C5E1D": ("1919 年，大战的最后一年，我离开修院，自愿加入多塞特郡团担任随军神父；在那里，[[Stanislav]]将我训练成驱灵师。\n\n大战；我们当真以为，事情最坏也不过如此。过了二十年，才知道我们错得有多离谱。我并不遗憾自己错过了……", "Exorcist 依官方职涯名统一；保留链接与段落。"),
    "TAN-DB0433B66B0B": ("我就是这么学来的。那时我很年轻。后来战争爆发。一名战地驱灵师训练我做他的助手。斯坦尼斯拉夫神父。", "Exorcist 依官方职涯名统一。"),
    "TAN-3D5380CD8E2D": ("[Craft] 使用它。", "[Craft] 是引擎控制标记，必须原样保留。"),
    "TAN-74BF319435C4": ("[Craft] 旧日技艺，新式工具。", "[Craft] 是引擎控制标记，必须原样保留。"),
    "TAN-5F3595CEE64C": ("[END] 暂时没别的事了，医生。", "[END] 是引擎控制标记，必须原样保留。"),
    "TAN-B5686861B043": ("[Craft] 对赶时间的人来说，已经够神圣了。 ", "[Craft] 是引擎控制标记，必须原样保留；保留末尾空格。"),
    "TAN-E9A89E5E0818": ("[Craft] 干活。", "[Craft] 是引擎控制标记，必须原样保留。"),
    "TAN-05CAA104F6C8": ("[END] ", "[END] 是引擎控制标记，必须原样保留；保留末尾空格。"),
}


def main() -> None:
    added = json.loads(ADDED.read_text(encoding="utf-8"))
    assert {r["id"] for r in added} == set(NEW_ZH)
    with SUPPLEMENT.open("w", encoding="utf-8", newline="\n") as handle:
        for row in added:
            out = {
                "id": row["id"],
                "source": row["source"],
                "translation": NEW_ZH[row["id"]],
                "status": "translated",
                "notes": "2026.8.j.18 新增／改写字段；已按上下文人工终审。",
            }
            handle.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n")

    seen: set[str] = set()
    for chunk in sorted((ROOT / "translations").glob("chunk_*.jsonl")):
        rows = [json.loads(line) for line in chunk.read_text(encoding="utf-8").splitlines() if line]
        changed = False
        for row in rows:
            if row["id"] in FIXES:
                row["translation"], row["notes"] = FIXES[row["id"]]
                seen.add(row["id"])
                changed = True
        if changed:
            with chunk.open("w", encoding="utf-8", newline="\n") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    missing = set(FIXES) - seen
    if missing:
        raise SystemExit(f"missing correction IDs: {sorted(missing)}")
    print(json.dumps({"supplement": len(added), "corrected": len(seen)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
