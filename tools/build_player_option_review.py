#!/usr/bin/env python3
"""Build a graph-aware review worklist for player dialogue options.

The Pixel Crushers database stores the visible choice on the destination
player node.  A non-empty ``Menu Text`` wins; otherwise ``Dialogue Text`` is
shown.  This tool follows the authored links instead of assuming that adjacent
database rows are related, and joins every visible string to the current
translation chunks without modifying them.
"""

from __future__ import annotations

import argparse
import collections
import csv
import html
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


PLAYER_ACTOR_ID = 1
TAG_RE = re.compile(r"<[^<>]+>")
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
WORD_RE = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?")
TRANSLATABLE_RE = re.compile(r"[A-Za-z\u3400-\u4dbf\u4e00-\u9fff]")
GENERIC_CHOICE_RE = re.compile(
    r"\b(?:back|continue|done|go|leave|no|nothing|return|stay|stop|wait|yes)\b",
    re.IGNORECASE,
)


class ReviewInputError(RuntimeError):
    """Raised when an input cannot produce a reliable review report."""


@dataclass(frozen=True)
class TranslationMatch:
    translation: str
    ids: tuple[str, ...]
    statuses: tuple[str, ...]
    missing: bool
    ambiguous: bool


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a true-graph player-option translation review report."
    )
    parser.add_argument("graph", type=Path, help="dialogue_context_*_graph.json")
    parser.add_argument(
        "translations",
        type=Path,
        help="directory containing the authoritative chunk_*.jsonl files",
    )
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path)
    parser.add_argument("--max-console", type=int, default=20)
    return parser.parse_args(argv)


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReviewInputError(f"cannot read graph {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("databases"), list):
        raise ReviewInputError("graph root must contain a 'databases' list")
    return data


def read_translation_rows(directory: Path) -> list[dict[str, Any]]:
    paths = sorted(directory.glob("chunk_*.jsonl"))
    if not paths:
        raise ReviewInputError(f"no chunk_*.jsonl files found in {directory}")
    rows: list[dict[str, Any]] = []
    seen_ids: dict[str, tuple[Path, int]] = {}
    for path in paths:
        try:
            with path.open(encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ReviewInputError(
                            f"{path}:{line_number}: translation row is not an object"
                        )
                    missing = [
                        field
                        for field in ("id", "source", "translation")
                        if field not in row
                    ]
                    if missing:
                        raise ReviewInputError(
                            f"{path}:{line_number}: missing {', '.join(missing)}"
                        )
                    row_id = str(row["id"])
                    if row_id in seen_ids:
                        first_path, first_line = seen_ids[row_id]
                        raise ReviewInputError(
                            f"duplicate translation id {row_id}: "
                            f"{first_path}:{first_line} and {path}:{line_number}"
                        )
                    seen_ids[row_id] = (path, line_number)
                    rows.append(row)
        except ReviewInputError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ReviewInputError(f"cannot read {path}: {exc}") from exc
    return rows


def build_translation_index(
    rows: Iterable[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        index[str(row["source"])].append(row)
    return dict(index)


def translation_match(
    source: str, index: dict[str, list[dict[str, Any]]]
) -> TranslationMatch:
    if not source:
        return TranslationMatch("", (), (), True, False)
    rows = index.get(source, [])
    if not rows:
        return TranslationMatch("", (), (), True, False)
    translations = tuple(dict.fromkeys(str(row.get("translation", "")) for row in rows))
    ids = tuple(str(row.get("id", "")) for row in rows)
    statuses = tuple(dict.fromkeys(str(row.get("status", "")) for row in rows))
    return TranslationMatch(
        translation=translations[0],
        ids=ids,
        statuses=statuses,
        missing=not translations[0].strip(),
        ambiguous=len(translations) > 1,
    )


def actor_payload(database: dict[str, Any], actor_id: int) -> dict[str, Any]:
    actor = (database.get("actors") or {}).get(str(actor_id), {})
    return {
        "id": actor_id,
        "name": str(actor.get("name", "")),
        "display_name": str(actor.get("display_name", "")),
    }


def visible_choice(entry: dict[str, Any]) -> tuple[str, str]:
    menu_text = str(entry.get("menu_text", ""))
    if menu_text.strip():
        return "menu_text", menu_text
    return "dialogue_text", str(entry.get("dialogue_text", ""))


def visible_text(value: str) -> str:
    value = html.unescape(value)
    value = WIKILINK_RE.sub(lambda match: match.group(1), value)
    return TAG_RE.sub("", value)


def translation_payload(
    source: str, translation_index: dict[str, list[dict[str, Any]]]
) -> dict[str, Any]:
    match = translation_match(source, translation_index)
    return {
        "source": source,
        "translation": match.translation,
        "translation_ids": list(match.ids),
        "translation_statuses": list(match.statuses),
        "translation_required": bool(TRANSLATABLE_RE.search(visible_text(source))),
        "translation_missing": match.missing,
        "translation_ambiguous": match.ambiguous,
    }


def entry_payload(
    database: dict[str, Any],
    conversation: dict[str, Any],
    entry: dict[str, Any],
    translation_index: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    field, source = visible_choice(entry)
    return {
        "conversation_id": int(conversation.get("id", 0)),
        "conversation_title": str(conversation.get("title", "")),
        "entry_id": int(entry.get("id", 0)),
        "entry_index": int(entry.get("entry_index", 0)),
        "actor": actor_payload(database, int(entry.get("actor_id", 0))),
        "conversant": actor_payload(database, int(entry.get("conversant_id", 0))),
        "selected_text_field": field,
        "text": translation_payload(source, translation_index),
        "conditions": str(entry.get("conditions", "")),
    }


def resolve_link_destination(
    link: dict[str, Any],
    entries: dict[tuple[int, int], tuple[dict[str, Any], dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    key = (
        int(link.get("destination_conversation_id", 0)),
        int(link.get("destination_dialogue_id", 0)),
    )
    return entries.get(key)


def risk_assessment(
    option: dict[str, Any],
    duplicate_source_count: int,
    unresolved_successors: int,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    source = str(option["option"]["source"])
    cleaned = visible_text(source).strip()
    words = WORD_RE.findall(cleaned)

    def add(points: int, reason: str) -> None:
        nonlocal score
        score += points
        reasons.append(reason)

    if not cleaned:
        add(20, "empty_control_node")
    elif (
        option["option"]["translation_required"]
        and option["option"]["translation_missing"]
    ):
        add(80, "missing_translation")
    elif option["option"]["translation_missing"]:
        reasons.append("nonlinguistic_passthrough")
    if option["option"]["translation_ambiguous"]:
        add(50, "ambiguous_translation_lookup")
    if unresolved_successors:
        add(40, "unresolved_successor_link")
    if option["selected_text_field"] == "menu_text":
        add(10, "menu_text_override")
        dialogue_source = str(option["dialogue_text"]["source"])
        if dialogue_source.strip() and dialogue_source != source:
            add(15, "menu_and_dialogue_differ")
    if cleaned and GENERIC_CHOICE_RE.search(cleaned):
        add(35, "generic_direction_or_confirmation")
    if cleaned and (len(words) <= 2 or len(cleaned) <= 12):
        add(15, "very_short_option")
    parent_count = len(option["parents"])
    if parent_count > 1:
        add(min(25, 8 + parent_count * 2), "multiple_parent_contexts")
    parent_texts = {
        str(parent["text"]["source"]).strip()
        for parent in option["parents"]
        if str(parent["text"]["source"]).strip()
    }
    if len(parent_texts) > 1:
        add(10, "divergent_parent_lines")
    parent_conversations = {
        (parent["conversation_id"], parent["conversation_title"])
        for parent in option["parents"]
    }
    if len(parent_conversations) > 1:
        add(15, "cross_conversation_reuse")
    if duplicate_source_count > 1:
        add(min(25, 8 + duplicate_source_count), "duplicate_option_source")
    if str(option["conditions"]).strip():
        add(5, "conditional_option")
    if len(option["successors"]) > 1:
        add(8, "multiple_successors")
    return score, reasons


def build_report(
    graph_path: Path,
    translation_path: Path,
    graph: dict[str, Any],
    translation_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    translation_index = build_translation_index(translation_rows)
    pending: list[dict[str, Any]] = []
    unresolved_links = 0

    for database_number, database in enumerate(graph["databases"]):
        conversations = database.get("conversations") or []
        entries: dict[
            tuple[int, int], tuple[dict[str, Any], dict[str, Any]]
        ] = {}
        for conversation in conversations:
            conversation_id = int(conversation.get("id", 0))
            for entry in conversation.get("entries") or []:
                key = (conversation_id, int(entry.get("id", 0)))
                if key in entries:
                    raise ReviewInputError(
                        f"database {database_number} has duplicate entry key {key}"
                    )
                entries[key] = (conversation, entry)

        incoming: dict[
            tuple[int, int], list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]
        ] = collections.defaultdict(list)
        for conversation in conversations:
            for entry in conversation.get("entries") or []:
                for link in entry.get("outgoing_links") or []:
                    destination = resolve_link_destination(link, entries)
                    if destination is None:
                        unresolved_links += 1
                        continue
                    destination_conversation, destination_entry = destination
                    if int(destination_entry.get("actor_id", 0)) != PLAYER_ACTOR_ID:
                        continue
                    destination_key = (
                        int(destination_conversation.get("id", 0)),
                        int(destination_entry.get("id", 0)),
                    )
                    incoming[destination_key].append((conversation, entry, link))

        for key, parent_links in incoming.items():
            conversation, entry = entries[key]
            selected_text_field, option_source = visible_choice(entry)
            parents = [
                {
                    **entry_payload(
                        database,
                        parent_conversation,
                        parent_entry,
                        translation_index,
                    ),
                    "is_connector": bool(link.get("is_connector", False)),
                }
                for parent_conversation, parent_entry, link in parent_links
            ]
            successors: list[dict[str, Any]] = []
            unresolved_successors = 0
            for link in entry.get("outgoing_links") or []:
                destination = resolve_link_destination(link, entries)
                if destination is None:
                    unresolved_successors += 1
                    continue
                successor_conversation, successor_entry = destination
                successors.append(
                    {
                        **entry_payload(
                            database,
                            successor_conversation,
                            successor_entry,
                            translation_index,
                        ),
                        "is_connector": bool(link.get("is_connector", False)),
                    }
                )
            pending.append(
                {
                    "database_index": database_number,
                    "asset_file": str(database.get("asset_file", "")),
                    "database_path_id": int(database.get("path_id", 0)),
                    "conversation_id": int(conversation.get("id", 0)),
                    "conversation_index": int(conversation.get("conversation_index", 0)),
                    "conversation_title": str(conversation.get("title", "")),
                    "conversation_description": str(
                        conversation.get("description", "")
                    ),
                    "entry_id": int(entry.get("id", 0)),
                    "entry_index": int(entry.get("entry_index", 0)),
                    "actor": actor_payload(
                        database, int(entry.get("actor_id", 0))
                    ),
                    "conversant": actor_payload(
                        database, int(entry.get("conversant_id", 0))
                    ),
                    "selected_text_field": selected_text_field,
                    "option": translation_payload(option_source, translation_index),
                    "menu_text": translation_payload(
                        str(entry.get("menu_text", "")), translation_index
                    ),
                    "dialogue_text": translation_payload(
                        str(entry.get("dialogue_text", "")), translation_index
                    ),
                    "conditions": str(entry.get("conditions", "")),
                    "parents": parents,
                    "successors": successors,
                    "unresolved_successor_links": unresolved_successors,
                }
            )

    duplicate_counts = collections.Counter(
        str(option["option"]["source"]) for option in pending if option["option"]["source"]
    )
    for option in pending:
        duplicate_count = duplicate_counts[str(option["option"]["source"])]
        score, reasons = risk_assessment(
            option, duplicate_count, int(option["unresolved_successor_links"])
        )
        option["duplicate_option_source_nodes"] = duplicate_count
        option["risk_score"] = score
        option["risk_reasons"] = reasons

    pending.sort(
        key=lambda option: (
            -int(option["risk_score"]),
            str(option["conversation_title"]),
            int(option["entry_id"]),
        )
    )
    for rank, option in enumerate(pending, 1):
        option["review_rank"] = rank

    reason_counts = collections.Counter(
        reason for option in pending for reason in option["risk_reasons"]
    )
    summary = {
        "databases": len(graph["databases"]),
        "translation_rows": len(translation_rows),
        "player_option_nodes": len(pending),
        "player_option_parent_edges": sum(len(item["parents"]) for item in pending),
        "player_option_successor_edges": sum(
            len(item["successors"]) for item in pending
        ),
        "menu_text_options": sum(
            item["selected_text_field"] == "menu_text" for item in pending
        ),
        "empty_visible_options": sum(
            not str(item["option"]["source"]).strip() for item in pending
        ),
        "missing_option_translations": sum(
            bool(item["option"]["translation_required"])
            and bool(item["option"]["translation_missing"])
            for item in pending
        ),
        "nonlinguistic_passthrough_options": sum(
            not bool(item["option"]["translation_required"])
            and bool(str(item["option"]["source"]).strip())
            for item in pending
        ),
        "ambiguous_option_translations": sum(
            bool(item["option"]["translation_ambiguous"]) for item in pending
        ),
        "unresolved_graph_links": unresolved_links,
        "unresolved_option_successor_links": sum(
            int(item["unresolved_successor_links"]) for item in pending
        ),
        "risk_reasons": dict(sorted(reason_counts.items())),
    }
    return {
        "tool": "build_player_option_review.py",
        "schema_version": 1,
        "inputs": {
            "graph": str(graph_path.resolve()),
            "translations": str(translation_path.resolve()),
        },
        "summary": summary,
        "options": pending,
    }


def compact(value: str, limit: int = 90) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def flatten_nodes(nodes: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for node in nodes:
        actor = node.get("actor") or {}
        speaker = actor.get("display_name") or actor.get("name") or actor.get("id")
        text = node.get("text") or {}
        source = compact(str(text.get("source", "")), 140)
        translation = compact(str(text.get("translation", "")), 140)
        conditions = compact(str(node.get("conditions", "")), 100)
        parts.append(
            f"{node.get('conversation_id')}:{node.get('entry_id')} "
            f"[{speaker}] EN={source} | ZH={translation} | IF={conditions}"
        )
    return " || ".join(parts)


def write_csv(path: Path, options: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = (
        "review_rank",
        "risk_score",
        "risk_reasons",
        "conversation_id",
        "conversation_title",
        "entry_id",
        "selected_text_field",
        "option_source",
        "option_translation",
        "translation_ids",
        "conditions",
        "parent_count",
        "parents",
        "successor_count",
        "successors",
    )
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for option in options:
            writer.writerow(
                {
                    "review_rank": option["review_rank"],
                    "risk_score": option["risk_score"],
                    "risk_reasons": ";".join(option["risk_reasons"]),
                    "conversation_id": option["conversation_id"],
                    "conversation_title": option["conversation_title"],
                    "entry_id": option["entry_id"],
                    "selected_text_field": option["selected_text_field"],
                    "option_source": option["option"]["source"],
                    "option_translation": option["option"]["translation"],
                    "translation_ids": ";".join(
                        option["option"]["translation_ids"]
                    ),
                    "conditions": option["conditions"],
                    "parent_count": len(option["parents"]),
                    "parents": flatten_nodes(option["parents"]),
                    "successor_count": len(option["successors"]),
                    "successors": flatten_nodes(option["successors"]),
                }
            )


def print_report(report: dict[str, Any], max_console: int) -> None:
    summary = report["summary"]
    print("Player option graph review")
    print(f"Graph:        {report['inputs']['graph']}")
    print(f"Translations: {report['inputs']['translations']}")
    print(
        "Options: {player_option_nodes} | Parent edges: "
        "{player_option_parent_edges} | Successor edges: "
        "{player_option_successor_edges}".format(**summary)
    )
    print(
        "Menu Text: {menu_text_options} | Empty: {empty_visible_options} | "
        "Missing translations: {missing_option_translations} | "
        "Nonlinguistic passthrough: {nonlinguistic_passthrough_options} | "
        "Ambiguous: {ambiguous_option_translations}".format(**summary)
    )
    print("Risk reasons:")
    for reason, count in summary["risk_reasons"].items():
        print(f"  {reason}: {count}")
    if max_console > 0:
        print("Highest-risk options:")
    for option in report["options"][:max_console]:
        print(
            f"  #{option['review_rank']} score={option['risk_score']} "
            f"{option['conversation_title']} {option['conversation_id']}:"
            f"{option['entry_id']} {compact(option['option']['source'])}"
        )
        print(f"    ZH: {compact(option['option']['translation'])}")
        print(f"    Why: {', '.join(option['risk_reasons']) or '-'}")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        graph = read_json(args.graph)
        translation_rows = read_translation_rows(args.translations)
        report = build_report(args.graph, args.translations, graph, translation_rows)
        output_path = args.json_output.resolve()
        if output_path == args.graph.resolve():
            raise ReviewInputError("refusing to overwrite the input graph")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        if args.csv_output:
            write_csv(args.csv_output, report["options"])
    except (ReviewInputError, OSError) as exc:
        print(f"player option review error: {exc}", file=sys.stderr)
        return 2

    print_report(report, args.max_console)
    print(f"JSON report: {args.json_output.resolve()}")
    if args.csv_output:
        print(f"CSV worklist: {args.csv_output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
