#!/usr/bin/env python3
"""Apply reviewed inflection/derivation families in their complete sentences."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "TAN-0310FE2C267F": "要更换装束，请找到衣柜区域。",
    "TAN-1D779AD34C25": "穿上这套装束",
    "TAN-23AB3B1CA0FC": "已解锁装束：{0}",
    "TAN-49690454E285": "已穿上装束：{0}",
    "TAN-498A6ED9A712": "‘绅士冒汗，淑女容光焕发，马才流汗。’所以，我没有流汗。不过换身轻薄些的衣服，我会稍微舒服一点。\n\n[更轻便的装束会提供少量加成。]",
    "TAN-583F98EFBAF6": "天气太热，实在不该穿这身。既不舒服，又显得尴尬。\n\n[换上更轻便的装束——或者留在室内。]",
    "TAN-6DFF83BE4F0D": "当前装束",
    "TAN-84FBD55E76E9": "风穿透单薄衣料，直接贴上我的皮肤。\n\n[换上更保暖的装束——或者留在室内。]",
    "TAN-894C58EA5463": "失去装束：{0}",
    "TAN-A534802CADF6": "[考虑我的装束选择。]",
    "TAN-AB14548BFD57": "一个包扎整齐、内装新装束的包裹。",
    "TAN-D96E994BB649": "这帮无赖从女人的鞋里抽牌，赌注也不大。输不掉你的衬衣——你穿的别的什么装束，也输不掉。",
    "TAN-08FA6E1939EE": "布莱克伍德是一位英国著名鬼故事作家的姓氏；是一份文风恶毒却颇有趣味的苏格兰文学杂志的刊名；而‘瑟雷诺·布莱克伍德’又是个广为使用的秘学化名。\n\n当然，[[Serena]]·布莱克伍德也是一位前任司书的名字——她待我不薄。",
    "TAN-C47BEE97D79D": "对，正是。上面有列文森的签名——那位预示未来的司书。",
    "TAN-6864EE55C304": "当真？我记得那里有位司书，自称有“预示”之才。也就是说——他写出作品，署上别人的名字——而那些人其实要到后来才会写出同样的作品。是个有意思的病例。就心理而言如此；或许还不止于心理。",
    "TAN-313541C62A2A": "司机转过头。邦国民兵团那顶缀着伽马徽章的帽子下，目光沉稳；他与我对视了片刻。",
    "TAN-4005C6761F4D": "这点小钱？赌场和民兵团哪有闲心管。可我们也不能把你拖进什么<i>犯禁</i>的勾当……",
    "TAN-4FC58A53A4C3": "可要是情报不准呢？我就有<i>两个</i>名字可以上报。所以当心！民兵团的莱昂已经练就了一副能嗅出谎言的鼻子。",
    "TAN-6A4064EC8CC1": "先生，民兵团不提供这种服务。请把您的淫欲带去那些“宽容之家”。",
    "TAN-D4D15360B3B2": "如果[[Skill]]挑战失败，你可以动用性相池中任何与该[[Skill]]的[[Aspects]]相匹配的点数，尝试强行取得成功。\n\n如果点数足够，点击分配，然后选择“成功”。\n\n不过，有时即使点数足够，你也会选择“认输”。或许你担心性相池点数不够应付后面的挑战。",
    "TAN-EC9E6DCEEB4B": "只消片刻，几只杯沿便沾上了一层淡淡的惑心术。",
    "TAN-7F43BCE9BAB4": "宁娜的踪迹通往昂蒂布城外不远的“今日”疗养院。",
    "TAN-EBFBADEBA613": "“通往其圣域的门，是名为‘今日’的疗养院隐秘房间里的一尊兽像……”",
    "TAN-4DF86A78A626": "他未必会像自己以为的那样喜欢这场变易。夜觉得很好笑。",
    "TAN-A9C8429BE729": "这场变易就是你住进疗养院的原因吗？",
    "TAN-AD6B80497C0F": "从宁娜改为无人",
}


def load(path: Path) -> list[dict]:
    return [json.loads(raw) for raw in path.read_text(encoding="utf-8-sig").splitlines() if raw]


def write(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")


def main() -> int:
    summary={}
    for directory in (ROOT/"translations_k97",ROOT/"translations_k83"):
        seen=set();changed=0
        for path in sorted(directory.glob("chunk_*.jsonl")):
            rows=load(path);dirty=False
            for row in rows:
                if row["id"] in TARGETS:
                    seen.add(row["id"])
                    if row["translation"]!=TARGETS[row["id"]]:
                        row["translation"]=TARGETS[row["id"]];dirty=True;changed+=1
                        row["notes"]=(row.get("notes","").rstrip("； ")+"；开放终审：按完整词形族与当前句法统一。" ).lstrip("；")
                if row["id"]=="TAN-560B3D164FC3":
                    before=row["translation"]
                    row["translation"]=row["translation"].replace("“必需之印”","“必然之印”").replace("本体梦理协调局 +","本体梦理协调办公室 +")
                    if row["translation"]!=before:dirty=True;changed+=1
            if dirty:write(path,rows)
        missing=set(TARGETS)-seen
        if missing:raise SystemExit(f"missing target ids in {directory}: {sorted(missing)}")
        summary[directory.name]=changed
    print(json.dumps({"targeted_rows":len(TARGETS),"changes":summary},ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":raise SystemExit(main())
