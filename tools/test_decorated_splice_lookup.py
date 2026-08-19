#!/usr/bin/env python3
"""Offline contract test for the decorated-splice / [q=...] pattern lookup.

The plugin matches display-decorated runtime strings (colour wrappers, option
numbering, ``[97%]`` check chances, sprites, substituted ``[q=...]`` tokens)
against the fingerprint catalog and the fingerprinted variable patterns.  This
test mirrors the C# algorithm exactly (UTF-16 segment lengths, first/last char
prefilter, SHA-256 segment fingerprints, whole-string anchoring, leading
decoration trims) and replays the exact byte forms captured from a real game
session by the diagnostic build.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MERGED = ROOT / "build" / "merged_k6"

TAG_RE = re.compile(r"<[^>]*>")
INVISIBLE = "‎‏​﻿"
LEADING_NUMBERING_RE = re.compile(r"^\s*\d{1,2}\.\s*")
LEADING_CHANCE_RE = re.compile(r"^\s*\[\d{1,3}%\]\s*")
LEADING_BRACKET_RE = re.compile(r"^\s*\[[^\[\]<>]{1,48}\]\s*[-–—]?\s*")
LEADING_WIKI_LABEL_RE = re.compile(r"^\s*\[?\[\[[^\]]+\]\]\]?\s*[-–—]?\s*")
RENDERED_LINK_RE = re.compile(
    r"<link\s*=\s*(?P<quote>[\"'])(?P<id>.*?)(?P=quote)[^>]*>.*?</link>", re.I | re.S)
RENDERED_LINK_VISIBLE_TEXT_RE = re.compile(r"(?<=>)[^<>]+(?=<)", re.S)
WIKI_LINK_RE = re.compile(r"\[\[(?P<id>[^\[\]]+)\]\]")
BUFFER_SPEAKER_PREFIX_RE = re.compile(
    r"^(?P<head><font=[^>]*><b><i><sprite=\d+>[^<]*</i></b></font>\s*—\s*)(?P<rest>.*)$", re.S)
BUFFER_SPEAKER_NAME_RE = re.compile(r"<sprite=\d+>(?P<name>[^<]*)</i>")
BUFFER_OUTER_COLOR_RE = re.compile(r"^(?P<open><color=[^>]*>)(?P<content>.*)(?P<close></color>)$", re.S)

# Byte-exact strings captured by travellingcn-diag.jsonl (2026-08-16 session).
LEON_SUBTITLE = (
    "<color=#231a17ff>This document would be satisfactory... except that you "
    "told me, earlier, that your name was Isnard. This is an entirely "
    "different name.</color>"
)
OPTION_ONE = (
    "<color=#221A17>1.</color><indent=28> <sprite=\"SmolSkillImages\" "
    "name=\"eloquence\"><space=-1.5em><sprite=\"SmolSkillImages\" "
    "name=\"outline\" tint=1> [97%] Isnard? I can't honestly call to mind "
    "anyone of that name  - you mean me? No no no - I'm afraid you must have "
    "me confused with someone else. I know how busy are the Milice."
)
OPTION_TWO = (
    "<color=#221A17>2.</color><indent=28> <sprite=\"SmolSkillImages\" "
    "name=\"dignity\"><space=-1.5em><sprite=\"SmolSkillImages\" "
    "name=\"outline\" tint=1> [79%] Isnard? Excuse me - do I look like a "
    "Isnard?"
)
INLINEBAR_SEPARATOR = (
    "<color=#231a17ff><line-height=18px><link=\"inlinebar:0\">"
    "<color=#00FFFF><b><size=0>.</size></b></color></link>‎  </line-height></color>"
)
RECIPE_INGREDIENT = (
    "Add an ingredient with Aspects Influence, Winter - the recipe will not "
    "consume it"
)
RECIPE_SKILL = (
    "You are skilled enough for this recipe… but only with Illumination in a "
    "<sprite=\"VenueImages\" name=\"holyplace\"> Holy Place or "
    "<sprite=\"VenueImages\" name=\"quietplace\"> Quiet Place, or Hushery in a "
    "<sprite=\"VenueImages\" name=\"quietplace\"> Quiet Place or "
    "<sprite=\"VenueImages\" name=\"shadowedplace\"> Shadowed Place"
)
# 实机采集：游戏在制作界面混用大写 OR 连接子句（v1.2.13 曾漏切）。
RECIPE_SKILL_UPPER_OR = (
    "You are skilled enough for this recipe… but only with Hushery in a "
    "<sprite=\"VenueImages\" name=\"holyplace\"> Holy Place or "
    "<sprite=\"VenueImages\" name=\"threshold\"> Threshold, OR Horomachistry in a "
    "<sprite=\"VenueImages\" name=\"quietplace\"> Quiet Place or "
    "<sprite=\"VenueImages\" name=\"shadowedplace\"> Shadowed Place"
)

# 实机采集的累计对话缓冲行（travellingcn-diag.jsonl，v1.2.14 会话）。
BUFFER_LINE_DIALOGUE = (
    "<font=\"georgia\"><b><i><sprite=0>Leon</i></b></font> — "
    "<color=#231a17cc>A young man blinks resentfully through the curtain of "
    "rain running off his cap.</color>"
)
BUFFER_LINE_DISAPPROVE = (
    "<color=#231a17cc><i><sprite=\"inline\" name=\"star\"> Leon disapproves "
    "(-1), and is now Wary</i></color>"
)
BUFFER_LINE_TRACES = (
    "<color=#231a17cc><i><sprite=\"inline\" name=\"star\"> Traces 1: enough to "
    "make me a subject of Rumour.</i></color>"
)
BUFFER_LINE_ECHO = (
    "<font=\"georgia\"><b><i><sprite=1>Me</i></b></font> — "
    "<color=#231a17cc><link=\"![DIALOGUE_ENTRY]155:114\"><color=#BA4802><b>"
    "<sprite=\"SmolSkillImages\" name=\"eloquence\"><space=-1.5em>"
    "<sprite=\"SmolSkillImages\" name=\"outline\" color=#D24B00FF> "
    "[<u>成功</u>]</b></color></link> - Isnard? I can't honestly call to mind "
    "anyone of that name  - you mean me? No no no - I'm afraid you must have "
    "me confused with someone else. I know how busy are the Milice.</color>"
)
DYNAMIC_CLAUSE_SEPARATORS = ((", or ", "；或 "), (", OR ", "；或 "))
DYNAMIC_LIST_JOINS = ((" or ", " 或 "), (" OR ", " 或 "), (", ", "、"))

# v1.2.16 实机采集形态：渲染时被修剪尾空格的目录行（"The Wars …" 源文带尾空格）。
BUFFER_LINE_TRAILING_SPACE = (
    "<color=#231a17cc>The Wars and their plagues took the glitter off those "
    "golden evenings, left the air dense and villainous.</color>"
)
# v1.2.16 实机采集形态：选项提示标签链接 + 正文脚注链接混合的整行。
NINA_OPTION = (
    "<color=#221A17>2.</color><indent=28> "
    "[<link=\"Nina in Antibes?\"><color=#BA4802><b>Nina in Antibes?</b></color></link>] "
    "I'll need something in return. I'm looking for someone: a woman named "
    "<link=\"Nina Lagasse\"><color=#BA4802><b>Nina Lagasse</b></color></link>."
)


def source_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def strip_decorations(value: str) -> str:
    stripped = TAG_RE.sub("", value)
    return "".join(char for char in stripped if char not in INVISIBLE)


class Runtime:
    def __init__(self) -> None:
        self.catalog = json.loads((MERGED / "catalog.zh-CN.json").read_text(encoding="utf-8"))
        pattern_file = json.loads((MERGED / "patterns.zh-CN.json").read_text(encoding="utf-8"))
        self.patterns = pattern_file["patterns"]
        self.link_targets = json.loads(
            (MERGED / "link_targets.zh-CN.json").read_text(encoding="utf-8"))

    def canonicalize_links(self, source: str) -> str:
        # CanonicalizeRenderedLinks：仅当链接 id 在脚注/补充映射里才还原为 [[id]]。
        def replace(match: re.Match) -> str:
            link_id = match.group("id")
            if link_id and source_hash(link_id) in self.link_targets:
                return "[[" + link_id + "]]"
            return match.group(0)
        if "<link" not in source.lower():
            return source
        return RENDERED_LINK_RE.sub(replace, source)

    def localize_wiki_labels(self, value: str) -> str:
        def replace(match: re.Match) -> str:
            label = match.group("id")
            translated = self.catalog.get(source_hash(label))
            return "[[" + (translated or label) + "]]"
        return WIKI_LINK_RE.sub(replace, value)

    def render_wiki_links(self, value: str, canonical_source: str) -> str:
        source_ids = WIKI_LINK_RE.findall(canonical_source)
        target_labels = WIKI_LINK_RE.findall(value)
        if len(source_ids) != len(target_labels):
            return value
        index = iter(range(len(source_ids)))
        return WIKI_LINK_RE.sub(
            lambda match: '<link="' + source_ids[next(index)] + '">' +
                match.group("id") + "</link>",
            value)

    def restore_authored_styles(self, result: str, authored: str, wiki_target: str) -> str:
        rendered = list(RENDERED_LINK_RE.finditer(result))
        authored_links = list(RENDERED_LINK_RE.finditer(authored))
        labels = WIKI_LINK_RE.findall(wiki_target)
        if not rendered or len(rendered) != len(authored_links) or len(rendered) != len(labels):
            return result
        output: list[str] = []
        position = 0
        for match, authored_match, label in zip(rendered, authored_links, labels):
            output.append(result[position:match.start()])
            rebuilt = RENDERED_LINK_VISIBLE_TEXT_RE.sub(label, authored_match.group(0), count=1)
            output.append(rebuilt)
            position = match.end()
        output.append(result[position:])
        return "".join(output)

    def find_segment(self, value: str, segment: dict, from_index: int, is_last: bool) -> int:
        length = segment["len"]
        if length == 0:
            return len(value) if is_last else from_index
        if length > len(value) - from_index or not segment["first"]:
            return -1
        first, last = segment["first"], segment["last"]
        index = from_index
        while index <= len(value) - length:
            window = value[index:index + length]
            if window[0] == first and window[-1] == last and source_hash(window) == segment["sha"]:
                return index
            index += 1
        return -1

    def split_translate(self, value: str, separator: str, joiner: str, depth: int) -> str | None:
        if separator not in value:
            return None
        parts = [part.strip() for part in value.split(separator)]
        if len(parts) < 2 or any(not part for part in parts):
            return None
        translated = [self.translate_dynamic_value(part, depth + 1) for part in parts]
        if translated == parts:
            return None
        return joiner.join(translated)

    def translate_dynamic_value(self, value: str, depth: int) -> str:
        if not value:
            return value
        exact = self.catalog.get(source_hash(value))
        if exact is not None:
            return exact
        if depth >= 8:
            return value
        trimmed = value.strip()
        # 牛津逗号切子句边界最优先；" {0} in a {1}" 等模式先于普通
        # " or " 拆分，否则连接词会劈开模式宾语。
        for separator, joiner in DYNAMIC_CLAUSE_SEPARATORS:
            claused = self.split_translate(trimmed, separator, joiner, depth)
            if claused is not None:
                return claused
        patterned = self.match_patterns(trimmed, depth + 1)
        if patterned is not None:
            return patterned
        for separator, joiner in DYNAMIC_LIST_JOINS:
            listed = self.split_translate(trimmed, separator, joiner, depth)
            if listed is not None:
                return listed
        return value

    def match_pattern(self, pattern: dict, visible: str, depth: int = 0) -> str | None:
        captures: list[str] = []
        position = 0
        for index, segment in enumerate(pattern["segments"]):
            start = self.find_segment(
                visible, segment, position, index == len(pattern["segments"]) - 1)
            if start < 0:
                return None
            if index == 0 and segment["len"] > 0 and start != 0:
                return None
            if index > 0:
                captures.append(visible[position:start])
            position = start + segment["len"]
        if position != len(visible):
            return None
        # 捕获值是别名、数字等动态内容；含装饰/控制括号说明首段之前的编号、
        # 概率前缀等装饰被误吞进变量槽，该匹配必须拒绝。
        if any(any(char in capture for char in "<>[]") for capture in captures):
            return None
        result = pattern["translation"]
        for token, capture in zip(pattern["tokens"], captures):
            result = result.replace(token, self.translate_dynamic_value(capture, depth + 1))
        return result

    def match_patterns(self, visible: str, depth: int = 0, min_literal: int = 0) -> str | None:
        if not visible or len(visible) > 2048:
            return None
        for pattern in self.patterns:
            # 锚点过弱的模式只允许在动态参数递归路径使用；整句拼接要求
            # 足够的字面锚点，否则会把未译整句变成"英文+。"僵尸串。
            literal = sum(seg["len"] for seg in pattern["segments"])
            if literal < min_literal or literal > len(visible):
                continue
            matched = self.match_pattern(pattern, visible, depth)
            if matched is not None:
                return matched
        return None

    def try_splice_candidate(
        self, source: str, candidate: str, visible: str, allow_wiki_links: bool
    ) -> str | None:
        # 过短或无字母的核心容易撞中目录里的标点/符号条目（如 "."→"。"），
        # 把隐形的版式分隔符也"翻译"掉；拼接只服务句级文本。
        if len(candidate) < 2 or not re.search(r"[A-Za-z]", candidate):
            return None
        translation = self.catalog.get(source_hash(candidate))
        if translation is None:
            translation = self.match_patterns(candidate, 0, 8)
        if not translation or ("[[" in translation and not allow_wiki_links):
            return None
        at = source.find(candidate)
        if at >= 0:
            return source[:at] + translation + source[at + len(candidate):]
        if candidate == visible:
            return translation
        return None

    def translate_label_prefix(self, target: str, visible: str, candidate: str) -> str:
        # TranslateSplicedLabelPrefix：正文命中后把被修剪的提示标签单独译出，
        # 替换其在拼接结果里的最后一次出现（链接 id 属性先于可见标签）。
        at = visible.find(candidate)
        if at <= 0:
            return target
        label_core = visible[:at].strip().strip("[] -–—")
        if len(label_core) < 2 or not re.search(r"[A-Za-z]", label_core):
            return target
        label_translation = self.catalog.get(source_hash(label_core))
        if not label_translation:
            return target
        label_at = target.rfind(label_core)
        if label_at < 0:
            return target
        return target[:label_at] + label_translation + target[label_at + len(label_core):]

    def try_splice(self, source: str) -> str | None:
        working = self.canonicalize_links(source)
        canonicalized = working != source
        visible = strip_decorations(working).strip()
        if not visible:
            return None
        candidate = visible
        target: str | None = None
        for _ in range(4):
            if not candidate:
                return None
            target = self.try_splice_candidate(working, candidate, visible, canonicalized)
            if target is not None:
                break
            # 修剪顺序：编号 → [97%] → [[wiki]] 提示标签 → 普通 [标签]。
            # 方括号规则排除了 '['，不会从 [[...]] 中间截断。
            trimmed = LEADING_NUMBERING_RE.sub("", candidate)
            trimmed = LEADING_CHANCE_RE.sub("", trimmed)
            trimmed = LEADING_WIKI_LABEL_RE.sub("", trimmed)
            trimmed = LEADING_BRACKET_RE.sub("", trimmed).strip()
            if trimmed == candidate:
                return None
            candidate = trimmed
        if target is None:
            return None
        if canonicalized:
            wiki_target = self.localize_wiki_labels(target)
            rendered = self.render_wiki_links(wiki_target, working)
            if "[[" in rendered:
                target = WIKI_LINK_RE.sub(lambda match: match.group("id"), wiki_target)
            else:
                target = self.restore_authored_styles(rendered, source, wiki_target)
        elif "[[" in target:
            # 非规范化路径不得把 authored [[...]] 残片带上屏。
            return None
        elif candidate != visible:
            target = self.translate_label_prefix(target, visible, candidate)
        return target

    def translate_buffer_line(self, line: str) -> str:
        """Mirror of LocalizeBufferLineForward (catalog/pattern subset)."""
        if len(line) < 2 or not re.search(r"[A-Za-z]", line):
            return line
        whole = self.catalog.get(source_hash(line))
        if whole is not None:
            return whole
        whole = self.try_splice(line)
        if whole is not None:
            return whole
        head = ""
        rest = line
        speaker = BUFFER_SPEAKER_PREFIX_RE.match(line)
        if speaker:
            head = speaker.group("head")
            rest = speaker.group("rest")
            name_match = BUFFER_SPEAKER_NAME_RE.search(head)
            if name_match:
                name = name_match.group("name")
                translated_name = self.catalog.get(source_hash(name))
                if translated_name is not None:
                    head = head.replace(name, translated_name)
        color = BUFFER_OUTER_COLOR_RE.match(rest)
        if color:
            content = color.group("content")
            translated = self.catalog.get(source_hash(content))
            if translated is None:
                translated = self.try_splice(content)
            if translated is not None:
                rest = color.group("open") + translated + color.group("close")
        return head + rest


def main() -> int:
    runtime = Runtime()
    errors: list[str] = []

    def require(name: str, condition: bool) -> None:
        if not condition:
            errors.append(name)

    leon = runtime.try_splice(LEON_SUBTITLE)
    require("莱昂台词经颜色包裹后拼接命中", leon is not None)
    if leon is not None:
        require("莱昂台词保留颜色包裹", leon.startswith("<color=#231a17ff>") and leon.endswith("</color>"))
        require("莱昂台词译文完整", "这份证件原本没有问题" in leon and "完全不同的名字" in leon)
        require("莱昂台词别名值中文化", "你姓 伊斯纳尔。" in leon)

    option_one = runtime.try_splice(OPTION_ONE)
    require("检定选项一拼接命中", option_one is not None)
    if option_one is not None:
        require("选项一保留编号颜色", "<color=#221A17>1.</color>" in option_one)
        require("选项一保留精灵图标", "<sprite=\"SmolSkillImages\" name=\"eloquence\">" in option_one)
        require("选项一保留检定概率", "[97%]" in option_one)
        require("选项一译文完整", "我实在想不起有谁" in option_one and "民兵团" in option_one)
        require("选项一别名值中文化", "伊斯纳尔？" in option_one)

    option_two = runtime.try_splice(OPTION_TWO)
    require("检定选项二拼接命中", option_two is not None)
    if option_two is not None:
        require("选项二保留检定概率", "[79%]" in option_two)
        require("选项二双变量替换", option_two.count("伊斯纳尔") == 2)

    require("隐形分隔符不误译", runtime.try_splice(INLINEBAR_SEPARATOR) is None)
    require("目录外字符串不误译", runtime.try_splice("Silence") is None)

    ingredient = runtime.try_splice(RECIPE_INGREDIENT)
    require("配方材料提示拼接命中", ingredient is not None)
    if ingredient is not None:
        require("配方材料提示模板中文化", "添加一份具备性相" in ingredient and "配方不会将其消耗" in ingredient)
        require("配方材料提示参数列表本地化", "影响、冬" in ingredient)

    skill = runtime.try_splice(RECIPE_SKILL)
    require("配方技艺提示拼接命中", skill is not None)
    if skill is not None:
        require("配方技艺提示模板中文化", "你具备制作此配方所需的技艺" in skill)
        require("配方技艺提示子句一", "圣地 或 静谧之地 中的 照明术" in skill)
        require("配方技艺提示子句二", "静谧之地 或 暗影之地 中的 静默术" in skill)

    upper = runtime.try_splice(RECIPE_SKILL_UPPER_OR)
    require("大写 OR 子句拼接命中", upper is not None)
    if upper is not None:
        require("大写 OR 不残留", "OR" not in upper and " or " not in upper)
        require("大写 OR 子句一", "圣地 或 门槛 中的 静默术" in upper)
        require("大写 OR 子句二", "静谧之地 或 暗影之地 中的 司辰学" in upper)

    dialogue = runtime.translate_buffer_line(BUFFER_LINE_DIALOGUE)
    require("缓冲对话行保留外层结构", dialogue.startswith("<font=\"georgia\">") and "<color=#231a17cc>" in dialogue)
    require("缓冲对话行说话人中文化", "<sprite=0>莱昂" in dialogue)
    require("缓冲对话行全句中文化", "忿忿地眨着眼" in dialogue and "cap。" not in dialogue)

    disapprove = runtime.translate_buffer_line(BUFFER_LINE_DISAPPROVE)
    require(
        "缓冲通知行模式命中",
        "莱昂 表示不赞同（-1），现为 戒备" in (disapprove or ""))

    traces = runtime.translate_buffer_line(BUFFER_LINE_TRACES)
    require("缓冲痕迹条件行命中", "1 点痕迹：足以让我成为传闻的主角。" in (traces or ""))
    require("缓冲痕迹条件行无半翻译", "痕迹s" not in (traces or ""))

    echo = runtime.translate_buffer_line(BUFFER_LINE_ECHO)
    require("缓冲选项回显保留回溯链接", "![DIALOGUE_ENTRY]155:114" in (echo or ""))
    require("缓冲选项回显保留结果标签", "[<u>成功</u>]" in (echo or ""))
    require("缓冲选项回显正文中文化", "我实在想不起有谁" in (echo or ""))

    trailing = runtime.translate_buffer_line(BUFFER_LINE_TRAILING_SPACE)
    require(
        "修剪尾空格的渲染行命中修剪变体",
        "诸战及随之而来的瘟疫" in (trailing or ""))
    require("修剪变体保留颜色包裹", (trailing or "").endswith("</color>"))

    nina = runtime.try_splice(NINA_OPTION)
    require("提示标签选项拼接命中", nina is not None)
    if nina is not None:
        require("提示标签中文化", "宁娜在昂蒂布？" in nina)
        require("提示标签链接保留", 'link="Nina in Antibes?"' in nina)
        require("正文中文化", "我需要一点回报" in nina)
        require("正文脚注链接保留", 'link="Nina Lagasse"' in nina)
        require("正文脚注标签中文化", "宁娜·拉格斯" in nina)
        require("提示标签选项无残留英文主体", "I'll need something" not in nina)

    # 含 [[...]] 链接的译文禁止裸文本拼接，必须留在 authored 链接恢复路径。
    linked = None
    for line in (MERGED / "review_catalog.jsonl").open(encoding="utf-8"):
        entry = json.loads(line)
        if "[[" in entry.get("translation", "") and "<" not in entry["source"]:
            linked = entry
            break
    require("测试基线含脚注链接条目", linked is not None)
    if linked is not None:
        require(
            "链接译文不裸回填",
            runtime.try_splice(f"<color=#231a17ff>{linked['source']}</color>") is None,
        )

    print(json.dumps({"errors": errors, "error_count": len(errors)}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
