#!/usr/bin/env python3
"""Bake reviewed zh-CN translations directly into the game's serialized assets.

The runtime patch intercepts rendered text; this tool instead rewrites the
authored strings in place (dialogue database fields, LocData entries, quality
labels, footnotes, scene UI text), so the game's own pipeline — typewriter,
buffer accumulation, [q=] substitution, [[link]] resolution — runs natively on
Chinese text.

Sites come from review_catalog.jsonl contexts (asset_file, path_id,
field_path); every write is verified against the recorded English source before
touching it, and the whole bake is re-read afterwards for a full assertion
pass.  Linkable labels additionally push their original English label onto
``alternativeLabels`` so runtime-injected English ``[[links]]`` still resolve
(ScriptablesCurator.MatchFromAlternate).

Only fingerprint-keyed data ships: this tool runs locally against a working
copy and never mutates the live game install by itself.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import shutil
import struct
import sys
from pathlib import Path
from typing import Any, Iterator

import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
from extract_unity_text import RawReader  # noqa: E402

UNITY_VERSION = "6000.4.0f1"
SCENE_FILE_RE = re.compile(r"^level\d+$")
SEGMENT_RE = re.compile(r"^(?P<name>[^\[\]]+)?(?:\[(?P<index>\d+)\])?$")
MONOBEHAVIOUR_HEADER_SIZE = 28  # m_GameObject PPtr + m_Enabled(+align) + m_Script PPtr

# Assets whose label participates in [[link]] resolution and that implement
# IHasAlternativeLabels (see ScriptablesCurator.EnumerateAlternativeSources).
LINKABLE_SCRIPTS = (
    "Travelling.Infrastructure.Footnotes.Footnote",
    "Travelling.PCQualities.Skill",
    "Travelling.PCQualities.Passion",
    "Travelling.PCQualities.Sign",
    "Travelling.PCQualities.Aspect",
    "Travelling.PCQualities.Item",
    "Travelling.PCQualities.Destination",
)


def with_source_edge_whitespace(source: str, translation: str) -> str:
    """把源串的首尾空白套到译文上：引文的 \\t\\t 缩进、段落尾距 \\n\\n、对话
    尾随空格都是排版结构，整体 strip 会把它们剥掉造成版式错位（v2.4.14 开场
    引文首行缩进丢失的教训）。"""
    lead = source[:len(source) - len(source.lstrip())]
    trail = source[len(source.rstrip()):]
    return lead + translation + trail


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("game_root", type=Path, help="Game install root (read-only reference)")
    parser.add_argument("catalog", type=Path, help="review_catalog.jsonl with contexts")
    parser.add_argument("work_dir", type=Path, help="Output directory for baked asset files")
    parser.add_argument("--supplement", type=Path, default=None,
                        help="runtime_supplement.csv (value-matched extra sites)")
    parser.add_argument("--link-targets", type=Path, default=None,
                        help="link_targets.csv (label -> zh mapping for alternativeLabels)")
    parser.add_argument("--site-overrides", type=Path, default=None,
                        help="site_overrides.csv（位点级译文覆盖：同一源串在不同显示上下文需要不同译文，"
                             "如 Spain 的 Quote 题签用《西班牙》、地图/脚注标签用裸名）")
    return parser.parse_args()


def find_data_dir(game_root: Path) -> Path:
    candidates = sorted(p for p in game_root.iterdir() if p.is_dir() and p.name.endswith("_Data"))
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one *_Data directory under {game_root}, found {len(candidates)}")
    return candidates[0]


def serialized_files(data_dir: Path) -> list[Path]:
    return sorted(
        p for p in data_dir.iterdir()
        if p.name == "globalgamemanagers" or p.suffix == ".assets" or SCENE_FILE_RE.match(p.name)
    )


def iter_segments(field_path: str) -> Iterator[tuple[str | None, int | None]]:
    for part in field_path.split("."):
        match = SEGMENT_RE.match(part)
        if not match or (match.group("name") is None and match.group("index") is None):
            raise ValueError(f"unparseable field_path segment {part!r} in {field_path!r}")
        name = match.group("name")
        index = match.group("index")
        yield name, int(index) if index is not None else None


def navigate(node: Any, field_path: str) -> Any:
    for name, index in iter_segments(field_path):
        if name is not None:
            if not isinstance(node, dict) or name not in node:
                raise KeyError(f"missing field {name!r} along {field_path!r}")
            node = node[name]
        if index is not None:
            if not isinstance(node, list) or index >= len(node):
                raise IndexError(f"missing index [{index}] along {field_path!r}")
            node = node[index]
    return node


def set_navigated(node: Any, field_path: str, value: str) -> None:
    segments = list(iter_segments(field_path))
    parent = node
    for name, index in segments[:-1]:
        if name is not None:
            parent = parent[name]
        if index is not None:
            parent = parent[index]
    last_name, last_index = segments[-1]
    if last_name is not None and last_index is not None:
        parent[last_name][last_index] = value
    elif last_name is not None:
        parent[last_name] = value
    else:
        parent[last_index] = value


def walk_strings(node: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from walk_strings(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk_strings(value, f"{path}.[{index}]")


def read_csv_mapping(path: Path, source_col: str, target_col: str) -> dict[str, str]:
    result: dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            source = (row.get(source_col) or "").strip()
            target = (row.get(target_col) or "").strip()
            if source and target:
                result.setdefault(source, target)
    return result


class RawWriter:
    """Mirror of extract_unity_text.RawReader for Unity's aligned fields."""

    def __init__(self) -> None:
        self.data = bytearray()

    def align4(self) -> None:
        while len(self.data) % 4:
            self.data.append(0)

    def i32(self, value: int) -> None:
        self.data += struct.pack("<i", value)

    def i64(self, value: int) -> None:
        self.data += struct.pack("<q", value)

    def boolean(self, value: bool) -> None:
        self.data.append(1 if value else 0)
        self.align4()

    def string(self, value: str) -> None:
        encoded = value.encode("utf-8")
        self.i32(len(encoded))
        self.data += encoded
        self.align4()

    def pptr(self, value: dict[str, int]) -> None:
        self.i32(value["m_FileID"])
        self.i64(value["m_PathID"])

    def string_list(self, values: list[str]) -> None:
        self.i32(len(values))
        for value in values:
            self.string(value)


def write_footnote_body(writer: RawWriter, tree: dict[str, Any]) -> None:
    writer.string(tree["m_Name"])
    writer.string(tree["id"])
    writer.string(tree["label"])
    writer.string_list(tree["alternativeLabels"])
    writer.string(tree["description"])
    writer.string(tree["Notes"])
    writer.boolean(tree["NoChoicesOK"])
    choices = tree["Choices"]
    writer.i32(len(choices))
    for choice in choices:
        writer.string(choice["id"])
        writer.string(choice["label"])
        writer.string(choice["description"])
        writer.pptr(choice["experienceQuality"])
        writer.i32(choice["experienceLevel"])


def read_raw_with_offset(obj: Any) -> tuple[dict[str, Any], str, bytes]:
    """Raw layouts for the four types TypeTreeGenerator 1.25 mis-models.

    Returns (tree, kind, tail).  ``tail`` preserves anything past the modeled
    region (Aspect readers intentionally stop early), and is re-appended
    verbatim on write.
    """
    data = obj.get_raw_data()
    header = data[:MONOBEHAVIOUR_HEADER_SIZE]

    def finish(reader: RawReader, tree: dict[str, Any], kind: str, checked: bool) -> tuple:
        if checked and reader.offset != len(data):
            raise ValueError(f"{kind} parser stopped at {reader.offset}/{len(data)}")
        tail = b"" if checked else data[reader.offset:]
        return tree, kind, tail

    errors: list[str] = []
    # Footnote
    try:
        reader = RawReader(data, MONOBEHAVIOUR_HEADER_SIZE)
        tree = {
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
        choices = []
        for _ in range(choice_count):
            choices.append({
                "id": reader.string(),
                "label": reader.string(),
                "description": reader.string(),
                "experienceQuality": {"m_FileID": reader.i32(), "m_PathID": reader.i64()},
                "experienceLevel": reader.i32(),
            })
        tree["Choices"] = choices
        return finish(reader, tree, "footnote", checked=True)
    except Exception as exc:
        errors.append(f"footnote: {exc}")
    # Aspect（读取器刻意停在 _description；保留尾随字节）
    try:
        reader = RawReader(data, MONOBEHAVIOUR_HEADER_SIZE)
        tree = {"m_Name": reader.string()}
        tree["_setOrigin"] = reader.i32()
        criteria = reader.i32()
        if criteria != 0:
            raise ValueError(f"unsupported friendly criteria: {criteria}")
        tree["_systemCouplingNote"] = reader.string()
        tree["_id"] = reader.string()
        tree["_label"] = reader.string()
        alias_count = reader.i32()
        if not 0 <= alias_count <= 1_000:
            raise ValueError(f"invalid Aspect alias count: {alias_count}")
        tree["_alternativeLabels"] = [reader.string() for _ in range(alias_count)]
        tree["_description"] = reader.string()
        return finish(reader, tree, "aspect", checked=False)
    except Exception as exc:
        errors.append(f"aspect: {exc}")
    # RelationshipQuality
    try:
        reader = RawReader(data, MONOBEHAVIOUR_HEADER_SIZE)
        tree = {"m_Name": reader.string()}
        tree["_setOrigin"] = reader.i32()
        criteria = reader.i32()
        if criteria != 0:
            raise ValueError(f"unsupported friendly criteria: {criteria}")
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
            raise ValueError(f"invalid alert count: {message_count}")
        tree["_overrideAlertMessages"] = [reader.string() for _ in range(message_count)]
        tree["bonusFromLikedAspect"] = reader.i32()
        like_count = reader.i32()
        tree["_LikesAspects"] = [
            {"m_FileID": reader.i32(), "m_PathID": reader.i64()} for _ in range(like_count)]
        tree["penaltyFromDislikedAspect"] = reader.i32()
        dislike_count = reader.i32()
        tree["_DislikesAspects"] = [
            {"m_FileID": reader.i32(), "m_PathID": reader.i64()} for _ in range(dislike_count)]
        return finish(reader, tree, "relationship", checked=True)
    except Exception as exc:
        errors.append(f"relationship: {exc}")
    # MusicTrackLibrary
    try:
        reader = RawReader(data, MONOBEHAVIOUR_HEADER_SIZE)

        def listing() -> dict[str, Any]:
            return {
                "Id": reader.string(),
                "DisplayName": reader.string(),
                "ArtistName": reader.string(),
                "UseInScenes": _raw_string_array(reader, "UseInScenes"),
                "UseAsFirstTrackInScenes": _raw_string_array(reader, "UseAsFirstTrackInScenes"),
                "Clip": {"m_FileID": reader.i32(), "m_PathID": reader.i64()},
                "SyncedWithTrackId": reader.string(),
            }

        tree = {"m_Name": reader.string(), "_defaultTrackListing": listing()}
        listing_count = reader.i32()
        if not 0 <= listing_count <= 10_000:
            raise ValueError(f"invalid listing count: {listing_count}")
        tree["Listings"] = [listing() for _ in range(listing_count)]
        return finish(reader, tree, "music", checked=True)
    except Exception as exc:
        errors.append(f"music: {exc}")
    raise ValueError("raw layouts all failed: " + "; ".join(errors))


def _raw_string_array(reader: RawReader, field_name: str) -> list[str]:
    count = reader.i32()
    if not 0 <= count <= 10_000:
        raise ValueError(f"invalid {field_name} count: {count}")
    return [reader.string() for _ in range(count)]


def write_raw_object(obj: Any, tree: dict[str, Any], kind: str, tail: bytes) -> None:
    header = obj.get_raw_data()[:MONOBEHAVIOUR_HEADER_SIZE]
    writer = RawWriter()
    writer.data += header
    if kind == "footnote":
        write_footnote_body(writer, tree)
    elif kind == "aspect":
        writer.string(tree["m_Name"])
        writer.i32(tree["_setOrigin"])
        writer.i32(0)  # friendly criteria：读取时断言为空
        writer.string(tree["_systemCouplingNote"])
        writer.string(tree["_id"])
        writer.string(tree["_label"])
        writer.string_list(tree["_alternativeLabels"])
        writer.string(tree["_description"])
    elif kind == "relationship":
        writer.string(tree["m_Name"])
        writer.i32(tree["_setOrigin"])
        writer.i32(0)
        writer.string(tree["_systemCouplingNote"])
        writer.string(tree["_id"])
        writer.string(tree["_label"])
        writer.pptr(tree["_icon"])
        writer.pptr(tree["_journalImage"])
        writer.string(tree["_actorName"])
        writer.i32(tree["_actorId"])
        writer.boolean(tree["_forceAlwaysActiveInJournal"])
        writer.string(tree["_overrideJournalStatusLabel"])
        writer.string(tree["_overrideJournalDescription"])
        writer.string_list(tree["_overrideAlertMessages"])
        writer.i32(tree["bonusFromLikedAspect"])
        writer.i32(len(tree["_LikesAspects"]))
        for pptr in tree["_LikesAspects"]:
            writer.pptr(pptr)
        writer.i32(tree["penaltyFromDislikedAspect"])
        writer.i32(len(tree["_DislikesAspects"]))
        for pptr in tree["_DislikesAspects"]:
            writer.pptr(pptr)
    elif kind == "music":
        writer.string(tree["m_Name"])

        def listing(value: dict[str, Any]) -> None:
            writer.string(value["Id"])
            writer.string(value["DisplayName"])
            writer.string(value["ArtistName"])
            writer.string_list(value["UseInScenes"])
            writer.string_list(value["UseAsFirstTrackInScenes"])
            writer.pptr(value["Clip"])
            writer.string(value["SyncedWithTrackId"])

        listing(tree["_defaultTrackListing"])
        writer.i32(len(tree["Listings"]))
        for value in tree["Listings"]:
            listing(value)
    else:
        raise ValueError(f"unknown raw kind {kind}")
    writer.data += tail
    obj.set_raw_data(bytes(writer.data))


def main() -> int:
    args = parse_args()
    game_root = args.game_root.resolve()
    data_dir = find_data_dir(game_root)
    work_dir = args.work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    workspace = args.catalog.resolve().parents[2]
    supplement_path = args.supplement or workspace / "glossary" / "runtime_supplement.csv"
    link_targets_path = args.link_targets or workspace / "glossary" / "link_targets.csv"
    site_overrides_path = args.site_overrides or workspace / "glossary" / "site_overrides.csv"

    # site -> desired translation, and the expected current (English) value.
    site_translation: dict[tuple[str, int, str], str] = {}
    site_source: dict[tuple[str, int, str], str] = {}
    object_scripts: dict[tuple[str, int], str] = {}  # 对象 -> 脚本类全名（原始布局路由用）
    skill_label_map: dict[str, str] = {}  # 中文技能标签 -> 英文原标签（RawLabel 用）
    conflicts: list[str] = []
    with args.catalog.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            entry = json.loads(line)
            translation = (entry.get("translation") or "").strip()
            if not translation:
                continue
            for context in entry.get("contexts") or []:
                site = (context["asset_file"], context["path_id"], context["field_path"])
                ctx_source = context.get("source", entry["source"]) or ""
                baked = with_source_edge_whitespace(ctx_source, translation)
                if site in site_translation and site_translation[site] != baked:
                    conflicts.append(f"{site}: {site_translation[site][:40]!r} vs {baked[:40]!r}")
                    continue
                site_translation[site] = baked
                site_source[site] = ctx_source
                object_scripts.setdefault(
                    (context["asset_file"], context["path_id"]),
                    context.get("script", ""))
                if (context["field_path"] == "_label" and
                        context.get("script", "").startswith("Travelling.PCQualities.Skill")):
                    source_text = context.get("source", entry["source"])
                    if translation != source_text:
                        skill_label_map[translation] = source_text
    if conflicts:
        print(f"Site conflicts (same field, different translations): {len(conflicts)}")
        for conflict in conflicts[:10]:
            print("  " + conflict)
        return 1

    # 位点级译文覆盖：同一源串在不同显示上下文需要不同译文（如 Spain：地图与
    # 脚注标签用裸名，Quote 题签用《西班牙》）。覆盖目标必须是目录已收录的
    # 位点，且 source_en 须与目录登记的源文一致（防 ID/位点静默漂移）。
    site_override_count = 0
    if site_overrides_path.exists():
        with site_overrides_path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                site = (row["asset_file"], int(row["path_id"]), row["field_path"])
                target = (row.get("translation") or "").strip()
                if not target:
                    continue
                if site not in site_translation:
                    print(f"Site override targets unknown site: {site}")
                    return 1
                if row.get("source_en") and site_source.get(site) != row["source_en"]:
                    print(f"Site override source drift at {site}: "
                          f"{site_source.get(site)!r} != {row['source_en']!r}")
                    return 1
                site_translation[site] = target
                site_override_count += 1
        print(f"Site overrides applied: {site_override_count}")

    needed_files = {site[0] for site in site_translation}
    supplement = read_csv_mapping(supplement_path, "source_en", "target_zh") if supplement_path.exists() else {}
    link_labels = read_csv_mapping(link_targets_path, "source_en", "target_zh") if link_targets_path.exists() else {}
    link_labels_ci = {key.casefold(): value for key, value in link_labels.items()}

    # Supplement rows carry no hand-curated context: pull their sites from the
    # latest extraction snapshot (asset_file/path_id/field_path per string).
    extracted_path = workspace / "build" / "extracted_current" / "all_string_fields.jsonl"
    supplement_sites = 0
    if supplement and extracted_path.exists():
        with extracted_path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                source_value = row.get("source", "")
                target = supplement.get(source_value)
                if target is None:
                    # 提取快照可能带首尾空白（补充表键已 strip），宽容匹配一次。
                    target = supplement.get(source_value.strip())
                if target is None or not row.get("candidate"):
                    continue
                site = (row["asset_file"], row["path_id"], row["field_path"])
                if site in site_translation:
                    continue  # 目录条目已覆盖该字段
                site_translation[site] = target
                site_source[site] = row["source"]
                object_scripts.setdefault(
                    (row["asset_file"], row["path_id"]), row.get("script", ""))
                needed_files.add(row["asset_file"])
                supplement_sites += 1

    all_files = serialized_files(data_dir)
    for path in all_files:
        if path.name in needed_files:
            shutil.copy2(path, work_dir / path.name)
    load_paths = [
        str(work_dir / path.name) if path.name in needed_files else str(path)
        for path in all_files
    ]
    env = UnityPy.load(*load_paths)
    generator = TypeTreeGenerator(UNITY_VERSION)
    generator.load_local_game(str(game_root))
    env.typetree_generator = generator

    # Map work-dir serialized files by bare name.
    file_by_name: dict[str, Any] = {}
    for key, serialized in env.files.items():
        name = Path(str(key)).name
        if str(work_dir) in str(key) or (work_dir / name).exists() and Path(str(key)).parent == work_dir:
            file_by_name[name] = serialized
    missing_files = needed_files - set(file_by_name)
    if missing_files:
        print(f"Work-dir files not loaded: {sorted(missing_files)}")
        return 1

    stats: collections.Counter[str] = collections.Counter()
    mismatches: list[str] = []
    dirty_files: set[str] = set()
    label_alt_added = 0
    link_alias_added = 0

    # Group sites by object: the DialogueDatabase alone carries thousands of
    # sites, and read/save_typetree on it costs seconds per call.
    sites_by_object: dict[tuple[str, int], list[tuple[str, str]]] = collections.defaultdict(list)
    for (asset_file, path_id, field_path), translation in sorted(site_translation.items()):
        sites_by_object[(asset_file, path_id)].append((field_path, translation))

    for (asset_file, path_id), sites in sorted(sites_by_object.items()):
        serialized = file_by_name[asset_file]
        obj = serialized.objects.get(path_id)
        if obj is None:
            mismatches.append(f"{asset_file}:{path_id} object missing")
            continue
        raw_kind: str | None = None
        raw_tail = b""
        # 注意：v2.2.15 曾按脚本类名把 Footnote/Aspect/RelationshipQuality/
        # MusicTrackLibrary 全部强制走原始布局写回，结果 Unity 启动判定
        # resources.assets 损坏（崩溃）。回退为 typetree 优先。已知限制：
        # typetree 模型把 Footnote.alternativeLabels 读成字符串 → 别名推送
        # 对这四类静默失效；该需求改由插件运行时注入（Plugin.cs
        # InjectAlternativeLabels），烘焙不再为此写原始布局。
        try:
            tree = obj.read_typetree()
        except Exception:
            try:
                tree, raw_kind, raw_tail = read_raw_with_offset(obj)
            except Exception as raw_exc:
                mismatches.append(f"{asset_file}:{path_id} read failed: {raw_exc}")
                continue
        changed = False
        alt_candidates: list[str] = []
        for field_path, translation in sites:
            try:
                current = navigate(tree, field_path)
            except (KeyError, IndexError, ValueError) as exc:
                mismatches.append(f"{asset_file}:{path_id}:{field_path} navigate failed: {exc}")
                continue
            expected = site_source[(asset_file, path_id, field_path)]
            if not isinstance(current, str):
                mismatches.append(f"{asset_file}:{path_id}:{field_path} not a string")
                continue
            if current == translation:
                stats["already_baked"] += 1
                continue
            if current != expected:
                # 提取快照可能与目录源有首尾空白差异；宽容比对，拒绝盲目覆盖。
                if current.strip() != expected.strip():
                    mismatches.append(
                        f"{asset_file}:{path_id}:{field_path} value drift: "
                        f"{current[:40]!r} != {expected[:40]!r}")
                    continue
                stats["trimmed_match"] += 1
            set_navigated(tree, field_path, translation)
            # 链接 label 烘焙后，把原英文 label 记入 alternativeLabels，
            # 让代码运行时注入的英文 [[X]] 仍能解析（MatchFromAlternate）。
            if field_path.endswith("label") or field_path.endswith("Label"):
                alt_candidates.append(current)
            stats["baked"] += 1
            changed = True
        # [[X]] 链接的显示文字烘焙成中文后，悬停解析仍按 label /
        # alternativeLabels 匹配（MatchFromAlternate，OrdinalIgnoreCase）。
        # 除把被烘 label 的英文原值记入 alternativeLabels 外，还要为每个在
        # link_targets.csv 里有译名的英文别名追加中文别名（如 Amiral ->
        # 海军上将），否则烘焙后的 [[海军上将]] 悬停只弹出空窗口。
        # 注意：即使本对象没有字段变化（已全部烘焙过），别名也可能需要补写。
        aliases_changed = False
        for alt_field in ("alternativeLabels", "_alternativeLabels"):
            alternatives = tree.get(alt_field)
            if not isinstance(alternatives, list):
                continue
            for original in alt_candidates:
                if original not in alternatives:
                    alternatives.append(original)
                    label_alt_added += 1
                    aliases_changed = True
            for alias in list(alternatives):
                zh_alias = link_labels.get(alias) or link_labels_ci.get(alias.casefold())
                if zh_alias and zh_alias not in alternatives:
                    alternatives.append(zh_alias)
                    link_alias_added += 1
                    aliases_changed = True
        if not changed and not aliases_changed:
            continue
        if raw_kind is not None:
            write_raw_object(obj, tree, raw_kind, raw_tail)
        else:
            obj.save_typetree(tree)
        dirty_files.add(asset_file)

    saved: dict[str, int] = {}
    for name in sorted(dirty_files):
        serialized = file_by_name[name]
        data = serialized.save()
        out_path = work_dir / name
        with out_path.open("wb") as handle:
            handle.write(data)
        saved[name] = len(data)

    # Skill 标签已烘成中文；运行时 sprite 图集键（RawLabel）必须保持英文。
    (work_dir / "raw_labels.json").write_text(
        json.dumps(skill_label_map, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "sites": len(site_translation),
        "supplement_sites": supplement_sites,
        "site_overrides": site_override_count,
        "stats": dict(stats),
        "label_alternative_labels_added": label_alt_added,
        "link_aliases_added": link_alias_added,
        "skill_raw_labels": len(skill_label_map),
        "mismatches": mismatches,
        "files_written": saved,
    }
    (work_dir / "bake_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in {"mismatches", "files_written"}}, ensure_ascii=False, indent=2))
    print(f"files_written: {len(saved)}  mismatches: {len(mismatches)}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
