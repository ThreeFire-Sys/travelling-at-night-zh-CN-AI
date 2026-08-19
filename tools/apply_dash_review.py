#!/usr/bin/env python3
"""Apply the final review of Chinese-only em-dash candidates."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXES = {
    "TAN-17D82AE9C6A3": "很高兴你竟能毫发无伤地活下来。甚至，请容我说，连军团惯有的沙漠肤色都没染上。",
    "TAN-39B5C033817F": "‘骄阳被分裂时，祂的具名者也一同破碎。’ \r\n\r\n[[Hours]]的具名者，是祂们最重要的仆从、侧面或流溢。有些，或许全部，具名者从前都是[[Long]]。\n\n[[Mansus]]灵体往往喜欢哄骗轻信的凡人，说自己是具名者。谁还会跟它们争辩真假？",
    "TAN-406F3D28E142": "利米亚教团（后称忘却会）常用这项仪式掩盖踪迹，尽管它本身便有引发迷狂的风险。",
    "TAN-4C4F2142C2F7": "VSTUPNÍ VÍZUM。正式签名落在正式印章上，印章饰以波希米亚双尾狮。捷克斯洛伐克尚不是人民共和国；还不算，还没完全算。  ",
    "TAN-54DA5EFBE1A9": "[[Moth]]逐光而行；但孩子们，请转向差异之子[[Cross]]，从中追索[[History]]。",
    "TAN-680E6D195044": "明澈的智识，无情的启示，金色的清明。灯是那处秘密所在（有时称为太阳的居屋，或[[Mansus]]）以及其上之光的准则。如今，它是西方的[[Corona]]与东方的[[Gleam]]；它的[[Hours]]已闭上双眼。",
    "TAN-75F5FC771CB8": "南特主教马上就要上车了！他把手提箱落下了！幸好，我是他的私人秘书，正拿着那件遗失的行李；只要<i>女检票员</i>放我过去，我就能交给他。不，我不需要车票，我要留在昂蒂布督办几项调查。",
    "TAN-96C181AC014A": "假如你是无限而不可知的统一体，要怎样才能让世间其他一切感知到你？怎样才能既包含万物，又只是一个“一”，而不是，你知道的，万物本身？尤其万物之中还有许多独一无二、彼此根本不同的东西。\n\n也许，你还可化作一个个独特的“一”：每一个本身都是绝对的统一体，又因其独特而区别于其他统一体。在[[seirai]]另一端，喧嚣纷繁的诸心智只能隐约触及它们。有人称这些“一”为“一者”；有人称它们为“[[Hours]]”；十字派信徒则称之为“异端”。",
}


def main() -> None:
    changed = 0
    for path in sorted((ROOT / "translations").glob("chunk_*.jsonl")):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines()]
        local = 0
        for row in rows:
            target = FIXES.get(row["id"])
            if target is None:
                continue
            row["translation"] = target
            row["notes"] = (row.get("notes", "") + " 破折号专项终审：改用更适合中文的逗号、括号或分号。 ").strip()
            local += 1
        if local:
            path.write_text(
                "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
                encoding="utf-8",
            )
            changed += local
    print(json.dumps({"reviewed": 9, "changed": changed, "retained_as_deliberate": ["TAN-07D8AA8F171D"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
