#!/usr/bin/env python3
"""Regression contracts for reported F9 composite-text corruption."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "src/TravellingCN/LanguageSwap.cs").read_text(encoding="utf-8-sig")
PLUGIN = (ROOT / "src/TravellingCN/Plugin.cs").read_text(encoding="utf-8-sig")
SWAP = json.loads((ROOT / "build/baked_assets/lang_swap.json").read_text(encoding="utf-8-sig"))


def swap_counted(mapping: dict[str, str], value: str) -> str | None:
    parts = re.split(r"([,，])", value)
    output: list[str] = []
    replacements = 0
    for index, part in enumerate(parts):
        if index % 2:
            output.append(part)
            continue
        match = re.fullmatch(r"(\s*\d+\s+)(.+?)(\s*)", part)
        if not match or match.group(2) not in mapping:
            return None
        output.extend((match.group(1), mapping[match.group(2)], match.group(3)))
        replacements += 1
    return "".join(output) if replacements else None


# ---------------------------------------------------------------------------
# 与 C# 侧 TryRewriteQueryTokens / BuildTemplate / AssembleTemplateSwap 对应的
# 最小复刻：只覆盖夹具用到的语义（非贪婪组、末尾占位符贪婪、开括号贪婪、
# 合成占位符、按目标模板拼装）。
# ---------------------------------------------------------------------------

QUERY_TOKEN_RE = re.compile(r"\[q=[^\[\]]+\]")


def rewrite_query_tokens(source: str, target: str) -> tuple[str, str] | None:
    if re.search(r"\[q=[^\[\]]+\]\[q=", source):
        return None
    source_tokens = set(QUERY_TOKEN_RE.findall(source))
    if any(token not in source_tokens for token in QUERY_TOKEN_RE.findall(target)):
        return None
    used = {int(n) for n in re.findall(r"\{(\d+)\}", source + target)}
    ids: dict[str, int] = {}
    next_index = 0

    def synthetic(token: str) -> str:
        nonlocal next_index
        if token not in ids:
            while next_index in used:
                next_index += 1
            ids[token] = next_index
            used.add(next_index)
            next_index += 1
        return "{" + str(ids[token]) + "}"

    return (
        QUERY_TOKEN_RE.sub(lambda m: synthetic(m.group(0)), source),
        QUERY_TOKEN_RE.sub(lambda m: synthetic(m.group(0)), target),
    )


def build_template(source: str, target: str) -> dict:
    placeholders = list(re.finditer(r"\{(\d+)\}", source))
    pattern = ["^"]
    substring: list[str] = []
    group_placeholders: list[int] = []
    first_literal = ""
    position = 0
    for i, match in enumerate(placeholders):
        literal = source[position:match.start()]
        if not first_literal and literal:
            first_literal = literal
        pattern.append(re.escape(literal))
        substring.append(re.escape(literal))
        following = (
            source[match.end():placeholders[i + 1].start()]
            if i + 1 < len(placeholders)
            else source[match.end():]
        )
        greedy_paren = bool(re.match(r"\s*[(\（\[【]", following))
        pattern.append("(.+)" if greedy_paren else "(.+?)")
        is_last_token = i == len(placeholders) - 1 and match.end() == len(source)
        substring.append("(.+)" if is_last_token else ("([^\n]+)" if greedy_paren else "(.+?)"))
        group_placeholders.append(int(match.group(1)))
        position = match.end()
    tail = source[position:]
    pattern.append(re.escape(tail))
    pattern.append("$")
    substring.append(re.escape(tail))
    segments: list[tuple[str, object]] = []
    position = 0
    for match in re.finditer(r"\{(\d+)\}", target):
        if match.start() > position:
            segments.append(("lit", target[position:match.start()]))
        segments.append(("ph", int(match.group(1))))
        position = match.end()
    if position < len(target):
        segments.append(("lit", target[position:]))
    return {
        "pattern": re.compile("".join(pattern)),
        "substring": re.compile("".join(substring)),
        "first_literal": first_literal,
        "starts_with_ph": bool(placeholders) and placeholders[0].start() == 0,
        "group_placeholders": group_placeholders,
        "segments": segments,
    }


def assemble_template(template: dict, match: re.Match, swap_group) -> str:
    swapped: dict[int, str] = {}
    for i, placeholder in enumerate(template["group_placeholders"]):
        swapped[placeholder] = swap_group(match.group(i + 1))
    output: list[str] = []
    for kind, value in template["segments"]:
        if kind == "lit":
            output.append(value)
        elif value in swapped:
            output.append(swapped[value])
    return "".join(output)


def main() -> int:
    errors: list[str] = []
    checks = 0

    def require(name: str, condition: bool) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(name)

    require("template records prefix-placeholder state", "StartsWithPlaceholder" in SOURCE)
    require(
        "Tier 2 fullmatch does not discard prefix-placeholder templates",
        "if (!template.StartsWithPlaceholder && template.FirstLiteral.Length > 0" in SOURCE,
    )
    require(
        "Tier 3.5 keeps prefix-placeholder templates only at line start",
        "template.StartsWithPlaceholder && match.Index != 0" in SOURCE,
    )
    require(
        "reordering/short-literal templates require independently mapped groups",
        "template.RequiresExactGroups" in SOURCE and "TemplateGroupsAllExact" in SOURCE,
    )
    require(
        "exact-group registry covers both reordering and 'Not' templates",
        '"{0} in a {1}"' in SOURCE
        and '"{1} 中的 {0}"' in SOURCE
        and '"Not {0}"' in SOURCE
        and '"非 {0}"' in SOURCE,
    )
    assemble = SOURCE[SOURCE.index("private static string AssembleTemplateSwap") :]
    counted_index = assemble.find("TrySwapCountedLabelList(map, coreCapture")
    recursive_index = assemble.find("TrySwapDisplayText(map, coreCapture")
    require(
        "counted one-character labels are handled before generic recursion",
        counted_index >= 0 and recursive_index > counted_index,
    )
    require(
        "speaker prefix allows spaced names with lazy match",
        "FindSpeakerSeparator" in SOURCE
        and "plainName.Length > 40" in SOURCE
        and "plainName.Contains('—')" in SOURCE,
    )
    require(
        "query token rewrite declared and wired into direction map build",
        "QueryTokenPattern" in SOURCE
        and "TryRewriteQueryTokens(pair.Key, pair.Value" in SOURCE,
    )
    require(
        "strip-inheritance probe forces English mode idempotently",
        "DebugSetEnglishMode(bool english)" in SOURCE
        and "LanguageSwap.DebugSetEnglishMode(true);" in PLUGIN
        and "LanguageSwap.DebugSetEnglishMode(false);" in PLUGIN,
    )
    require(
        "regression summaries are per-suite deltas, not a shared cascade",
        PLUGIN.count("var failureBaseline = _regressionFailures;")
        == PLUGIN.count("DumpRegressionSummary(") - 1  # 减去定义处
        and PLUGIN.count("DumpRegressionSummary(") >= 5
        and ', failureBaseline)' in PLUGIN,
    )
    require(
        "scenario probe exists and is config-gated",
        "AutoProbeScenarioRoutine" in PLUGIN and "DumpScenarioResidue" in PLUGIN,
    )
    require(
        "buffer round-trip probe carries the user-reported fixtures",
        "AutoProbeBufferFixturesRoutine" in PLUGIN
        and "BufferFixtures" in PLUGIN
        and "严格说来，也不算" in PLUGIN
        and "请原谅，霍布森先生" in PLUGIN,
    )

    template_source = "{0} in a {1}"
    require("dangerous prefix-placeholder fixture exists in map", template_source in SWAP["en2zh"])
    flagpole = (
        "2. Frost in winter; sounds loudest at night; "
        "in a riven world, the Horned-Axe prominent."
    )
    old_match = re.search(r"(.+?) in a (.+)", flagpole)
    old_corruption = (
        f"{old_match.group(2)} 中的 {old_match.group(1)}" if old_match is not None else ""
    ).replace("Horned-Axe", "双角斧")
    require(
        "fixture reproduces the screenshot's reordered mixed-language option",
        old_corruption
        == "riven world, the 双角斧 prominent. 中的 2. Frost in winter; sounds loudest at night;",
    )
    reorder = build_template("{0} in a {1}", "{1} 中的 {0}")
    reorder_match = reorder["substring"].search(flagpole)
    require(
        "reordering template substring-matches ordinary prose (precondition)",
        reorder_match is not None and reorder_match.start() == 0,
    )
    require(
        "...but every capture fails the exact-key gate, so the match is dropped",
        reorder_match is not None
        and all(
            reorder_match.group(i) not in SWAP["en2zh"]
            for i in (1, 2)
        ),
    )

    require(
        "CN counted aspects restore to English",
        swap_counted(SWAP["zh2en"], "1 启, 1 灯") == "1 Knock, 1 Lantern",
    )
    require(
        "English counted aspects restore to Chinese",
        swap_counted(SWAP["en2zh"], "1 Knock, 1 Lantern") == "1 启, 1 灯",
    )
    require(
        "single counted aspect is also supported",
        swap_counted(SWAP["zh2en"], "1 灯") == "1 Lantern",
    )
    require(
        "flagpole option retains an exact bidirectional pair",
        SWAP["en2zh"].get(
            "Frost in winter; sounds loudest at night; in a riven world, "
            "the Horned-Axe prominent."
        )
        == "冬日结霜；夜里声响最盛；世界裂分之时，双角斧彰显。",
    )

    # --- v2.6.4：查询令牌模板化 -------------------------------------------------
    en_choco = (
        "Forgive me, [q=alias.formal.fr], but there is something about you that "
        "recalls... the abandoned chocolate-box. The colours are bright, the "
        "corners square, the lid only a little askew. But one senses an absence."
    )
    zh_choco = (
        "请原谅，[q=alias.formal.fr]，但您身上有种东西，叫人想起……一只被弃置的"
        "巧克力盒。颜色鲜艳，四角方正，盒盖不过略略歪斜。可人总能感觉到，"
        "里面少了什么。"
    )
    require("chocolate-box pair is in the map", SWAP["en2zh"].get(en_choco) == zh_choco)
    # 中文显示态里 [q=alias.formal.fr] 已解析为烘焙后的中文别名“霍布森先生”；
    # zh2en 对该别名的确定性选择是 "Herr Hobson"（e2z 再映回同一中文，往返稳定）。
    display_zh = zh_choco.replace("[q=alias.formal.fr]", "霍布森先生")
    display_en = en_choco.replace("[q=alias.formal.fr]", "Herr Hobson")
    # zh2en 方向：模板源=中文键，匹配中文显示态，拼装出英文。
    rewritten = rewrite_query_tokens(zh_choco, en_choco)
    require("query tokens rewrite to a template", rewritten is not None)
    if rewritten is not None:
        template = build_template(*rewritten)
        match = template["pattern"].match(display_zh)
        require("resolved zh display fullmatches the query template", match is not None)
        if match is not None:
            swapped = assemble_template(template, match, lambda g: SWAP["zh2en"].get(g, g))
            require(
                "zh->en whole-paragraph swap resolves the alias",
                swapped == display_en,
            )
    # en2zh 方向：模板源=英文键，匹配英文显示态，拼装出中文。
    rewritten_back = rewrite_query_tokens(en_choco, zh_choco)
    require("reverse query rewrite exists", rewritten_back is not None)
    if rewritten_back is not None:
        back_template = build_template(*rewritten_back)
        back_match = back_template["pattern"].match(display_en)
        require("resolved en display fullmatches the reverse template", back_match is not None)
        if back_match is not None:
            swapped_back = assemble_template(
                back_template, back_match, lambda g: SWAP["en2zh"].get(g, g)
            )
            require(
                "en->zh whole-paragraph swap resolves the alias back",
                swapped_back == display_zh,
            )

    # --- v2.6.4："Not {0}" 短字面模板不得吞掉长段 -------------------------------
    kept = (
        "Not 'kept', really. The Janviers are dispersed across the Continent, now. "
        "We sold our premises in the Republic, just last month. A number of "
        "long-abandoned items were sent on to me. Fortuitous."
    )
    not_template = build_template("Not {0}", "非 {0}")
    not_match = not_template["pattern"].match(kept)
    require(
        "'Not {0}' still fullmatches any Not-paragraph (precondition)",
        not_match is not None,
    )
    require(
        "...but its capture is not an exact key, so the exact-group gate drops it",
        not_match is not None and not_match.group(1) not in SWAP["en2zh"],
    )
    speaker_line = "The elder Janvier — " + kept
    speaker_match = re.match(r"^([^—\n<>]{1,40}?)( — )", speaker_line)
    require(
        "spaced English speaker name splits at ' — '",
        speaker_match is not None and speaker_match.group(1) == "The elder Janvier",
    )
    require(
        "speaker name is a standalone map key",
        speaker_match is not None and speaker_match.group(1) in SWAP["en2zh"],
    )
    require(
        "the paragraph after the prefix is an exact key",
        speaker_match is not None
        and speaker_line[speaker_match.end():] in SWAP["en2zh"],
    )

    # --- v2.6.4：赞成系统行（前缀占位符 + 行首锚） ------------------------------
    approval = build_template(
        "{0} 表示赞同（+{1}），现为 {2}", "{0} approves (+{1}), and is now {2}"
    )
    approval_line = "✧ 老让维耶 表示赞同（+7），现为 感激"
    approval_match = approval["substring"].search(approval_line)
    require(
        "approval template substring-matches despite the ✧ prefix",
        approval_match is not None,
    )
    require(
        "...and the match is anchored at line start (pure-text index 0)",
        approval_match is not None and approval_match.start() == 0,
    )
    if approval_match is not None:
        require(
            "approval captures name/amount/state",
            approval_match.group(1) == "✧ 老让维耶"
            and approval_match.group(2) == "7"
            and approval_match.group(3) == "感激",
        )
        require(
            "state word is a bidirectional exact key",
            SWAP["zh2en"].get("感激") == "Appreciative",
        )
        swapped = assemble_template(
            approval,
            approval_match,
            lambda g: SWAP["zh2en"].get(g, g.replace("老让维耶", "The elder Janvier")),
        )
        require(
            "approval line assembles fully to English",
            swapped == "✧ The elder Janvier approves (+7), and is now Appreciative",
        )

    # --- v2.6.4：运行时拼接提示行 "Used X (Y)" 已入图 ---------------------------
    require(
        "runtime-composed 'Used {0} ({1})' template is in en2zh",
        SWAP["en2zh"].get("Used {0} ({1})") == "动用了 {0}（{1}）",
    )
    require(
        "...and zh2en",
        SWAP["zh2en"].get("动用了 {0}（{1}）") == "Used {0} ({1})",
    )

    # --- v2.6.4：译文数据修复在位 ------------------------------------------------
    translations = {
        path.name: path.read_text(encoding="utf-8-sig")
        for path in (ROOT / "translations_k97").glob("chunk_*.jsonl")
    }
    chunk7 = translations.get("chunk_007.jsonl", "")
    chunk9 = translations.get("chunk_009.jsonl", "")
    require(
        "'... but lost.' no longer mistranslated as a lost game",
        '"source":"... but lost.","translation":"……却已失落。"' in chunk9,
    )
    require(
        "the inert animal is the café cat, not a beast",
        '"translation":"这猫基本不会动，先生。别指望它。"' in chunk7,
    )
    require(
        "no '畜生' wording remains anywhere in the active set",
        all("畜生" not in body for body in translations.values()),
    )

    print(json.dumps({"checks": checks, "errors": errors}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
