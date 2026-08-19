#!/usr/bin/env python3
"""Extract string fields from a Unity Mono build with source context.

The script is intentionally read-only with respect to the game installation.
It uses UnityPy's optional TypeTreeGeneratorAPI to reconstruct MonoBehaviour
layouts from the game's managed assemblies.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator


SERIALIZED_FILE_NAMES = {"globalgamemanagers"}
SERIALIZED_FILE_SUFFIXES = {".assets"}
SCENE_FILE_RE = re.compile(r"^level\d+$")
LETTER_RE = re.compile(r"[A-Za-z]")
ASSETISH_RE = re.compile(
    r"(?:^|[/\\])(?:Assets|Library|Packages)(?:[/\\]|$)|"
    r"\.(?:png|jpe?g|tga|psd|mat|prefab|asset|anim|controller|wav|ogg|mp3|dll|cs|shader)$",
    re.IGNORECASE,
)
TYPEISH_RE = re.compile(
    r"^(?:[A-Za-z_]\w*\.){1,}[A-Za-z_]\w*(?:,\s*[A-Za-z_]\w*)?$"
)
# loc 查找键形态（UI_FOOTNOTE_UNSUBTLE）：与插件 LanguageSwap 的 LocKeyPattern
# 同规。这类字符串是程序查找键而非显示文本——如 OptionToggleController/
# OptionDropdownController 的 _values.[i].Label（叶子名是 "Label"，字段名规则
# 拦不住），译掉它会让 Loc 查无此键（v2.1.16 / k6 迁移复活事故）。
LOC_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$")


@dataclass(frozen=True)
class ScriptRef:
    file_name: str
    path_id: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("game_root", type=Path, help="Directory containing the Unity executable")
    parser.add_argument("output_dir", type=Path)
    return parser.parse_args()


def find_data_dir(game_root: Path) -> Path:
    candidates = sorted(p for p in game_root.iterdir() if p.is_dir() and p.name.endswith("_Data"))
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one *_Data directory under {game_root}, found {len(candidates)}")
    return candidates[0]


def serialized_files(data_dir: Path) -> list[Path]:
    result: list[Path] = []
    for path in data_dir.iterdir():
        if not path.is_file():
            continue
        if (
            path.name in SERIALIZED_FILE_NAMES
            or path.suffix in SERIALIZED_FILE_SUFFIXES
            or SCENE_FILE_RE.fullmatch(path.name)
        ):
            result.append(path)
    return sorted(result, key=lambda p: p.name)


def mono_script_name(data: Any) -> str:
    namespace = getattr(data, "m_Namespace", "")
    class_name = getattr(data, "m_ClassName", "")
    assembly = getattr(data, "m_AssemblyName", "")
    qualified = f"{namespace}.{class_name}" if namespace else class_name
    return f"{qualified}, {assembly}" if assembly else qualified


def read_script_ref(obj: Any) -> ScriptRef | None:
    """Read the MonoBehaviour header directly.

    TypeTreeGeneratorAPI currently misses the alignment flag on m_Enabled for
    some Unity 6 builds. Directly reading the standard header avoids reporting
    a shifted m_Script pointer while leaving the generated tree usable for the
    remaining fields.
    """

    raw = obj.get_raw_data()
    if len(raw) < 28:
        return None
    file_id = struct.unpack_from("<i", raw, 16)[0]
    path_id = struct.unpack_from("<q", raw, 20)[0]
    if file_id == 0:
        return ScriptRef(obj.assets_file.name, path_id)
    externals = obj.assets_file.externals
    if not 1 <= file_id <= len(externals):
        return None
    external_name = Path(externals[file_id - 1].path).name
    return ScriptRef(external_name, path_id)


def walk_strings(value: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield ".".join(path), value
        return
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk_strings(child, path + (str(key),))
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            yield from walk_strings(child, path + (f"[{index}]",))


class RawReader:
    """Minimal reader for Unity's aligned strings and primitive fields."""

    def __init__(self, data: bytes, offset: int = 0) -> None:
        self.data = data
        self.offset = offset

    def _ensure(self, size: int) -> None:
        if size < 0 or self.offset + size > len(self.data):
            raise ValueError(
                f"raw field out of bounds at {self.offset}: "
                f"requested {size}, object size {len(self.data)}"
            )

    def i32(self) -> int:
        self._ensure(4)
        value = struct.unpack_from("<i", self.data, self.offset)[0]
        self.offset += 4
        return value

    def i64(self) -> int:
        self._ensure(8)
        value = struct.unpack_from("<q", self.data, self.offset)[0]
        self.offset += 8
        return value

    def boolean(self) -> bool:
        self._ensure(1)
        value = bool(self.data[self.offset])
        self.offset += 1
        self.align4()
        return value

    def align4(self) -> None:
        self.offset = (self.offset + 3) & ~3

    def string(self) -> str:
        size = self.i32()
        self._ensure(size)
        value = self.data[self.offset : self.offset + size].decode("utf-8")
        self.offset += size
        self.align4()
        return value


def read_footnote_raw(obj: Any) -> dict[str, Any]:
    """Read Footnote objects whose generated Unity 6 tree is currently wrong.

    TypeTreeGenerator 1.25 models ``alternativeLabels`` as one string.  The
    shipped class actually serializes a list of strings.  Empty lists happen
    to parse, while every footnote with aliases shifts the remaining fields
    and fails.  Keeping this small explicit layout prevents those lore entries
    from silently disappearing from the translation inventory.
    """

    reader = RawReader(obj.get_raw_data(), 28)
    tree: dict[str, Any] = {
        "m_Name": reader.string(),
        "id": reader.string(),
        "label": reader.string(),
    }
    alias_count = reader.i32()
    if not 0 <= alias_count <= 1_000:
        raise ValueError(f"invalid Footnote alias count: {alias_count}")
    tree["alternativeLabels"] = [reader.string() for _ in range(alias_count)]
    tree["description"] = reader.string()
    tree["Notes"] = reader.string()
    tree["NoChoicesOK"] = reader.boolean()
    choice_count = reader.i32()
    if not 0 <= choice_count <= 1_000:
        raise ValueError(f"invalid Footnote choice count: {choice_count}")
    choices: list[dict[str, Any]] = []
    for _ in range(choice_count):
        choice = {
            "id": reader.string(),
            "label": reader.string(),
            "description": reader.string(),
            "experienceQuality": {
                "m_FileID": reader.i32(),
                "m_PathID": reader.i64(),
            },
            "experienceLevel": reader.i32(),
        }
        choices.append(choice)
    tree["Choices"] = choices
    if reader.offset != len(reader.data):
        raise ValueError(
            f"Footnote parser stopped at {reader.offset}/{len(reader.data)} bytes"
        )
    return tree


def _read_empty_friendly_criteria(reader: RawReader, type_name: str) -> None:
    count = reader.i32()
    if count != 0:
        raise ValueError(
            f"manual {type_name} parser does not support {count} friendly criteria"
        )


def read_aspect_raw(obj: Any) -> dict[str, Any]:
    """Read visible Aspect strings when ``_alternativeLabels`` is non-empty."""

    reader = RawReader(obj.get_raw_data(), 28)
    tree: dict[str, Any] = {"m_Name": reader.string()}
    tree["_setOrigin"] = reader.i32()
    _read_empty_friendly_criteria(reader, "Aspect")
    tree["_systemCouplingNote"] = reader.string()
    tree["_id"] = reader.string()
    tree["_label"] = reader.string()
    alias_count = reader.i32()
    if not 0 <= alias_count <= 1_000:
        raise ValueError(f"invalid Aspect alias count: {alias_count}")
    tree["_alternativeLabels"] = [reader.string() for _ in range(alias_count)]
    tree["_description"] = reader.string()
    return tree


def read_relationship_quality_raw(obj: Any) -> dict[str, Any]:
    """Read RelationshipQuality, including its serialized alert-message list."""

    reader = RawReader(obj.get_raw_data(), 28)
    tree: dict[str, Any] = {"m_Name": reader.string()}
    tree["_setOrigin"] = reader.i32()
    _read_empty_friendly_criteria(reader, "RelationshipQuality")
    tree["_systemCouplingNote"] = reader.string()
    tree["_id"] = reader.string()
    tree["_label"] = reader.string()
    tree["_icon"] = {"m_FileID": reader.i32(), "m_PathID": reader.i64()}
    tree["_journalImage"] = {"m_FileID": reader.i32(), "m_PathID": reader.i64()}
    tree["_actorName"] = reader.string()
    tree["_actorId"] = reader.i32()
    tree["_forceAlwaysActiveInJournal"] = reader.boolean()
    tree["_overrideJournalStatusLabel"] = reader.string()
    tree["_overrideJournalDescription"] = reader.string()
    message_count = reader.i32()
    if not 0 <= message_count <= 10_000:
        raise ValueError(f"invalid RelationshipQuality alert count: {message_count}")
    tree["_overrideAlertMessages"] = [reader.string() for _ in range(message_count)]
    tree["bonusFromLikedAspect"] = reader.i32()
    like_count = reader.i32()
    tree["_LikesAspects"] = [
        {"m_FileID": reader.i32(), "m_PathID": reader.i64()}
        for _ in range(like_count)
    ]
    tree["penaltyFromDislikedAspect"] = reader.i32()
    dislike_count = reader.i32()
    tree["_DislikesAspects"] = [
        {"m_FileID": reader.i32(), "m_PathID": reader.i64()}
        for _ in range(dislike_count)
    ]
    if reader.offset != len(reader.data):
        raise ValueError(
            "RelationshipQuality parser stopped at "
            f"{reader.offset}/{len(reader.data)} bytes"
        )
    return tree


def _read_string_array(reader: RawReader, field_name: str) -> list[str]:
    count = reader.i32()
    if not 0 <= count <= 10_000:
        raise ValueError(f"invalid {field_name} count: {count}")
    return [reader.string() for _ in range(count)]


def _read_music_track_listing(reader: RawReader) -> dict[str, Any]:
    """Read the serialised, non-Unity-object fields of one music listing."""

    return {
        "Id": reader.string(),
        "DisplayName": reader.string(),
        "ArtistName": reader.string(),
        "UseInScenes": _read_string_array(reader, "MusicTrackListing.UseInScenes"),
        "UseAsFirstTrackInScenes": _read_string_array(
            reader, "MusicTrackListing.UseAsFirstTrackInScenes"
        ),
        "Clip": {"m_FileID": reader.i32(), "m_PathID": reader.i64()},
        "SyncedWithTrackId": reader.string(),
    }


def read_music_track_library_raw(obj: Any) -> dict[str, Any]:
    """Read player-visible music metadata when the generated tree is stale.

    The Unity 6 type-tree generator currently misreads this ScriptableObject.
    ``DisplayName`` and ``ArtistName`` are passed directly to the in-game music
    player UI, so silently dropping the object would leave visible text outside
    the localisation inventory.
    """

    reader = RawReader(obj.get_raw_data(), 28)
    tree: dict[str, Any] = {
        "m_Name": reader.string(),
        "_defaultTrackListing": _read_music_track_listing(reader),
    }
    listing_count = reader.i32()
    if not 0 <= listing_count <= 10_000:
        raise ValueError(f"invalid MusicTrackLibrary listing count: {listing_count}")
    tree["Listings"] = [
        _read_music_track_listing(reader) for _ in range(listing_count)
    ]
    if reader.offset != len(reader.data):
        raise ValueError(
            "MusicTrackLibrary parser stopped at "
            f"{reader.offset}/{len(reader.data)} bytes"
        )
    return tree


def classify(field_path: str, value: str) -> tuple[bool, str]:
    text = value.strip()
    leaf = field_path.rsplit(".", 1)[-1].lower()
    if not text:
        return False, "empty"
    if not LETTER_RE.search(text):
        return False, "no_latin_letters"
    if leaf in {"m_name", "m_assemblyname", "m_namespace", "m_classname"}:
        return False, "engine_identifier"
    if leaf.endswith("key") or "lockey" in leaf or leaf.endswith("id"):
        return False, "key_or_id"
    if LOC_KEY_RE.fullmatch(text):
        return False, "key_or_id"
    if ASSETISH_RE.search(text):
        return False, "asset_path"
    if TYPEISH_RE.fullmatch(text):
        return False, "type_name"
    if len(text) == 1:
        return False, "single_character"
    return True, "candidate"


def game_object_names(environment: Any) -> dict[tuple[str, int], str]:
    names: dict[tuple[str, int], str] = {}
    for obj in environment.objects:
        if obj.type.name != "GameObject":
            continue
        try:
            names[(obj.assets_file.name, obj.path_id)] = obj.read().m_Name
        except Exception:
            continue
    return names


def script_names(environment: Any) -> dict[ScriptRef, str]:
    names: dict[ScriptRef, str] = {}
    for obj in environment.objects:
        if obj.type.name != "MonoScript":
            continue
        try:
            names[ScriptRef(obj.assets_file.name, obj.path_id)] = mono_script_name(obj.read())
        except Exception:
            continue
    return names


def extract_rows(environment: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    objects_by_file: collections.Counter[str] = collections.Counter()
    errors: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    go_names = game_object_names(environment)
    scripts = script_names(environment)

    for obj in environment.objects:
        if obj.type.name == "TextAsset":
            asset_file = obj.assets_file.name
            objects_by_file[asset_file] += 1
            try:
                data = obj.read()
                value = data.m_Script
                if isinstance(value, bytes):
                    value = value.decode("utf-8", errors="strict")
                else:
                    # UnityPy may surface binary TextAssets with surrogate
                    # code points. They are not localisable text and cannot
                    # be represented in our UTF-8 JSONL inventory.
                    value.encode("utf-8", errors="strict")
                if "\x00" in value:
                    continue
                is_candidate, reason = classify("m_Script", value)
                rows.append(
                    {
                        "asset_file": asset_file,
                        "path_id": obj.path_id,
                        "game_object": getattr(data, "m_Name", ""),
                        "script": "UnityEngine.TextAsset",
                        "field_path": "m_Script",
                        "source": value,
                        "candidate": is_candidate,
                        "classification": reason,
                    }
                )
            except Exception as exc:
                errors.append(
                    {
                        "asset_file": asset_file,
                        "path_id": obj.path_id,
                        "script": "UnityEngine.TextAsset",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            continue
        if obj.type.name != "MonoBehaviour":
            continue
        asset_file = obj.assets_file.name
        objects_by_file[asset_file] += 1
        script_ref = read_script_ref(obj)
        script = scripts.get(script_ref, "") if script_ref else ""
        try:
            tree = obj.read_typetree()
        except Exception as exc:
            fallback_reader = None
            if "Footnote" in script:
                fallback_reader = read_footnote_raw
            elif ".Aspect," in script:
                fallback_reader = read_aspect_raw
            elif ".RelationshipQuality," in script:
                fallback_reader = read_relationship_quality_raw
            elif ".MusicTrackLibrary," in script:
                fallback_reader = read_music_track_library_raw
            if fallback_reader is not None:
                try:
                    tree = fallback_reader(obj)
                except Exception as fallback_exc:
                    errors.append(
                        {
                            "asset_file": asset_file,
                            "path_id": obj.path_id,
                            "script": script,
                            "error": f"{type(exc).__name__}: {exc}",
                            "fallback_error": (
                                f"{type(fallback_exc).__name__}: {fallback_exc}"
                            ),
                        }
                    )
                    continue
            else:
                errors.append(
                    {
                        "asset_file": asset_file,
                        "path_id": obj.path_id,
                        "script": script,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue
        game_object_id = tree.get("m_GameObject", {}).get("m_PathID", 0)
        game_object = go_names.get((asset_file, game_object_id), "")
        for field_path, value in walk_strings(tree):
            is_candidate, reason = classify(field_path, value)
            rows.append(
                {
                    "asset_file": asset_file,
                    "path_id": obj.path_id,
                    "game_object": game_object,
                    "script": script,
                    "field_path": field_path,
                    "source": value,
                    "candidate": is_candidate,
                    "classification": reason,
                }
            )

    errors.append(
        {
            "summary": {
                "translatable_objects_by_file": dict(sorted(objects_by_file.items())),
                "rows": len(rows),
            }
        }
    )
    return rows, errors


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")


def write_candidates_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "id",
        "asset_file",
        "path_id",
        "game_object",
        "script",
        "field_path",
        "source",
        "translation",
        "status",
        "notes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        index = 0
        for row in rows:
            if not row["candidate"]:
                continue
            index += 1
            writer.writerow(
                {
                    "id": f"TAN-{index:06d}",
                    "asset_file": row["asset_file"],
                    "path_id": row["path_id"],
                    "game_object": row["game_object"],
                    "script": row["script"],
                    "field_path": row["field_path"],
                    "source": row["source"],
                    "translation": "",
                    "status": "untranslated",
                    "notes": "",
                }
            )


def main() -> int:
    args = parse_args()
    game_root = args.game_root.resolve()
    output_dir = args.output_dir.resolve()
    data_dir = find_data_dir(game_root)
    files = serialized_files(data_dir)
    if not files:
        raise RuntimeError(f"No serialized Unity files found in {data_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    environment = UnityPy.load(*(str(path) for path in files))
    generator = TypeTreeGenerator("6000.4.0f1")
    generator.load_local_game(str(game_root))
    environment.typetree_generator = generator

    rows, diagnostics = extract_rows(environment)
    write_jsonl(output_dir / "all_string_fields.jsonl", rows)
    write_candidates_csv(output_dir / "translation_candidates.csv", rows)
    (output_dir / "diagnostics.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    candidate_count = sum(bool(row["candidate"]) for row in rows)
    print(f"Serialized files: {len(files)}")
    print(f"String fields: {len(rows)}")
    print(f"Translation candidates: {candidate_count}")
    print(f"Diagnostics: {output_dir / 'diagnostics.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
