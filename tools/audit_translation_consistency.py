#!/usr/bin/env python3
"""Read-only final-pass audit for the Travelling at Night translation catalog.

The tool never edits the catalog, glossary, or translation chunks.  It can print
a concise human report, emit JSON on stdout, and optionally write a standalone
JSON report with ``--json-output``.
"""

from __future__ import annotations

import argparse
import collections
import csv
import difflib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


TAG_RE = re.compile(r"<[^<>]+>")
WIKILINK_RE = re.compile(r"\[\[[^\]]+\]\]")
QUERY_RE = re.compile(r"\[q=[^\]]+\]", re.IGNORECASE)
BRACE_RE = re.compile(r"\{[^{}]*\}")
URL_RE = re.compile(r"(?:https?|ftp)://[^\s<>\]\[()]+", re.IGNORECASE)
PRINTF_RE = re.compile(r"%(?:\d+\$)?[-+#0 ]*\d*(?:\.\d+)?[diouxXeEfFgGcrsa%]")
DOLLAR_VARIABLE_RE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*")
BACKTICK_RE = re.compile(r"`[^`\n]+`")
PATH_RE = re.compile(r"(?<!\w)(?:[A-Za-z]:[\\/]|\.\.?[\\/])[^\s<>\"']+")
IDENTIFIER_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    r"[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+|"
    r"[a-z]+:[A-Za-z][A-Za-z0-9]*|"
    r"[a-z]+[A-Z][A-Za-z0-9]*|"
    r"[A-Z][a-z0-9]+(?:[A-Z][A-Za-z0-9]*)+|"
    r"[A-Za-z][A-Za-z0-9]*Id"
    r")(?![A-Za-z0-9])"
)
ENGLISH_WORD_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]+(?:['’][A-Za-z]+)?)(?![A-Za-z])")
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")

PROTECTED_PATTERNS: tuple[re.Pattern[str], ...] = (
    TAG_RE,
    WIKILINK_RE,
    QUERY_RE,
    BRACE_RE,
    URL_RE,
    PRINTF_RE,
    DOLLAR_VARIABLE_RE,
    BACKTICK_RE,
    PATH_RE,
)

# Wiki-link contents are player-visible labels and often carry the decisive
# half of a setting entity (for example ``Church ... [[Sun]]``).  They must be
# unwrapped, not hidden, for terminology checks.  Other protected spans remain
# masked so markup and runtime tokens do not create false positives.
VISIBLE_MASK_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    pattern for pattern in PROTECTED_PATTERNS if pattern is not WIKILINK_RE
)

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}

# Known internal strings from the extracted Unity data.  They are deliberately
# left untouched and should not be reported as untranslated prose.
KNOWN_DEBUG_STRINGS = {
    "=[Inc",
    "AcceptedHigh",
    "AcceptedMid",
    "TravelledToDestinationId",
    "bkm_whitedoor",
    "do:crafted",
    "FNORD",
    "No-op",
    "rejoined",
}

ENGLISH_ALLOWLIST = {
    "am",
    "cm",
    "dlc",
    "id",
    "ii",
    "iii",
    "iv",
    "ix",
    "kg",
    "km",
    "mm",
    "npc",
    "ok",
    "pc",
    "pm",
    "ui",
    "url",
    "vi",
    "vii",
    "viii",
    "xi",
    "xii",
}

# Short setting terms whose English spelling is also an ordinary UI/prose word.
# Enforce these only in wording that clearly signals the setting sense.
AMBIGUOUS_TERM_CONTEXTS: dict[str, re.Pattern[str]] = {
    "Name": re.compile(r"\b(?:a|an|the)\s+Name\b|\bNames\b"),
    "Long": re.compile(r"\b(?:a|an|the)\s+Long\b|\bLongs\b"),
    "Know": re.compile(r"\b(?:a|an|the)\s+Know\b"),
    "Hour": re.compile(r"\b(?:a|an|the)\s+Hour\b|\bHours\b"),
    "State": re.compile(r"\bthe\s+State\b|\bState(?:'s|’s)\b"),
    "Cross": re.compile(r"\bthe\s+Cross\b|\bCross(?:'s|’s)\b"),
    "Wood": re.compile(r"\bthe\s+Wood\b|\bWood(?:'s|’s)\b"),
    "Wake": re.compile(r"\bthe\s+Wake\b|\bin\s+Wake\b"),
    "Glory": re.compile(r"\bthe\s+Glory\b|\bGlory(?:'s|’s)\b"),
    "Bounds": re.compile(r"\bthe\s+Bounds\b|\bBounds(?:'s|’s)\b"),
}


@dataclass(frozen=True)
class GlossaryEntry:
    source: str
    target: str
    kind: str
    case_sensitive: bool
    confidence: str
    notes: str


@dataclass(frozen=True)
class BannedVariant:
    variant: str
    preferred: str
    source_terms: tuple[str, ...]
    reason: str


# Project-specific deprecated variants collected during the translation pass.
# A source guard keeps ordinary Chinese prose from triggering false positives.
BANNED_VARIANTS: tuple[BannedVariant, ...] = (
    BannedVariant("诸部", "部委", ("Ministries", "the Ministries"), "同作 Steam 官方简中定名"),
    BannedVariant("联盟各部", "部委", ("Ministries", "the Ministries"), "同作 Steam 官方简中定名"),
    BannedVariant("黑市手腕", "钻营", ("Spivvery",), "同作 Steam 官方简中定名"),
    BannedVariant("世故", "修养", ("Sophistication",), "同作 Steam 官方简中定名"),
    BannedVariant("世俗技能", "世俗技艺", ("Worldly Skill",), "项目编辑裁决：与前作中文语体一致"),
    BannedVariant("异世技能", "异世技艺", ("Unworldly Skill", "Unworldly Skills"), "项目编辑裁决：Skill 统一为‘技艺’"),
    BannedVariant("技能检定", "技艺检定", ("Skill", "Skills"), "项目编辑裁决：Skill 统一为‘技艺’"),
    BannedVariant("光明之术", "光之技艺", ("Bright Art", "Bright Arts"), "新作技艺定名"),
    BannedVariant("夜之术", "夜之技艺", ("Night Art", "Night Arts"), "新作技艺定名"),
    BannedVariant("林泽", "丛林学", ("Bosk",), "技艺定名"),
    BannedVariant("鸟歌", "鸟鸣学", ("Birdsong",), "技艺定名"),
    BannedVariant("存护", "保存术", ("Preservation",), "技艺定名"),
    BannedVariant("启明术", "照明术", ("Illumination",), "技艺定名"),
    BannedVariant("噤声术", "静默术", ("Hushery",), "技艺定名"),
    BannedVariant("未思诸艺", "未拾技艺", ("Arts Unregarded", "Arts Unconsidered"), "技艺定名"),
    BannedVariant("未思技艺", "未拾技艺", ("Arts Unregarded", "Arts Unconsidered"), "技艺定名"),
    BannedVariant("未虑技艺", "未拾技艺", ("Arts Unregarded", "Arts Unconsidered"), "技艺定名"),
    BannedVariant("伊卡里亚主义", "伊加利亚主义", ("Icarianism",), "思想名称定名"),
    BannedVariant("伊卡利亚主义", "伊加利亚主义", ("Icarianism",), "思想名称定名"),
    BannedVariant("尼娜·拉加斯", "宁娜·拉格斯", ("Nina Lagasse",), "人物定名：依中文维基通行译名"),
    BannedVariant("妮娜·拉加斯", "宁娜·拉格斯", ("Nina Lagasse",), "人物定名：依中文维基通行译名"),
    BannedVariant("妮娜·拉格斯", "宁娜·拉格斯", ("Nina Lagasse",), "人物定名：依中文维基通行译名"),
    BannedVariant("宁娜·拉加斯", "宁娜·拉格斯", ("Nina Lagasse",), "人物定名：依中文维基通行译名"),
    BannedVariant("尼娜", "宁娜", ("Nina",), "人物简称：依中文维基通行译名"),
    BannedVariant("妮娜", "宁娜", ("Nina",), "人物简称：依中文维基通行译名"),
    BannedVariant("拉加斯", "拉格斯", ("Lagasse",), "人物姓氏：依中文维基通行译名"),
    BannedVariant("拉伽什", "拉格什", ("Lagash",), "地名及人物别称：依中文维基通行译名"),
    BannedVariant("科斯利", "科赛利", ("Coseley",), "人物定名"),
    BannedVariant("科兹利", "科赛利", ("Coseley",), "人物定名"),
    BannedVariant("科塞利", "科赛利", ("Coseley",), "人物定名"),
    BannedVariant("富奇内语", "富奇诺语", ("Fucine",), "语言定名"),
    BannedVariant("富辛语", "富奇诺语", ("Fucine",), "语言定名"),
    BannedVariant("介壳十字会", "介壳种", ("Carapace Cross",), "分类名称定名"),
    BannedVariant("甲壳十字会", "介壳种", ("Carapace Cross",), "分类名称定名"),
    BannedVariant("甲壳种", "介壳种", ("Carapace", "Carapace Cross"), "分类名称定名"),
    BannedVariant("甲胄异种", "介壳种", ("Cross", "Carapace Cross"), "分类名称定名"),
    BannedVariant("甲胄种", "介壳种", ("Cross", "Carapace Cross"), "分类名称定名"),
    BannedVariant("伊卡里安", "伊加利亚", ("Icarian", "Icarians", "Icarianism"), "思想与阵营定名"),
    BannedVariant("伊卡洛斯派", "伊加利亚派", ("Icarian", "Icarians"), "思想与阵营定名"),
    BannedVariant("欧比耶", "奥比耶", ("Aubière", "Aubiere"), "人物定名"),
    BannedVariant("欧比埃", "奥比耶", ("Aubière", "Aubiere"), "人物定名"),
    BannedVariant("西诺姆布尔", "西农布尔", ("Sinombre",), "人物定名"),
    BannedVariant("西诺姆", "西农布尔", ("Sinombre",), "人物定名"),
    BannedVariant("若姆", "豪梅", ("Jaume",), "人物定名"),
    BannedVariant("海梅", "豪梅", ("Jaume",), "Jaume 不与西班牙语 Jaime 混同"),
    BannedVariant("巡礼者玫瑰", "朝圣者玫瑰", ("The Pilgrim Rose",), "作品定名"),
    BannedVariant("梦境协调办公室", "本体梦理协调办公室", ("Office of Onteiric Coordination",), "机构定名"),
    BannedVariant("本体秘理协调办公室", "本体梦理协调办公室", ("Office of Onteiric Coordination",), "旧译未保留 oneirology 词根"),
    BannedVariant("梦境协调", "本体梦理协调", ("Onteiric Coordination", "ONTEIRIC CO-ORDINATION"), "机构职能定名"),
    BannedVariant("本体秘理协调", "本体梦理协调", ("Onteiric Coordination", "ONTEIRIC CO-ORDINATION"), "旧译未保留 oneirology 词根"),
    BannedVariant("本体秘理", "本体梦理", ("Onteirology", "onteiric", "onteirological", "onteiriologically", "onteiristically"), "旧译未保留 ontology／oneirology 双重词根"),
    BannedVariant("西尼亚尔", "西涅尔", ("signaire", "Signaire"), "按法语实际读音 /si.ɲɛʁ/ 定名"),
    BannedVariant("一元体", "一者", ("Henad", "henad", "henads"), "Henad 单复数定名"),
    BannedVariant("trygikon", "三角灵", ("Trygikon", "trygikon"), "术语漏译"),
    BannedVariant("瞳中扉", "瞳中之扉", ("Door-in-the-Eye", "Door in the Eye"), "前作 Wiki 词条定名"),
    BannedVariant("神链", "序链", ("Seira", "seira", "seirai", "seiral"), "普罗克洛斯神学术语与同作 Wiki 定名"),
    BannedVariant("不可征服之太阳教会", "无敌太阳教会", ("Church of the Unconquered Sun", "Church of the Unconquerable Sun"), "前作机构定名"),
    BannedVariant("不败太阳", "无敌太阳", ("Unconquered Sun", "Unconquerable Sun"), "前作机构与太阳称号定名"),
    BannedVariant("圣秩会", "领受圣职", ("Ordination",), "Ordination 是神学行为，不是名为‘圣秩会’的机构"),
    BannedVariant("领受的圣秩", "领受圣职", ("ordained",), "避免名词化直译和机构歧义"),
    BannedVariant("诸阳之书", "骄阳之书", ("Book of Suns",), "沿用前作作品名"),
    BannedVariant("公认本", "通行版", ("Received Version", "Received and Sanctioned versions"), "沿用前作版本名"),
    BannedVariant("通行本", "通行版", ("Received Version", "Received and Sanctioned versions"), "沿用前作版本名"),
    BannedVariant("核准本", "核准版", ("Sanctioned Version", "Received and Sanctioned versions"), "沿用前作版本名"),
    BannedVariant("太阳中之战", "太阳之战", ("War in the Sun",), "同作 Steam 官方简中定名"),
    BannedVariant("太阳大战", "太阳之战", ("War in the Sun",), "同作 Steam 官方简中定名"),
    BannedVariant("世界大战", "世界之战", ("War in the World",), "同作 Steam 官方简中定名"),
    BannedVariant("圣阿格尼丝", "圣亚割妮", ("St Agnes",), "沿用《密教模拟器》既有圣人名"),
    BannedVariant("圣艾格尼丝", "圣亚割妮", ("St Agnes",), "沿用《密教模拟器》既有圣人名"),
    BannedVariant("圣梅兰克忒", "圣梅兰瑟", ("St Melancthe", "Melancthe"), "沿用《司辰之书》既有圣人名"),
    BannedVariant("圣布兰丹修道院", "圣布伦丹修道院", ("Abbey of St Brandan",), "沿用《司辰之书》既有地点名"),
    BannedVariant("三重结姐妹会", "三重绳结姐妹会", ("Sisterhood of the Triple Knot",), "沿用《司辰之书》既有组织名"),
    BannedVariant("利米亚修会", "利米亚教团", ("Ordo Limiae",), "沿用《司辰之书》既有组织名"),
    BannedVariant("忘却者", "忘却会", ("Obliviates",), "沿用《司辰之书》既有组织名"),
    BannedVariant("思特拉斯科因", "斯特拉思科因", ("Strathcoyne",), "沿用《司辰之书》既有人名"),
    BannedVariant("斯特拉斯科因", "斯特拉思科因", ("Strathcoyne",), "沿用《司辰之书》既有人名"),
    BannedVariant("伊洛波利", "伊利奥波里", ("Illopoly",), "沿用《司辰之书》《夜游漫记》既有人名"),
    BannedVariant("伊里奥波利", "伊利奥波里", ("Illopoly",), "沿用《司辰之书》《夜游漫记》既有人名"),
    BannedVariant("伊利奥波利", "伊利奥波里", ("Illopoly",), "沿用《司辰之书》《夜游漫记》既有人名"),
    BannedVariant("夏伊玛", "柴玛", ("Chaima",), "沿用《司辰之书》既有人名"),
    BannedVariant("沙伊玛", "柴玛", ("Chaima",), "沿用《司辰之书》既有人名"),
    BannedVariant("塞蕾娜", "瑟雷娜", ("Serena",), "沿用《司辰之书》既有人名"),
    BannedVariant("塞雷诺", "瑟雷诺", ("Sereno",), "保持 Serena/Sereno 同一音译词根"),
    BannedVariant("拉韦林", "拉维林", ("Raveline", "Ravelines"), "沿用《密教模拟器》Exile DLC 既有译名"),
    BannedVariant("拉韦利讷", "拉维林", ("Raveline", "Ravelines"), "沿用《密教模拟器》Exile DLC 既有译名"),
    BannedVariant("大墨", "伟大墨水", ("Great Inks",), "沿用《司辰之书》既有译名"),
    BannedVariant("乌祖尔特", "珀金", ("Uzult", "uzult"), "沿用《司辰之书》终刻墨既有译名"),
    BannedVariant("禽形", "鸟形", ("Aviform", "Aviforms"), "沿用《司辰之书》鸟形司辰既有译名"),
    BannedVariant("无形塞拉皮翁", "隐形的塞拉皮雍", ("Invisible Serapeum",), "沿用《司辰之书》既有地点名"),
    BannedVariant("隐形塞拉皮雍", "隐形的塞拉皮雍", ("Invisible Serapeum",), "沿用《司辰之书》既有地点名"),
    BannedVariant("永不停歇之心", "不息之心", ("Heart Relentless",), "沿用前作司辰称号"),
    BannedVariant("未筑之城", "未建之城", ("City Unbuilt", "Unbuilt City"), "沿用《司辰之书》既有地点名"),
    BannedVariant("霍科鲍德", "霍科博尔德", ("Hokobald",), "沿用《司辰之书》既有人名"),
    BannedVariant("烛匠", "制烛人", ("Chandler",), "沿用《司辰之书》司辰称号"),
    BannedVariant("蜡烛匠", "制烛人", ("Chandler",), "沿用《司辰之书》司辰称号"),
    BannedVariant("启明牧者", "沐光明的牧羊人", ("Shepherd-Illuminate", "Shepherd Illuminate"), "沿用《司辰之书》既有称号"),
    BannedVariant("沐光明牧者", "沐光明的牧羊人", ("Shepherd-Illuminate", "Shepherd Illuminate"), "沿用《司辰之书》既有称号"),
    BannedVariant("牧者·启明者", "沐光明的牧羊人", ("Shepherd-Illuminate", "Shepherd Illuminate"), "沿用《司辰之书》既有称号"),
    BannedVariant("法兰西斯克", "弗朗西斯克", ("francisque", "francisques", "Francisque", "Francisques"), "法兰西邦国货币与斧徽定名"),
    BannedVariant("雅努维埃", "让维耶", ("Janvier", "Janviers"), "同一裁缝家族姓氏定名"),
    BannedVariant("吉讷福尔", "吉内福尔", ("Guinefort", "St Guinefort"), "法国民间圣犬名统一"),
    BannedVariant("费利克斯家", "菲利克斯之家", ("Chez Felix", "chez Felix"), "昂蒂布酒馆地点名统一"),
    BannedVariant("两场大战", "诸战", ("the Wars", "Wars"), "不得给固定历史时期擅加数量"),
    BannedVariant("几场大战", "诸战", ("the Wars", "Wars"), "固定历史时期定名"),
    BannedVariant("<i>poinçonneuse</i>", "<i>女检票员</i>", ("poinçonneuse",), "普通法语职业名在车站场景统一翻译"),
    BannedVariant("法兰西克", "弗朗西斯克", ("francisque", "francisques", "Francisque", "Francisques"), "法兰西邦国货币与斧徽定名"),
    BannedVariant("外籍军团", "军团", ("Légion", "Légion du Seuil"), "Légion 是门槛军团而非法国外籍军团"),
    BannedVariant("阿伦·皮", "阿伦·褪皮", ("Arun Peel",), "沿用前作社区既有角色译名"),
    BannedVariant("我的过去", "我的过往", ("My Past",), "回忆条目标题统一"),
)


class AuditInputError(RuntimeError):
    """Raised when an input cannot be parsed reliably."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit a merged Simplified-Chinese review catalog without modifying it."
    )
    parser.add_argument("catalog", type=Path, help="Merged review_catalog.jsonl")
    parser.add_argument("glossary", type=Path, help="glossary.csv")
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Optional standalone JSON report path; never overwrites either input",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full JSON report to stdout instead of the human summary",
    )
    parser.add_argument(
        "--max-console",
        type=int,
        default=80,
        help="Maximum individual issues shown in human output (default: 80)",
    )
    parser.add_argument(
        "--fail-on",
        choices=("never", "error", "warning"),
        default="error",
        help="Exit non-zero at this severity threshold (default: error)",
    )
    parser.add_argument(
        "--duplicate-target-min-chars",
        type=int,
        default=6,
        help="Minimum visible target length for duplicate-translation checks",
    )
    args = parser.parse_args(argv)
    if args.max_console < 0:
        parser.error("--max-console must be non-negative")
    if args.duplicate_target_min_chars < 1:
        parser.error("--duplicate-target-min-chars must be positive")
    return args


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise AuditInputError(
                        f"{path}:{line_number}: invalid JSON: {exc.msg}"
                    ) from exc
                if not isinstance(row, dict):
                    raise AuditInputError(f"{path}:{line_number}: expected a JSON object")
                row["_audit_line"] = line_number
                rows.append(row)
    except OSError as exc:
        raise AuditInputError(f"cannot read catalog {path}: {exc}") from exc
    return rows


def read_glossary(path: Path) -> list[GlossaryEntry]:
    required = {"source_en", "target_zh", "type", "case_sensitive", "confidence", "notes"}
    entries: list[GlossaryEntry] = []
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = required - set(reader.fieldnames or ())
            if missing:
                raise AuditInputError(
                    f"{path}: missing glossary columns: {', '.join(sorted(missing))}"
                )
            for line_number, row in enumerate(reader, 2):
                source = row["source_en"].strip()
                target = row["target_zh"].strip()
                if not source or not target:
                    raise AuditInputError(
                        f"{path}:{line_number}: source_en and target_zh must be non-empty"
                    )
                entries.append(
                    GlossaryEntry(
                        source=source,
                        target=target,
                        kind=row["type"].strip(),
                        case_sensitive=row["case_sensitive"].strip().lower()
                        not in {"false", "0", "no"},
                        confidence=row["confidence"].strip(),
                        notes=row["notes"].strip(),
                    )
                )
    except OSError as exc:
        raise AuditInputError(f"cannot read glossary {path}: {exc}") from exc
    return entries


def mask_matches(text: str, patterns: Iterable[re.Pattern[str]]) -> str:
    """Replace protected spans with spaces while preserving rough positions."""

    result = text
    for pattern in patterns:
        result = pattern.sub(lambda match: " " * len(match.group(0)), result)
    return result


def visible_text(text: str) -> str:
    unwrapped_links = WIKILINK_RE.sub(lambda match: match.group(0)[2:-2], text)
    return mask_matches(unwrapped_links, VISIBLE_MASK_PATTERNS)


def normalized_text(text: str) -> str:
    return unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n").strip()


def compact_excerpt(text: str, limit: int = 150) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def source_term_pattern(term: str, case_sensitive: bool = True) -> re.Pattern[str]:
    escaped = re.escape(term).replace(r"\ ", r"\s+")
    left = r"(?<![A-Za-z0-9])" if term and term[0].isalnum() else ""
    right = r"(?![A-Za-z0-9])" if term and term[-1].isalnum() else ""
    return re.compile(left + escaped + right, 0 if case_sensitive else re.IGNORECASE)


def source_mentions(text: str, term: str, case_sensitive: bool = True) -> bool:
    return bool(source_term_pattern(term, case_sensitive).search(text))


def row_context(row: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "line": row.get("_audit_line"),
        "domain": row.get("domain", ""),
    }
    contexts = row.get("contexts")
    if isinstance(contexts, list) and contexts and isinstance(contexts[0], dict):
        first = contexts[0]
        for key in ("conversation", "speaker", "conversant", "field_path", "asset_file"):
            if first.get(key) not in (None, ""):
                result[key] = first[key]
    return result


def add_row_issue(
    issues: list[dict[str, Any]],
    row: dict[str, Any],
    severity: str,
    code: str,
    detail: str,
    suggestion: str = "",
    **extra: Any,
) -> None:
    issue: dict[str, Any] = {
        "severity": severity,
        "code": code,
        "id": row.get("id", ""),
        "source": row.get("source", ""),
        "translation": row.get("translation", ""),
        "detail": detail,
        "context": row_context(row),
    }
    if suggestion:
        issue["suggestion"] = suggestion
    issue.update(extra)
    issues.append(issue)


def build_effective_glossary(entries: list[GlossaryEntry]) -> list[GlossaryEntry]:
    """Add common source forms that are implicit in article-prefixed entries."""

    effective = list(entries)
    targets = {entry.source: entry.target for entry in entries}
    aliases = {
        "Group": targets.get("the Group", "集团"),
        "Union": targets.get("the Union", "联盟"),
        "Ministries": targets.get("the Ministries", "联盟"),
    }
    present = {entry.source for entry in entries}
    for source, target in aliases.items():
        if source not in present:
            effective.append(
                GlossaryEntry(source, target, "势力", True, "high", "审计别名")
            )
    return effective


def audit_glossary_conflicts(
    entries: list[GlossaryEntry], issues: list[dict[str, Any]]
) -> None:
    grouped: dict[str, set[str]] = collections.defaultdict(set)
    for entry in entries:
        grouped[entry.source].add(entry.target)
    for source, targets in sorted(grouped.items()):
        if len(targets) > 1:
            issues.append(
                {
                    "severity": "error",
                    "code": "glossary_conflict",
                    "id": "",
                    "source": source,
                    "translation": "",
                    "detail": f"术语表同一源词存在 {len(targets)} 个目标译名",
                    "variants": sorted(targets),
                }
            )


def audit_fixed_terms(
    rows: list[dict[str, Any]],
    entries: list[GlossaryEntry],
    issues: list[dict[str, Any]],
) -> None:
    effective = build_effective_glossary(entries)
    for row in rows:
        source = visible_text(str(row.get("source", "")))
        target = visible_text(str(row.get("translation", "")))
        exact_glossary_match = any(
            (
                source == entry.source
                if entry.case_sensitive
                else source.casefold() == entry.source.casefold()
            )
            and target == entry.target
            for entry in effective
        )
        seen: set[tuple[str, str]] = set()
        for entry in effective:
            # A longer exact label may intentionally lexicalise its headword
            # differently (e.g. Weariness Collapse -> 累倒). Once the complete
            # source/target pair is canonical, substring terms must not produce
            # false "missing" warnings.
            if exact_glossary_match:
                continue
            if not source_mentions(source, entry.source, entry.case_sensitive):
                continue
            context_rule = AMBIGUOUS_TERM_CONTEXTS.get(entry.source)
            if context_rule is not None and not context_rule.search(source):
                continue
            if entry.target in target:
                continue
            key = (entry.source, entry.target)
            if key in seen:
                continue
            seen.add(key)
            add_row_issue(
                issues,
                row,
                "warning",
                "fixed_term_missing",
                f"源文含固定术语“{entry.source}”，译文未见规范译名“{entry.target}”",
                f"核对是否应使用“{entry.target}”",
                term={
                    "source": entry.source,
                    "target": entry.target,
                    "type": entry.kind,
                    "confidence": entry.confidence,
                },
            )

        for rule in BANNED_VARIANTS:
            # Some deprecated forms are substrings of the canonical term
            # (for example “大墨” inside “伟大墨水”). Ignore occurrences that
            # exist only as part of the preferred spelling.
            target_without_preferred = target.replace(rule.preferred, "")
            if rule.variant not in target_without_preferred:
                continue
            if not any(source_mentions(source, term, False) for term in rule.source_terms):
                continue
            add_row_issue(
                issues,
                row,
                "error",
                "banned_term_variant",
                f"检测到已禁用变体“{rule.variant}”：{rule.reason}",
                f"改用“{rule.preferred}”",
                variant=rule.variant,
                preferred=rule.preferred,
            )


def looks_like_debug_string(value: str) -> bool:
    stripped = value.strip()
    if stripped in KNOWN_DEBUG_STRINGS:
        return True
    if not stripped or re.search(r"\s", stripped):
        return False
    if re.fullmatch(r"[=:+\-*/.\[\]A-Za-z0-9_]+", stripped) is None:
        return False
    return bool(
        "_" in stripped
        or ":" in stripped
        or stripped.startswith(("=", "["))
        or re.search(r"[a-z][A-Z]|[A-Za-z]Id$", stripped)
    )


def english_fragments(text: str) -> list[str]:
    cleaned = visible_text(text)
    for debug in sorted(KNOWN_DEBUG_STRINGS, key=len, reverse=True):
        cleaned = cleaned.replace(debug, " " * len(debug))
    cleaned = IDENTIFIER_RE.sub(lambda match: " " * len(match.group(0)), cleaned)
    words: list[tuple[int, int, str]] = []
    for match in ENGLISH_WORD_RE.finditer(cleaned):
        word = match.group(1)
        folded = word.casefold().replace("’", "'")
        if folded in ENGLISH_ALLOWLIST:
            continue
        if len(re.sub(r"[^A-Za-z]", "", word)) < 4:
            continue
        words.append((match.start(), match.end(), word))
    if not words:
        return []

    groups: list[list[tuple[int, int, str]]] = [[words[0]]]
    for item in words[1:]:
        gap = cleaned[groups[-1][-1][1] : item[0]]
        if re.fullmatch(r"[\s,.'’\-–—:;/()]*", gap):
            groups[-1].append(item)
        else:
            groups.append([item])
    fragments: list[str] = []
    for group in groups:
        start, end = group[0][0], group[-1][1]
        fragments.append(cleaned[start:end].strip())
    return fragments


def audit_english_residue(
    rows: list[dict[str, Any]], issues: list[dict[str, Any]]
) -> None:
    for row in rows:
        source = str(row.get("source", ""))
        target = str(row.get("translation", ""))
        if normalized_text(source) == normalized_text(target) and looks_like_debug_string(target):
            continue
        fragments = english_fragments(target)
        if not fragments:
            continue
        has_han = bool(HAN_RE.search(visible_text(target)))
        code = "english_residue" if has_han else "unchanged_english"
        detail = "简中译文仍含连续英文" if has_han else "译文仍为英文且不像已知调试串"
        add_row_issue(
            issues,
            row,
            "warning",
            code,
            detail + "：" + "；".join(f"“{fragment}”" for fragment in fragments[:6]),
            "确认是专名、引文或技术字符串；否则翻译或音译",
            fragments=fragments,
        )


def punctuation_findings(text: str) -> list[str]:
    cleaned = visible_text(text)
    findings: list[str] = []
    patterns = (
        ("中文旁使用半角逗号/分号/冒号/问叹号", re.compile(r"[\u3400-\u9fff][,;:!?]|[,;:!?][\u3400-\u9fff]")),
        ("中文旁使用半角句点", re.compile(r"[\u3400-\u9fff]\.(?!\d)|(?<!\d)\.[\u3400-\u9fff]")),
        ("中文使用三个半角点作省略号", re.compile(r"[\u3400-\u9fff]?\.\.\.[\u3400-\u9fff]?")),
        ("中文使用半角圆括号", re.compile(r"\([\u3400-\u9fff]|[\u3400-\u9fff]\)")),
        ("中文之间使用半角连字符", re.compile(r"[\u3400-\u9fff]\s*-\s*[\u3400-\u9fff]")),
        ("中文使用直引号", re.compile(r"[\"'][^\"'\n]*[\u3400-\u9fff][^\"'\n]*[\"']")),
    )
    for label, pattern in patterns:
        matches = [compact_excerpt(match.group(0), 50) for match in pattern.finditer(cleaned)]
        if matches:
            findings.append(f"{label}：{', '.join(matches[:4])}")
    return findings


def audit_punctuation(rows: list[dict[str, Any]], issues: list[dict[str, Any]]) -> None:
    for row in rows:
        findings = punctuation_findings(str(row.get("translation", "")))
        if findings:
            add_row_issue(
                issues,
                row,
                "warning",
                "mixed_punctuation",
                "；".join(findings),
                "按简中正文规范改用全角标点；技术片段则可在复核后保留",
                findings=findings,
            )


SOURCE_AUTHORIAL_DASH_RE = re.compile(
    r"(?:(?<=\s)|^)-{1,3}(?=\s|$|[A-Za-z])|[\u2013\u2014]+"
)
SINGLE_EM_DASH_RE = re.compile(r"(?<!\u2014)\u2014(?!\u2014)")


def audit_dash_alignment(
    rows: list[dict[str, Any]], issues: list[dict[str, Any]]
) -> None:
    """Flag dash typography and likely translator-added dash density for review.

    A Chinese em dash is two U+2014 characters.  The source frequently uses
    spaced hyphens, double/triple hyphens, en dashes, or em dashes as the same
    authorial device, so counts are compared semantically rather than by glyph.
    This is deliberately a warning-only audit: Chinese syntax may legitimately
    add or remove a boundary even when the source punctuation differs.
    """

    for row in rows:
        source = visible_text(str(row.get("source", "")))
        target = visible_text(str(row.get("translation", "")))
        source_count = len(SOURCE_AUTHORIAL_DASH_RE.findall(source))
        target_count = target.count("——")

        findings: list[str] = []
        # A single U+2014 can be a legitimate Chinese connection mark (一字线)
        # in a numeric range or a hyphenated proper name.  Only flag it when it
        # is used in Chinese prose without a matching source connector.
        source_has_connector = bool(re.search(r"(?<=\w)-(?=\w)", source))
        unexplained_single = False
        for match in SINGLE_EM_DASH_RE.finditer(target):
            left = target[match.start() - 1] if match.start() else ""
            right = target[match.end()] if match.end() < len(target) else ""
            if left.isdigit() and right.isdigit():
                continue
            if source_has_connector:
                continue
            if not HAN_RE.search(target):
                continue
            unexplained_single = True
            break
        if unexplained_single:
            findings.append("译文疑似以单个 U+2014 充当破折号；简中破折号应写作两个字符“——”")
        if target_count >= 2 and source_count == 0:
            findings.append(
                f"原文无作者式破折停顿，译文新增 {target_count} 处长破折号"
            )
        elif target_count >= 4 and target_count > source_count + 1:
            findings.append(
                f"译文长破折号密度明显高于原文（原文 {source_count}，译文 {target_count}）"
            )

        if findings:
            add_row_issue(
                issues,
                row,
                "warning",
                "dash_alignment_review",
                "；".join(findings),
                "对照原句确认是必要的中文插入语/中断；否则改用逗号、冒号、分号或句号",
                source_dash_count=source_count,
                translation_dash_count=target_count,
            )


def audit_duplicate_sources(
    rows: list[dict[str, Any]], issues: list[dict[str, Any]]
) -> None:
    grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        grouped[str(row.get("source", ""))].append(row)
    for source, members in grouped.items():
        variants: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        for row in members:
            variants[normalized_text(str(row.get("translation", "")))].append(row)
        if len(variants) <= 1:
            continue
        variant_payload = [
            {
                "translation": translation,
                "ids": [str(row.get("id", "")) for row in variant_rows],
                "domains": sorted({str(row.get("domain", "")) for row in variant_rows}),
            }
            for translation, variant_rows in sorted(variants.items())
        ]
        issues.append(
            {
                "severity": "warning",
                "code": "duplicate_source_drift",
                "id": "",
                "ids": [str(row.get("id", "")) for row in members],
                "source": source,
                "translation": "",
                "detail": f"同一 source 出现 {len(variants)} 种译法",
                "suggestion": "结合 speaker、conversant 与领域确认是否属于必要的上下文差异",
                "variants": variant_payload,
            }
        )


def source_similarity(values: list[str]) -> float:
    if len(values) < 2:
        return 1.0
    ratios: list[float] = []
    for index, left in enumerate(values):
        for right in values[index + 1 :]:
            ratios.append(difflib.SequenceMatcher(None, left, right).ratio())
    return min(ratios, default=1.0)


def audit_duplicate_targets(
    rows: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    min_chars: int,
) -> None:
    grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        target = normalized_text(str(row.get("translation", "")))
        if len(visible_text(target).strip()) < min_chars:
            continue
        if looks_like_debug_string(target):
            continue
        grouped[target].append(row)

    for target, members in grouped.items():
        sources = sorted({normalized_text(str(row.get("source", ""))) for row in members})
        if len(sources) <= 1:
            continue
        similarity = source_similarity(sources)
        # Two near-identical English variants legitimately sharing one Chinese
        # rendering are common.  Three or more sources merit review regardless.
        if len(sources) == 2 and similarity >= 0.72:
            continue
        issues.append(
            {
                "severity": "warning",
                "code": "duplicate_translation_suspect",
                "id": "",
                "ids": [str(row.get("id", "")) for row in members],
                "source": "",
                "translation": target,
                "detail": f"{len(sources)} 条不同 source 共用同一译文",
                "suggestion": "确认不是复制粘贴、漏译或过度归并；同义短标签可保留",
                "source_similarity_min": round(similarity, 3),
                "sources": [compact_excerpt(source, 180) for source in sources[:12]],
                "contexts": [row_context(row) for row in members[:12]],
            }
        )


def validate_catalog_rows(
    rows: list[dict[str, Any]], issues: list[dict[str, Any]]
) -> None:
    seen_ids: dict[str, dict[str, Any]] = {}
    for row in rows:
        missing = [key for key in ("id", "source", "translation") if key not in row]
        if missing:
            add_row_issue(
                issues,
                row,
                "error",
                "catalog_missing_field",
                "catalog 行缺少字段：" + ", ".join(missing),
            )
            continue
        row_id = str(row.get("id", ""))
        if row_id in seen_ids:
            add_row_issue(
                issues,
                row,
                "error",
                "duplicate_id",
                f"ID 与 catalog 第 {seen_ids[row_id].get('_audit_line')} 行重复",
            )
        else:
            seen_ids[row_id] = row
        if not str(row.get("translation", "")).strip():
            add_row_issue(
                issues,
                row,
                "error",
                "empty_translation",
                "译文为空",
            )


def issue_sort_key(issue: dict[str, Any]) -> tuple[Any, ...]:
    context = issue.get("context") or {}
    return (
        SEVERITY_ORDER.get(str(issue.get("severity")), 99),
        str(issue.get("code", "")),
        str(issue.get("id", "")),
        int(context.get("line") or 0),
    )


def build_report(
    catalog_path: Path,
    glossary_path: Path,
    rows: list[dict[str, Any]],
    glossary: list[GlossaryEntry],
    min_duplicate_chars: int,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    validate_catalog_rows(rows, issues)
    audit_glossary_conflicts(glossary, issues)
    audit_fixed_terms(rows, glossary, issues)
    audit_english_residue(rows, issues)
    audit_punctuation(rows, issues)
    audit_dash_alignment(rows, issues)
    audit_duplicate_sources(rows, issues)
    audit_duplicate_targets(rows, issues, min_duplicate_chars)
    issues.sort(key=issue_sort_key)

    severity_counts = collections.Counter(issue["severity"] for issue in issues)
    code_counts = collections.Counter(issue["code"] for issue in issues)
    return {
        "tool": "audit_translation_consistency.py",
        "schema_version": 1,
        "inputs": {
            "catalog": str(catalog_path.resolve()),
            "glossary": str(glossary_path.resolve()),
        },
        "summary": {
            "catalog_rows": len(rows),
            "glossary_rows": len(glossary),
            "issues": len(issues),
            "errors": severity_counts.get("error", 0),
            "warnings": severity_counts.get("warning", 0),
            "info": severity_counts.get("info", 0),
            "by_code": dict(sorted(code_counts.items())),
        },
        "issues": issues,
    }


def print_human_report(report: dict[str, Any], max_console: int) -> None:
    summary = report["summary"]
    print("Translation consistency audit")
    print(f"Catalog:  {report['inputs']['catalog']}")
    print(f"Glossary: {report['inputs']['glossary']}")
    print(
        "Rows: {catalog_rows} | Glossary: {glossary_rows} | "
        "Errors: {errors} | Warnings: {warnings} | Info: {info}".format(**summary)
    )
    if summary["by_code"]:
        print("By code:")
        for code, count in summary["by_code"].items():
            print(f"  {code}: {count}")
    shown = report["issues"][:max_console]
    if shown:
        print("Issues:")
    for issue in shown:
        location = issue.get("id") or ",".join(issue.get("ids", [])[:3]) or "catalog"
        print(
            f"  [{str(issue['severity']).upper()}] {issue['code']} {location}: "
            f"{compact_excerpt(str(issue['detail']), 220)}"
        )
        if issue.get("suggestion"):
            print(f"    -> {compact_excerpt(str(issue['suggestion']), 220)}")
    omitted = len(report["issues"]) - len(shown)
    if omitted > 0:
        print(f"  ... {omitted} more issue(s); use --json or --json-output for all details")


def exit_code(report: dict[str, Any], fail_on: str) -> int:
    if fail_on == "never":
        return 0
    if fail_on == "warning":
        return 1 if report["summary"]["errors"] or report["summary"]["warnings"] else 0
    return 1 if report["summary"]["errors"] else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        catalog = read_jsonl(args.catalog)
        glossary = read_glossary(args.glossary)
        report = build_report(
            args.catalog,
            args.glossary,
            catalog,
            glossary,
            args.duplicate_target_min_chars,
        )
    except AuditInputError as exc:
        print(f"audit input error: {exc}", file=sys.stderr)
        return 2

    if args.json_output:
        if args.json_output.resolve() in {args.catalog.resolve(), args.glossary.resolve()}:
            print("refusing to overwrite an input file", file=sys.stderr)
            return 2
        try:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        except OSError as exc:
            print(f"cannot write JSON report {args.json_output}: {exc}", file=sys.stderr)
            return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human_report(report, args.max_console)
        if args.json_output:
            print(f"JSON report: {args.json_output.resolve()}")
    return exit_code(report, args.fail_on)


if __name__ == "__main__":
    raise SystemExit(main())
