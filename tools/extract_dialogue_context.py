#!/usr/bin/env python3
"""Extract Pixel Crushers dialogue speaker and neighbourhood metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator

from extract_unity_text import find_data_dir


DIALOGUE_SCRIPT = "PixelCrushers.DialogueSystem.Wrappers.DialogueDatabase"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("game_root", type=Path)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("output", type=Path)
    return parser.parse_args()


def database_objects(inventory: Path) -> set[tuple[str, int]]:
    result: set[tuple[str, int]] = set()
    with inventory.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("script", "").startswith(DIALOGUE_SCRIPT):
                result.add((row["asset_file"], int(row["path_id"])))
    return result


def field_map(record: dict[str, Any]) -> dict[str, str]:
    return {
        field.get("title", ""): field.get("value", "")
        for field in record.get("fields", [])
        if field.get("title")
    }


def int_member(record: dict[str, Any], *names: str) -> int:
    for name in names:
        value = record.get(name)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    return 0


def extract_database(tree: dict[str, Any]) -> dict[str, Any]:
    actors: dict[str, dict[str, str]] = {}
    for actor in tree.get("actors", []):
        fields = field_map(actor)
        actors[str(actor.get("id", 0))] = {
            "name": fields.get("Name", ""),
            "display_name": fields.get("Display Name", ""),
            "description": fields.get("Description", ""),
        }

    conversations: list[dict[str, Any]] = []
    for conversation_index, conversation in enumerate(tree.get("conversations", [])):
        conversation_fields = field_map(conversation)
        entries: list[dict[str, Any]] = []
        for entry_index, entry in enumerate(conversation.get("dialogueEntries", [])):
            fields = field_map(entry)
            outgoing_links = []
            for link in entry.get("outgoingLinks", []):
                outgoing_links.append(
                    {
                        "origin_conversation_id": int_member(
                            link, "originConversationID", "originConversationId"
                        ),
                        "origin_dialogue_id": int_member(
                            link, "originDialogueID", "originDialogueId"
                        ),
                        "destination_conversation_id": int_member(
                            link, "destinationConversationID", "destinationConversationId"
                        ),
                        "destination_dialogue_id": int_member(
                            link, "destinationDialogueID", "destinationDialogueId"
                        ),
                        "is_connector": bool(link.get("isConnector", False)),
                    }
                )
            entries.append(
                {
                    "entry_index": entry_index,
                    "id": entry.get("id", 0),
                    "actor_id": int(fields.get("Actor", "0") or 0),
                    "conversant_id": int(fields.get("Conversant", "0") or 0),
                    "dialogue_text": fields.get("Dialogue Text", ""),
                    "menu_text": fields.get("Menu Text", ""),
                    "description": fields.get("Description", ""),
                    "conditions": fields.get("Conditions", ""),
                    "outgoing_links": outgoing_links,
                }
            )
        conversations.append(
            {
                "conversation_index": conversation_index,
                "id": conversation.get("id", 0),
                "title": conversation_fields.get("Title", ""),
                "description": conversation_fields.get("Description", ""),
                "entries": entries,
            }
        )
    return {"actors": actors, "conversations": conversations}


def main() -> int:
    args = parse_args()
    game_root = args.game_root.resolve()
    data_dir = find_data_dir(game_root)
    targets = database_objects(args.inventory)
    generator = TypeTreeGenerator("6000.4.0f1")
    generator.load_local_game(str(game_root))
    output: dict[str, Any] = {"databases": []}

    for asset_file, path_id in sorted(targets):
        environment = UnityPy.load(str(data_dir / asset_file))
        environment.typetree_generator = generator
        obj = next(obj for obj in environment.objects if obj.path_id == path_id)
        database = extract_database(obj.read_typetree())
        database.update({"asset_file": asset_file, "path_id": path_id})
        output["databases"].append(database)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Dialogue databases: {len(output['databases'])}")
    print(f"Output: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
