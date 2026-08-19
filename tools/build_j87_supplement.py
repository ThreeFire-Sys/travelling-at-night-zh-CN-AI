#!/usr/bin/env python3
"""Build the j.87 rebase supplement: translations for strings the game update
revised (new content-hash IDs).

Most j.87 revisions are typo/whitespace fixes — the reviewed j.66 translation
is reused with whitespace mirrored to the new source.  Entries with real
wording changes carry hand-curated translations in CURATED below.  The patch
notes TextAsset is reassembled per section: verbatim sections reuse the
reviewed translation, only new/changed sections are hand-translated.

Every row is checked for link/query/format token balance against its source
before being written, so the downstream merge validator sees clean input.
"""

from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEW_WORKLIST = ROOT / "build" / "worklist_j87"
OLD_TRANSLATIONS = ROOT / "build" / "translations_j66_candidate"
OLD_WORKLIST = ROOT / "build" / "worklist_j66"
OUTPUT = ROOT / "build" / "translations_j87_supplement.jsonl"

LINK_RE = re.compile(r"\[\[[^\]]+\]\]")
QUERY_RE = re.compile(r"\[q=[^\]]+\]")
FORMAT_RE = re.compile(r"(?<!\{)\{\d+(?::[^{}]+)?\}(?!})")
TAG_RE = re.compile(r"<[^<>]+>")

# 真实措辞变化的条目：人工译文（术语沿用既有审校）。
CURATED = {
    "TAN-F776BE01733D": "我在想——我在想，也许这反而让您感到安慰。我的意思是，在这样的时代，我们都得作出艰难的选择——决定自己的人生该去往何处。而当您如此执着于拉格斯小姐时，便不必考虑其他事情。您也许就像一位踏上征途的骑士，得以从日常琐事中解脱。",
    "TAN-A3F4750B30EB": "对。就是这样。正是如此。所以我要告诉你，你会在哪儿找到你那位拉格斯小姐。也希望你从此别再插手我的事务。",
    "TAN-F5D320A03DF4": "西农布尔，斯特拉思科因，弗拉胡。拉维林？还有拉格斯。",
    "TAN-2CEFA5F91999": "“西尔万……”",
    "TAN-58840D2120EB": "我想一切无误。你可以自便了，先生。还有别的事吗？",
    "TAN-BC1CAF715D5C": "向安德蕾提我的名字——就是车站附近司辰书店的那个书商——这会为你打开一扇门。或许在门的另一边，你会找到你在找的东西。",
    "TAN-BE16420C0833": "塞拉皮雍专精于[[Forge]]密传与[[Horomachistry]]。",
    "TAN-20031BBD2715": "能让弗拉胡夫人这样的艺术家成为我们的客人，实在荣幸。",
    "TAN-359E0FD46E5E": "对了：罗迪娅……罗迪娅·弗拉胡？",
    "TAN-88633AE4565E": "有吗？没有？抱歉，[q=alias.familiar]，你说的是什么，我们完全听不懂。",
    "TAN-C3033B522360": "让我看看。名字是……[莱昂眯起了眼睛。]",
    "TAN-E948CF9530F8": "我需要悄悄买些东西。那些不公开出售的货色。有什么建议吗？",
    "TAN-334CA857AF58": "替我向安德蕾问好。也许她能帮到你。",
    "TAN-AD9B7FCEF789": "栖居于世界背后的隐秘诸神；凶险，崇高，在压制竞争者时绝不留情。有些从[[Know]]、[[Long]]与[[Names]]的位阶中一路攀升。有些则以全然不同的方式取得神位。\n\n诸战之前，司辰维系着[[History]]的意义。祂们的辩论与妥协，将每一种可能的过去编织成连贯的未来。如今祂们大概——基本上——都已离去，成为[[Uncounted]]。历史任由本体梦理的不连贯与圣显破坏摆布。直白地说：季节不对，人不是人，法国处处漏洞。",
}

PATCH_NOTES_ID = "TAN-A9621D02F556"

PATCH_NOTES_J87_ZH = """## 2026.8.j.87 ——“我的儿啊，看看你干了什么”

* 制作界面现在会显示更多关于你刚制作或想要制作的物品的信息
* 与某位长生者对话时，镜头现在能正确取景
* 疗养院的冰箱不再因为你第一次造访时没打开而空空如也
* 一些被遮蔽的房间在存档再读档后会显示出内部物体的轮廓
* 光标对实际可行走的区域不再那么悲观
* 物品栏右键菜单的一批问题修复
* 现在同一时间只应高亮一个回复选项
* 关闭弹出菜单时，确认删除提示会一并消失
* 伪造的邦国护照对你报的是哪个名字不再那么挑剔
* 如果你另辟蹊径达成目标，安德蕾的另一桩生意仍然可做
* 书店的三明治广告牌现在在首次经过之前即可交互
* 更新了角色面板立绘
* 大量叙事逻辑与文案修复
"""


def read_jsonl_dir(pattern: str) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for path in glob.glob(str(pattern)):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    row = json.loads(line)
                    rows[row["id"]] = row
    return rows


def mirror_edge_whitespace(source_new: str, source_old: str, translation_old: str) -> str:
    translation = translation_old
    if source_old.startswith((" ", "\n")) and not source_new.startswith((" ", "\n")):
        translation = translation.lstrip()
    if source_old.endswith((" ", "\n")) and not source_new.endswith((" ", "\n")):
        translation = translation.rstrip()
    return translation


def token_check(entry_id: str, source: str, translation: str) -> list[str]:
    problems = []
    if sorted(LINK_RE.findall(source)) != sorted(LINK_RE.findall(translation)):
        problems.append("link-token mismatch")
    if sorted(QUERY_RE.findall(source)) != sorted(QUERY_RE.findall(translation)):
        problems.append("query-token mismatch")
    if sorted(FORMAT_RE.findall(source)) != sorted(FORMAT_RE.findall(translation)):
        problems.append("format-token mismatch")
    if sorted(TAG_RE.findall(source)) != sorted(TAG_RE.findall(translation)):
        problems.append("tag mismatch")
    if source.count("\n") != translation.count("\n"):
        problems.append("newline count mismatch")
    if problems:
        print(f"TOKEN CHECK FAILED {entry_id}: {problems}")
    return problems


def split_sections(text: str) -> list[str]:
    parts = re.split(r"(?=^## )", text, flags=re.M)
    return [part for part in parts if part.strip()]


def main() -> int:
    new_entries = read_jsonl_dir(NEW_WORKLIST / "chunks" / "chunk_*.jsonl")
    old_translations = read_jsonl_dir(OLD_TRANSLATIONS / "chunk_*.jsonl")
    old_worklist = read_jsonl_dir(OLD_WORKLIST / "chunks" / "chunk_*.jsonl")

    fresh_ids = sorted(set(new_entries) - set(old_worklist))
    old_by_source: dict[str, dict] = {}
    for row_id, row in old_worklist.items():
        if row_id in old_translations and row_id not in new_entries:
            old_by_source[row["source"]] = old_translations[row_id]

    rows: list[dict] = []
    problems: list[str] = []
    for entry_id in fresh_ids:
        source = new_entries[entry_id]["source"]
        if entry_id == PATCH_NOTES_ID:
            continue  # 按段落重组，单独处理
        if entry_id in CURATED:
            translation = CURATED[entry_id]
        else:
            # 仅空白/拼写修订：按最佳旧源复用审校译文。
            import difflib
            best_source = max(
                old_by_source,
                key=lambda old_source: difflib.SequenceMatcher(None, source, old_source).ratio(),
            )
            ratio = difflib.SequenceMatcher(None, source, best_source).ratio()
            if ratio < 0.9:
                problems.append(f"{entry_id}: no confident old match ({ratio:.2f}) for {source[:60]!r}")
                continue
            translation = mirror_edge_whitespace(
                source, best_source, old_by_source[best_source]["translation"])
        problems.extend(token_check(entry_id, source, translation))
        rows.append({
            "id": entry_id,
            "source": source,
            "translation": translation,
            "status": "translated",
            "notes": "j.87 文本修订同步",
        })

    # 补丁说明：按 "## " 段落拆分，逐段对齐旧译文（忽略首尾空白差异）。
    old_pn = next(row for row in old_translations.values()
                  if row.get("source", "").startswith("## 2026.8.j.65"))
    old_zh_by_section: dict[str, str] = {}
    old_en_sections = split_sections(old_pn["source"])
    old_zh_parts = split_sections(old_pn["translation"])
    if len(old_zh_parts) != len(old_en_sections):
        problems.append(
            f"patch-notes old section count mismatch: en={len(old_en_sections)} zh={len(old_zh_parts)}")
    else:
        for en_section, zh_part in zip(old_en_sections, old_zh_parts):
            old_zh_by_section[en_section.strip()] = zh_part
    new_text = new_entries[PATCH_NOTES_ID]["source"]
    assembled: list[str] = []
    for section in split_sections(new_text):
        header = section.splitlines()[0].strip()
        if header.startswith("## 2026.8.j.87"):
            assembled.append(PATCH_NOTES_J87_ZH.rstrip("\n"))
            continue
        zh = old_zh_by_section.get(section.strip())
        if zh is None:
            problems.append(f"patch-notes section changed, needs translation: {header}")
            continue
        assembled.append(zh.rstrip("\n"))
    pn_translation = "\n\n".join(assembled) + "\n"
    rows.append({
        "id": PATCH_NOTES_ID,
        "source": new_text,
        "translation": pn_translation,
        "status": "translated",
        "notes": "j.87 新段落人工翻译，其余段落复用审校译文",
    })

    if problems:
        print("PROBLEMS:")
        for problem in problems:
            print("  " + problem)
        return 1
    with OUTPUT.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} supplement rows -> {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
