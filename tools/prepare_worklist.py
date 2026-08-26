#!/usr/bin/env python3
"""Turn the raw Unity string inventory into a context-rich translation worklist."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


DIALOGUE_SCRIPT = "PixelCrushers.DialogueSystem.Wrappers.DialogueDatabase"
FIELD_RE = re.compile(r"(.+\.fields\.\[\d+\])\.(title|typeString|value)$")
ENTRY_ROOT_RE = re.compile(r"conversations\.\[(\d+)\]\.dialogueEntries\.\[(\d+)\]")
CONVERSATION_ROOT_RE = re.compile(r"conversations\.\[(\d+)\]")
ACTOR_ROOT_RE = re.compile(r"actors\.\[(\d+)\]")
WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z'’-]*\b")
INDEX_RE = re.compile(r"\[\d+\]")

DIALOGUE_VALUE_FIELDS = {
    "Dialogue Text",
    "Menu Text",
    "Display Name",
    "WhenUnlockedOverride",
    "WhenLockedOverride",
    "Success Description",
    "Failure Description",
    "Response Menu Sequence",
}

LEAF_FIELDS = {
    "m_Script",
    "m_text",
    "m_Text",
    "_label",
    "label",
    "Label",
    "_description",
    "description",
    "Description",
    "_listingName",
    "_displayName",
    "displayName",
    "_tutorialText",
    "_content",
    "_author",
    "_source",
    "_note",
    "_customEntryMessage",
    "_customExitMessage",
    "_changeMessage",
    "changeMessage",
    "ChangeMessage",
    "text",
    # j.87 补漏：仪式建议、职业引导语、地名词、轴友好标签等（v2.0.3）
    "_advice",
    "friendlyText",
    "_overrideJournalDescription",
    "_introLabel",
    "_mapLabel",
    "emptinessPassionsLabel",
    # l.8 补漏：可计数物品的复数标签，用于需求/数量注解（"[5 Francisques]"）。
    # 此前从未入单——k.98 起的需求文案与 l.x 的价格注解才开始消费 _plural。
    "_plural",
}

EXCLUDED_PATH_PARTS = {
    "m_PersistentCalls",
    "m_AnimationTriggers",
    "m_ActionMaps",
    "spriteInfoList",
    "m_FaceInfo",
    "m_AtlasTextures",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("inventory", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--chunk-size", type=int, default=450)
    parser.add_argument("--dialogue-context", type=Path)
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def visible_text(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    if not re.search(r"[A-Za-z]", text):
        return False
    return True


def build_dialogue_fields(rows: list[dict[str, Any]]) -> dict[tuple[str, int, str], dict[str, str]]:
    groups: dict[tuple[str, int, str], dict[str, str]] = {}
    for row in rows:
        if not row["script"].startswith(DIALOGUE_SCRIPT):
            continue
        match = FIELD_RE.fullmatch(row["field_path"])
        if not match:
            continue
        key = (row["asset_file"], row["path_id"], match.group(1))
        groups.setdefault(key, {})[match.group(2)] = row["source"]
    return groups


def load_dialogue_context(path: Path | None) -> dict[tuple[str, int], dict[str, Any]]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        (database["asset_file"], int(database["path_id"])): database
        for database in payload.get("databases", [])
    }


def dialogue_contexts(
    rows: list[dict[str, Any]], database_contexts: dict[tuple[str, int], dict[str, Any]]
) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    groups = build_dialogue_fields(rows)

    records: dict[tuple[str, int, str], dict[str, str]] = collections.defaultdict(dict)
    conversation_titles: dict[tuple[str, int, int], str] = {}
    actor_names: dict[tuple[str, int, int], str] = {}
    database_entries: dict[tuple[str, int, int, int], dict[str, Any]] = {}
    for (asset_file, path_id), database in database_contexts.items():
        for actor_id, actor in database.get("actors", {}).items():
            actor_names[(asset_file, path_id, int(actor_id))] = actor.get("display_name") or actor.get("name", "")
        for conversation in database.get("conversations", []):
            conversation_index = int(conversation["conversation_index"])
            conversation_titles[(asset_file, path_id, conversation_index)] = conversation.get("title", "")
            for entry in conversation.get("entries", []):
                database_entries[
                    (asset_file, path_id, conversation_index, int(entry["entry_index"]))
                ] = entry
    for (asset_file, path_id, root), field in groups.items():
        record_root = root.split(".fields.", 1)[0]
        if field.get("title"):
            records[(asset_file, path_id, record_root)][field["title"]] = field.get("value", "")
        conv_match = CONVERSATION_ROOT_RE.fullmatch(record_root)
        if conv_match and field.get("title") == "Title":
            conversation_titles[(asset_file, path_id, int(conv_match.group(1)))] = field.get("value", "")
        actor_match = ACTOR_ROOT_RE.fullmatch(record_root)
        if not database_contexts and actor_match and field.get("title") == "Display Name":
            actor_names[(asset_file, path_id, int(actor_match.group(1)) + 1)] = field.get("value", "")

    dialogue_by_conversation: dict[tuple[str, int, int], list[tuple[int, str]]] = collections.defaultdict(list)
    for (asset_file, path_id, record_root), record in records.items():
        match = ENTRY_ROOT_RE.fullmatch(record_root)
        if match and record.get("Dialogue Text", "").strip():
            dialogue_by_conversation[(asset_file, path_id, int(match.group(1)))].append(
                (int(match.group(2)), record["Dialogue Text"])
            )
    for values in dialogue_by_conversation.values():
        values.sort(key=lambda item: item[0])

    for (asset_file, path_id, root), field in groups.items():
        title = field.get("title", "")
        value = field.get("value", "")
        if not visible_text(value):
            continue
        include = title in DIALOGUE_VALUE_FIELDS
        record_root = root.split(".fields.", 1)[0]
        conversation_description = (
            title == "Description" and CONVERSATION_ROOT_RE.fullmatch(record_root) is not None
        )
        # Conversation Description is the player-visible interaction title in
        # TravellingDialogueUI (for example stationCar -> “They Also Serve”).
        # Omitting it leaves every scene interaction heading in English even
        # though the runtime patch can already mutate Description fields.
        if title == "Description" and (
            root.startswith(("actors.", "items.")) or conversation_description
        ):
            include = True
        if re.fullmatch(r"SkillCheckModifier_\d+_Description", title):
            include = True
        if not include:
            continue
        domain = "dialogue"
        if root.startswith(("actors.", "items.")) or title != "Dialogue Text":
            domain = "dialogue_ui"
        context: dict[str, Any] = {
            "asset_file": asset_file,
            "path_id": path_id,
            "game_object": "",
            "script": DIALOGUE_SCRIPT,
            "field_path": f"{root}.value",
            "field_title": title,
            "domain": domain,
            "source": value,
        }
        entry_match = ENTRY_ROOT_RE.fullmatch(record_root)
        if entry_match:
            conversation_index = int(entry_match.group(1))
            entry_index = int(entry_match.group(2))
            record = records.get((asset_file, path_id, record_root), {})
            database_entry = database_entries.get(
                (asset_file, path_id, conversation_index, entry_index), {}
            )
            try:
                actor_id = int(database_entry.get("actor_id", record.get("Actor", "0")))
            except ValueError:
                actor_id = 0
            try:
                conversant_id = int(database_entry.get("conversant_id", record.get("Conversant", "0")))
            except ValueError:
                conversant_id = 0
            sequence = dialogue_by_conversation.get((asset_file, path_id, conversation_index), [])
            position = next((i for i, pair in enumerate(sequence) if pair[0] == entry_index), -1)
            context.update(
                {
                    "conversation": conversation_titles.get((asset_file, path_id, conversation_index), ""),
                    "entry_index": entry_index,
                    "speaker": actor_names.get((asset_file, path_id, actor_id), f"Actor {actor_id}"),
                    "conversant": actor_names.get((asset_file, path_id, conversant_id), f"Actor {conversant_id}"),
                    "previous_text": sequence[position - 1][1] if position > 0 else "",
                    "next_text": sequence[position + 1][1] if 0 <= position < len(sequence) - 1 else "",
                }
            )
        else:
            conversation_match = CONVERSATION_ROOT_RE.fullmatch(record_root)
            if conversation_match:
                context["conversation"] = conversation_titles.get(
                    (asset_file, path_id, int(conversation_match.group(1))), ""
                )
        contexts.append(context)
    return contexts


def infer_domain(row: dict[str, Any]) -> str:
    script = row["script"]
    path = row["field_path"]
    if "MusicTrackLibrary" in script and path.rsplit(".", 1)[-1] in {
        "DisplayName",
        "ArtistName",
    }:
        return "ui"
    if script == "UnityEngine.TextAsset":
        return "ui"
    if "Footnote" in script:
        return "footnotes"
    if script.endswith("LocData, travelling.scripts"):
        return "ui"
    if script.startswith(("TMPro.", "UnityEngine.UI.")):
        return "ui"
    if any(token in script for token in ("Item", "Recipe", "Quality", "Aspect", "Destination", "StateSO")):
        return "game_data"
    if "Quote" in script:
        return "lore"
    if "Tutorial" in script or "HUD" in script or ".UI." in script:
        return "ui"
    if path.startswith("entries."):
        return "ui"
    return "misc"


def ordinary_contexts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for row in rows:
        if row["script"].startswith(DIALOGUE_SCRIPT):
            continue
        if row["script"] == "UnityEngine.TextAsset" and row["game_object"] != "patch-notes":
            # Spine atlas/skeleton and performance-test JSON files are also
            # TextAssets, but are machine data rather than player-visible text.
            continue
        if not row["candidate"] or not visible_text(row["source"]):
            continue
        path = row["field_path"]
        if any(part in path for part in EXCLUDED_PATH_PARTS):
            continue
        leaf = path.rsplit(".", 1)[-1]
        normalized = INDEX_RE.sub("[]", path)
        include = leaf in LEAF_FIELDS
        include = include or (
            "MusicTrackLibrary" in row["script"]
            and leaf in {"DisplayName", "ArtistName"}
        )
        include = include or normalized.endswith("Choices.[].label")
        include = include or normalized.endswith("Choices.[].description")
        include = include or normalized.endswith("_overrideAlertMessages.[]")
        include = include or normalized.endswith("entries.[].value")
        include = include or normalized.endswith("_tips.[]._label")
        include = include or normalized.endswith("_tips.[]._description")
        include = include or normalized.endswith("_transitionsOut.[].text")
        include = include or normalized.endswith("QReqs.[].text")
        if not include:
            continue
        context = {
            "asset_file": row["asset_file"],
            "path_id": row["path_id"],
            "game_object": row["game_object"],
            "script": row["script"],
            "field_path": path,
            "field_title": "",
            "domain": infer_domain(row),
            "source": row["source"],
        }
        contexts.append(context)
    return contexts


def stable_id(source: str) -> str:
    return "TAN-" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:12].upper()


def deduplicate(contexts: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for context in contexts:
        grouped[context["source"]].append(context)

    entries: list[dict[str, Any]] = []
    domain_order = {"dialogue": 0, "dialogue_ui": 1, "footnotes": 2, "lore": 3, "game_data": 4, "ui": 5, "misc": 6}
    for source, source_contexts in grouped.items():
        domains = sorted({item["domain"] for item in source_contexts}, key=lambda d: domain_order.get(d, 99))
        entries.append(
            {
                "id": stable_id(source),
                "domain": domains[0],
                "all_domains": domains,
                "source": source,
                "translation": "",
                "status": "untranslated",
                "notes": "",
                "contexts": source_contexts,
            }
        )

    entries.sort(key=lambda item: (domain_order.get(item["domain"], 99), item["id"]))
    return entries


def write_jsonl(path: Path, entries: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> int:
    args = parse_args()
    rows = read_jsonl(args.inventory)
    database_contexts = load_dialogue_context(args.dialogue_context)
    contexts = dialogue_contexts(rows, database_contexts) + ordinary_contexts(rows)
    entries = deduplicate(contexts)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    chunk_dir = args.output_dir / "chunks"
    chunk_dir.mkdir(exist_ok=True)

    write_jsonl(args.output_dir / "worklist.jsonl", entries)
    for old_chunk in chunk_dir.glob("chunk_*.jsonl"):
        old_chunk.unlink()
    for index in range(0, len(entries), args.chunk_size):
        chunk = entries[index : index + args.chunk_size]
        write_jsonl(chunk_dir / f"chunk_{index // args.chunk_size + 1:03d}.jsonl", chunk)

    summary: dict[str, dict[str, int]] = collections.defaultdict(lambda: {"entries": 0, "words": 0})
    for entry in entries:
        summary[entry["domain"]]["entries"] += 1
        summary[entry["domain"]]["words"] += len(WORD_RE.findall(entry["source"]))
    report = {
        "entries": len(entries),
        "source_words": sum(len(WORD_RE.findall(entry["source"])) for entry in entries),
        "contexts": len(contexts),
        "domains": dict(summary),
        "chunks": (len(entries) + args.chunk_size - 1) // args.chunk_size,
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
