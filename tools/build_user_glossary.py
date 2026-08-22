#!/usr/bin/env python3
"""Validate terminology provenance and build the player-facing glossary.

The internal glossary is intentionally flat because the runtime QA works on exact
English spellings.  The public glossary is concept-oriented: singular/plural,
capitalisation and adjectival variants share one provenance record, while this
builder still requires every internal row to be covered exactly once.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse


ORIGIN_FILES = {
    "predecessor": "predecessor.jsonl",
    "travelling_new": "travelling_new.jsonl",
    "real_world": "real_world.jsonl",
    "editorial": "editorial.jsonl",
}

ORIGIN_TITLES = {
    "predecessor": "前作既有术语",
    "travelling_new": "《夜游漫记》新增术语",
    "real_world": "现实宗教、历史、语言与学术实体",
    "editorial": "界面与编辑裁决",
}

AUDIT_BASIS_LABELS = {
    "predecessor_official_same_id": "前作官中同 ID",
    "predecessor_official_corpus": "前作官中语料",
    "same_game_official_zh": "同作官方简中",
    "external_authority": "权威外部资料",
    "explicit_editorial_policy": "明确编辑裁决",
    "editorial_transliteration": "编辑音译",
    "language_or_professional_reference": "语言／专业资料",
    "current_asset_semantics": "当前资产语义",
    "retired_not_in_current_assets": "当前资产已退役",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glossary", type=Path, default=Path("glossary/glossary.csv"))
    parser.add_argument(
        "--provenance-dir", type=Path, default=Path("glossary/provenance")
    )
    parser.add_argument("--output", type=Path, default=Path("docs/USER_GLOSSARY.md"))
    parser.add_argument(
        "--quote-provenance", type=Path, default=Path("glossary/quote_provenance.jsonl")
    )
    parser.add_argument(
        "--conversation-description-provenance",
        type=Path,
        default=Path("glossary/conversation_description_provenance.jsonl"),
    )
    parser.add_argument(
        "--final-audit", type=Path, default=Path("glossary/final_term_audit.jsonl")
    )
    parser.add_argument("--worklist", type=Path, default=Path("build/worklist_k83/worklist.jsonl"))
    parser.add_argument("--translations", type=Path, default=Path("translations_k97"))
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def load_glossary(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"source_en", "target_zh", "type", "confidence", "notes"}
    missing = required - set(rows[0]) if rows else required
    if missing:
        raise ValueError(f"glossary missing columns: {sorted(missing)}")
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        source = row["source_en"].strip()
        if not source:
            raise ValueError("glossary contains an empty source_en")
        if source in result:
            raise ValueError(f"duplicate glossary source_en: {source}")
        result[source] = row
    return result


def load_records(directory: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for origin, filename in ORIGIN_FILES.items():
        path = directory / filename
        if not path.exists():
            raise ValueError(f"missing provenance file: {path}")
        with path.open("r", encoding="utf-8-sig") as handle:
            for line_no, raw in enumerate(handle, 1):
                raw = raw.strip()
                if not raw or raw.startswith("#"):
                    continue
                try:
                    record = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{line_no}: {exc}") from exc
                if not isinstance(record, dict):
                    raise ValueError(f"{path}:{line_no}: record must be an object")
                record["origin"] = origin
                record["_path"] = str(path)
                record["_line"] = line_no
                records.append(record)
    return records


def nonempty(record: dict[str, object], key: str) -> bool:
    return isinstance(record.get(key), str) and bool(str(record[key]).strip())


def research_fingerprint(
    record: dict[str, object], field: str, glossary: dict[str, dict[str, str]]
) -> str:
    """Expose boilerplate that differs only by the term substituted into it."""
    value = str(record.get(field, "")).casefold()
    source_terms = [str(record.get("canonical", "")), *[str(a) for a in record.get("aliases", [])]]
    terms = list(source_terms)
    for term in source_terms:
        row = glossary.get(term)
        if row:
            terms.append(row["target_zh"])
    for term in sorted({term for term in terms if term}, key=len, reverse=True):
        value = re.sub(re.escape(term.casefold()), "<词项>", value)
    return re.sub(r"\s+", " ", value).strip()


def validate(
    glossary: dict[str, dict[str, str]], records: list[dict[str, object]], strict: bool
) -> list[str]:
    errors: list[str] = []
    coverage: dict[str, list[str]] = defaultdict(list)
    canonical_seen: Counter[str] = Counter()

    for record in records:
        location = f"{record['_path']}:{record['_line']}"
        canonical = record.get("canonical")
        aliases = record.get("aliases", [])
        if not isinstance(canonical, str) or not canonical.strip():
            errors.append(f"{location}: missing canonical")
            continue
        canonical = canonical.strip()
        canonical_seen[canonical] += 1
        if not isinstance(aliases, list) or any(not isinstance(a, str) for a in aliases):
            errors.append(f"{location}: aliases must be a string list")
            aliases = []
        terms = [canonical, *[a.strip() for a in aliases if a.strip()]]
        for term in terms:
            coverage[term].append(location)
            if term not in glossary:
                errors.append(f"{location}: term not found in glossary: {term!r}")

        status = str(record.get("status", "")).strip()
        if status not in {"verified", "provisional", "draft"}:
            errors.append(f"{location}: invalid status {status!r}")
        if strict and status != "verified":
            errors.append(f"{location}: strict build requires status=verified")

        origin = str(record["origin"])
        for key in ("reference_label", "reference_url", "evidence", "rationale"):
            if not nonempty(record, key):
                errors.append(f"{location}: missing {key}")
        url = str(record.get("reference_url", "")).strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append(f"{location}: reference_url must be an HTTP(S) URL")
        if origin == "predecessor" and not parsed.netloc.endswith("huijiwiki.com"):
            errors.append(f"{location}: predecessor term must link a Huiji Wiki entry")
        if origin == "travelling_new" and not nonempty(record, "alternatives"):
            errors.append(f"{location}: new term must document rejected alternatives")
        public_research = " ".join(
            str(record.get(key, ""))
            for key in ("reference_label", "evidence", "rationale", "alternatives")
        )
        stale = re.search(r"(?i)\bj\.\d+\b|暂译|本轮|润色期", public_research)
        if stale:
            errors.append(
                f"{location}: player-facing research contains stale/internal marker {stale.group(0)!r}"
            )
        if origin == "travelling_new":
            target = glossary.get(canonical, {}).get("target_zh", "")
            if target and target not in f"{record.get('evidence', '')} {record.get('rationale', '')}":
                errors.append(
                    f"{location}: evidence/rationale does not name final target {target!r}"
                )
        comparison_label = record.get("comparison_label")
        comparison_url = record.get("comparison_url")
        if bool(comparison_label) != bool(comparison_url):
            errors.append(f"{location}: comparison_label and comparison_url must occur together")
        if comparison_url:
            comparison_parsed = urlparse(str(comparison_url))
            if comparison_parsed.scheme not in {"http", "https"} or not comparison_parsed.netloc:
                errors.append(f"{location}: comparison_url must be an HTTP(S) URL")

    for canonical, count in canonical_seen.items():
        if count != 1:
            errors.append(f"canonical appears in {count} provenance records: {canonical!r}")
    for term, locations in coverage.items():
        if len(locations) != 1:
            errors.append(f"term covered {len(locations)} times: {term!r} ({locations})")
    uncovered = sorted(set(glossary) - set(coverage), key=str.casefold)
    if uncovered:
        errors.append("uncovered glossary terms: " + ", ".join(uncovered))

    # A family may share a source, but its lexical evidence, naming argument and
    # rejected candidates may not be copy-pasted with only the headword changed.
    new_records = [record for record in records if record.get("origin") == "travelling_new"]
    for field in ("evidence", "rationale", "alternatives"):
        fingerprints: dict[str, list[str]] = defaultdict(list)
        for record in new_records:
            fingerprints[research_fingerprint(record, field, glossary)].append(
                str(record["canonical"])
            )
        for fingerprint, terms in fingerprints.items():
            if fingerprint and len(terms) > 1:
                errors.append(
                    f"new-term {field} is templated across {len(terms)} concepts: "
                    + ", ".join(sorted(terms, key=str.casefold))
                )
    return errors


def md(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def term_cell(record: dict[str, object], glossary: dict[str, dict[str, str]]) -> str:
    terms = [str(record["canonical"]), *[str(a) for a in record.get("aliases", [])]]
    pairs = []
    for term in terms:
        row = glossary[term]
        pairs.append(f"`{md(term)}` → {md(row['target_zh'])}")
    return "<br>".join(pairs)


def source_cell(record: dict[str, object]) -> str:
    label = md(record["reference_label"])
    url = md(record["reference_url"])
    return f"[{label}]({url})"


def reasoning_cell(record: dict[str, object]) -> str:
    reasoning = f"{md(record['evidence'])} {md(record['rationale'])}".strip()
    if record.get("comparison_url"):
        label = md(record["comparison_label"])
        url = md(record["comparison_url"])
        reasoning += f" 前作比较：[{label}]({url})。"
    if record.get("_audit_basis"):
        basis = AUDIT_BASIS_LABELS.get(str(record["_audit_basis"]), str(record["_audit_basis"]))
        confidence = {"fixed": "定译", "strong": "强证据", "editorial": "编辑定名"}.get(
            str(record.get("_audit_confidence", "")), str(record.get("_audit_confidence", ""))
        )
        reasoning += f" 终审依据：{basis}（{confidence}）。"
    return reasoning


def load_final_audit(
    path: Path, glossary: dict[str, dict[str, str]], records: list[dict[str, object]]
) -> tuple[list[dict[str, object]], list[str]]:
    audit = [
        json.loads(raw)
        for raw in path.read_text(encoding="utf-8-sig").splitlines()
        if raw
    ]
    errors = []
    by_term = {str(row.get("canonical")): row for row in audit}
    if len(audit) != 350 or len(by_term) != 350:
        errors.append(f"{path}: expected 350 unique historical verdicts, found {len(audit)}/{len(by_term)}")
    active = {str(record["canonical"]): record for record in records}
    for canonical, record in active.items():
        verdict = by_term.get(canonical)
        if verdict is None:
            errors.append(f"{path}: active concept lacks final verdict: {canonical}")
            continue
        if verdict.get("decision") == "retire":
            errors.append(f"{path}: retired concept remains active: {canonical}")
            continue
        target = glossary.get(canonical, {}).get("target_zh")
        if target != verdict.get("target_final"):
            errors.append(f"{path}: target drift for {canonical}: {target!r} != {verdict.get('target_final')!r}")
        record["_audit_basis"] = verdict.get("basis")
        record["_audit_confidence"] = verdict.get("confidence")
        record["_audit_decision"] = verdict.get("decision")
    for row in audit:
        canonical = str(row.get("canonical"))
        if row.get("decision") == "retire":
            if canonical in active or canonical in glossary:
                errors.append(f"{path}: retired concept still appears in active data: {canonical}")
        elif canonical not in active:
            errors.append(f"{path}: audited active concept missing provenance: {canonical}")
    return audit, errors


def load_quote_records(path: Path, strict: bool) -> tuple[list[dict[str, object]], list[str]]:
    records = []
    errors = []
    seen = set()
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_no, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            location = f"{path}:{line_no}"
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as exc:
                errors.append(f"{location}: {exc}")
                continue
            records.append(record)
            path_id = record.get("path_id")
            if not isinstance(path_id, int) or path_id in seen:
                errors.append(f"{location}: path_id must be a unique integer")
            seen.add(path_id)
            for key in ("source_en", "source_zh", "author_en", "author_zh", "kind", "reference_label", "reference_url", "evidence", "format_note"):
                if not nonempty(record, key):
                    errors.append(f"{location}: missing {key}")
            parsed = urlparse(str(record.get("reference_url", "")))
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                errors.append(f"{location}: reference_url must be an HTTP(S) URL")
            public_research = " ".join(
                str(record.get(key, ""))
                for key in ("reference_label", "evidence", "format_note")
            )
            stale = re.search(r"(?i)\bj\.\d+\b|暂译|本轮|润色期", public_research)
            if stale:
                errors.append(
                    f"{location}: quote research contains stale/internal marker {stale.group(0)!r}"
                )
            if strict and record.get("status") != "verified":
                errors.append(f"{location}: strict build requires status=verified")
    if len(records) != 23:
        errors.append(f"{path}: expected 23 quote records, found {len(records)}")
    return records, errors


def render_quotes(records: list[dict[str, object]]) -> list[str]:
    broad_counts = Counter(
        "诗歌／歌词" if "诗歌" in str(r["kind"]) or r["kind"] == "歌词"
        else "现实散文" if r["kind"] == "现实散文"
        else "秘史文献"
        for r in records
    )
    lines = [
        "## Quote 组件引文与诗歌出处",
        "",
        f"当前试玩版共核验 {len(records)} 个引文对象：诗歌／歌词 {broad_counts['诗歌／歌词']} 个、现实出版散文 {broad_counts['现实散文']} 个、秘史世界内文献 {broad_counts['秘史文献']} 个。它们并非全部出自诗句；仅对诗歌与歌词恢复原作分行，小说和设定散文保持段落体。",
        "",
        "| 游戏署名 | 体裁 | 外部出处 | 译名与排版核验 |",
        "|---|---|---|---|",
    ]
    for record in sorted(records, key=lambda row: int(row["path_id"])):
        work = f"`{md(record['source_en'])}` → {md(record['source_zh'])}<br>`{md(record['author_en'])}` → {md(record['author_zh'])}"
        source = f"[{md(record['reference_label'])}]({md(record['reference_url'])})"
        note = f"{md(record['evidence'])} {md(record['format_note'])}".strip()
        lines.append(f"| {work} | {md(record['kind'])} | {source} | {note} |")
    lines.append("")
    return lines


def load_conversation_descriptions(
    worklist: Path, translations_dir: Path
) -> dict[str, dict[str, str]]:
    translations = {}
    for path in sorted(translations_dir.glob("*.jsonl")):
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            if raw:
                row = json.loads(raw)
                translations[row["id"]] = row["translation"]
    result = {}
    pattern = re.compile(r"^conversations\.\[\d+\]\.fields\.\[\d+\]\.value$")
    for raw in worklist.read_text(encoding="utf-8-sig").splitlines():
        if not raw:
            continue
        row = json.loads(raw)
        for context in row.get("contexts", []):
            if (
                str(context.get("script", "")).split(",", 1)[0]
                == "PixelCrushers.DialogueSystem.Wrappers.DialogueDatabase"
                and context.get("field_title") == "Description"
                and pattern.fullmatch(str(context.get("field_path", "")))
            ):
                result[row["id"]] = {
                    "source": row["source"],
                    "translation": translations[row["id"]],
                    "conversation": str(context.get("conversation", "")),
                }
    return result


def load_conversation_description_records(
    path: Path, descriptions: dict[str, dict[str, str]], strict: bool
) -> tuple[list[dict[str, object]], list[str]]:
    records = []
    errors = []
    seen = set()
    for line_no, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not raw.strip():
            continue
        location = f"{path}:{line_no}"
        record = json.loads(raw)
        records.append(record)
        row_id = record.get("id")
        if not isinstance(row_id, str) or row_id in seen:
            errors.append(f"{location}: id must be a unique string")
        seen.add(row_id)
        if row_id not in descriptions:
            errors.append(f"{location}: id is not a conversation Description")
        for key in ("kind", "work", "author", "reference_label", "reference_url", "evidence", "status"):
            if not nonempty(record, key):
                errors.append(f"{location}: missing {key}")
        parsed = urlparse(str(record.get("reference_url", "")))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append(f"{location}: reference_url must be an HTTP(S) URL")
        public_research = " ".join(
            str(record.get(key, "")) for key in ("reference_label", "evidence")
        )
        stale = re.search(r"(?i)\bj\.\d+\b|暂译|本轮|润色期", public_research)
        if stale:
            errors.append(
                f"{location}: conversation research contains stale/internal marker {stale.group(0)!r}"
            )
        if strict and record.get("status") not in {"verified", "attribution_only", "no_external_source_found"}:
            errors.append(f"{location}: invalid review status")
    # There are 134 contexts but 133 unique string IDs: "Kepi Days" is reused
    # by the companion hub and the sanitarium conversation.
    if len(descriptions) != 133:
        errors.append(f"expected 133 unique conversation Description strings, found {len(descriptions)}")
    return records, errors


def render_conversation_descriptions(
    records: list[dict[str, object]], descriptions: dict[str, dict[str, str]]
) -> list[str]:
    statuses = Counter(str(record["status"]) for record in records)
    lines = [
        "## 会话题辞、互动场景名与出处",
        "",
        f"当前试玩版的 DialogueDatabase 共有 134 条会话级 `Description`。逐项复核其真实入边与显示用途后，为 {len(records)} 条有明确外部来源或需特别说明的题辞建立出处记录：可定位来源 {statuses['verified']} 条、仅能确认署名而未核得篇名 {statuses['attribution_only']} 条、精确检索后仍无外部文本见证 {statuses['no_external_source_found']} 条。其余条目属于内部机制／测试元数据、藏品题签、物品标签，或未发现可证外部来源的游戏原创与设定内题辞；不能仅因语言像诗就擅自署名。",
        "",
        "| 游戏题辞 → 本补丁译文 | 体裁判断 | 作品与作者 | 考据出处 | 核验说明 |",
        "|---|---|---|---|---|",
    ]
    for record in records:
        asset = descriptions[str(record["id"])]
        phrase = f"`{md(asset['source'])}` → {md(asset['translation'])}"
        work_author = f"{md(record['work'])}<br>{md(record['author'])}"
        reference = f"[{md(record['reference_label'])}]({md(record['reference_url'])})"
        note = f"{md(record['evidence'])} 状态：`{md(record['status'])}`。"
        lines.append(f"| {phrase} | {md(record['kind'])} | {work_author} | {reference} | {note} |")
    lines.append("")
    return lines


def render(
    glossary: dict[str, dict[str, str]],
    records: list[dict[str, object]],
    final_audit: list[dict[str, object]],
) -> str:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in records:
        grouped[str(record["origin"])].append(record)
    counts = {origin: len(grouped[origin]) for origin in ORIGIN_FILES}
    covered = sum(1 + len(record.get("aliases", [])) for record in records)
    audit_counts = Counter(str(row["decision"]) for row in final_audit)

    lines = [
        "# 《夜游漫记》简体中文术语与考据表",
        "",
        "> 本表随汉化补丁发布，面向玩家与后续审校者。英文大小写、单复数或词性异体按同一概念合并展示；内部 QA 仍逐项校验。译名不是 Weather Factory 的官方背书。",
        "",
        f"当前收录 {len(records)} 个概念，覆盖内部术语表 {covered}/{len(glossary)} 个精确词形：前作既有 {counts['predecessor']} 个、新作新增 {counts['travelling_new']} 个、现实实体 {counts['real_world']} 个、编辑裁决 {counts['editorial']} 个。",
        "",
        f"终审台账逐项覆盖 350 个历史概念：保留 {audit_counts['keep']} 个、改译 {audit_counts['change']} 个、从当前资产退役 {audit_counts['retire']} 个。‘编辑定名’表示证据足以作出项目终稿选择，但不冒充官方唯一译名。",
        "",
        "证据优先级：本地 Demo 英文原文与界面上下文 → 同作官方页面/Steam 简中 → 前作官方简中与中文 Wiki → 开发者文章 → 其他权威或专业资料。‘暂定’条目不得用于最终严格构建。",
        "",
    ]

    for origin in ORIGIN_FILES:
        lines.extend([f"## {ORIGIN_TITLES[origin]}", ""])
        if origin == "predecessor":
            lines.extend(
                [
                    "每一项均链接对应的中文 Wiki 词条或包含该专名的专题条目；译名沿用前作时不另造新词。",
                    "",
                    "| 英文 → 本补丁译名 | 类别 | Wiki 词条 | 沿用依据与说明 |",
                    "|---|---|---|---|",
                ]
            )
            for record in sorted(grouped[origin], key=lambda r: str(r["canonical"]).casefold()):
                category = glossary[str(record["canonical"])]["type"]
                note = reasoning_cell(record)
                lines.append(
                    f"| {term_cell(record, glossary)} | {md(category)} | {source_cell(record)} | {note} |"
                )
        elif origin == "travelling_new":
            lines.extend(
                [
                    "这些条目在本作中新增或获得新的机制义。‘命名理由’同时列出曾考虑但未采用的译法，避免以后无证据回改。",
                    "",
                    "| 英文 → 本补丁译名 | 类别 | 主证据 | 考据与命名理由 | 未采用译法 | 状态 |",
                    "|---|---|---|---|---|---|",
                ]
            )
            for record in sorted(grouped[origin], key=lambda r: str(r["canonical"]).casefold()):
                category = glossary[str(record["canonical"])]["type"]
                reasoning = reasoning_cell(record)
                lines.append(
                    f"| {term_cell(record, glossary)} | {md(category)} | {source_cell(record)} | {reasoning} | {md(record['alternatives'])} | {md(record['status'])} |"
                )
        else:
            heading = "考据与译名理由" if origin == "real_world" else "裁决理由"
            lines.extend(
                [
                    f"| 英文 → 本补丁译名 | 类别 | 参考 | {heading} | 状态 |",
                    "|---|---|---|---|---|",
                ]
            )
            for record in sorted(grouped[origin], key=lambda r: str(r["canonical"]).casefold()):
                category = glossary[str(record["canonical"])]["type"]
                reasoning = reasoning_cell(record)
                lines.append(
                    f"| {term_cell(record, glossary)} | {md(category)} | {source_cell(record)} | {reasoning} | {md(record['status'])} |"
                )
        lines.append("")

    lines.extend(
        [
            "## 终审退役词项",
            "",
            "以下词项曾在旧构建或早期方案中出现，但当前试玩版已不再使用，故移出活动术语表与运行时 QA：",
            "",
            "| 英文 | 旧译 | 退役理由 |",
            "|---|---|---|",
            *[
                f"| `{md(row['canonical'])}` | {md(row['target_before'])} | {md(row['audit_note'])} |"
                for row in final_audit
                if row.get("decision") == "retire"
            ],
            "",
            "## 维护规则",
            "",
            "- 修改 `glossary/glossary.csv` 时，必须同步更新 `glossary/provenance/` 中且只能有一条覆盖记录。",
            "- 前作既有术语必须提供可访问的灰机 Wiki 词条；新作术语必须写明主证据、构词理由和排除候选。",
            "- `glossary/quote_provenance.jsonl` 必须逐一覆盖 23 个互动引文对象；诗歌按出处复核分行，散文不得为了形式感擅自拆成诗行。",
            "- `glossary/conversation_description_provenance.jsonl` 记录 DialogueDatabase 会话题辞的外部出处与反证；不得把检索无据的题辞伪造为诗句。",
            "- 最终发布只接受 `verified`；`provisional` 与 `draft` 会令严格构建失败。",
            "- `glossary/final_term_audit.jsonl` 必须为每个历史概念保留唯一终审结论；活动词的最终译名和别名必须与 glossary/provenance 精确一致。",
            "- 本表记录译名证据，不复制 Wiki 或游戏长文；链接内容的版权归各自权利人。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    glossary = load_glossary(args.glossary)
    records = load_records(args.provenance_dir)
    errors = validate(glossary, records, args.strict)
    final_audit, audit_errors = load_final_audit(args.final_audit, glossary, records)
    errors.extend(audit_errors)
    quote_records, quote_errors = load_quote_records(args.quote_provenance, args.strict)
    errors.extend(quote_errors)
    descriptions = load_conversation_descriptions(args.worklist, args.translations)
    description_records, description_errors = load_conversation_description_records(
        args.conversation_description_provenance, descriptions, args.strict
    )
    errors.extend(description_errors)
    if errors:
        print(f"FAIL: {len(errors)} terminology provenance error(s)")
        for error in errors:
            print(f"- {error}")
        return 1
    output = render(glossary, records, final_audit)
    marker = "## 维护规则\n"
    extra = render_quotes(quote_records) + render_conversation_descriptions(
        description_records, descriptions
    )
    output = output.replace(marker, "\n".join(extra) + "\n" + marker)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8", newline="\n")
    print(
        f"PASS: {len(records)} concepts cover {len(glossary)} exact glossary terms; "
        f"{len(quote_records)} quote records; {len(description_records)}/134 conversation-description source records; wrote {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
