#!/usr/bin/env python3
"""Focused tests for manual Unity serialisation fallbacks."""

from __future__ import annotations

import importlib.util
import struct
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "extract_unity_text", ROOT / "tools" / "extract_unity_text.py"
)
assert SPEC and SPEC.loader
extractor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = extractor
SPEC.loader.exec_module(extractor)
WORKLIST_SPEC = importlib.util.spec_from_file_location(
    "prepare_worklist", ROOT / "tools" / "prepare_worklist.py"
)
assert WORKLIST_SPEC and WORKLIST_SPEC.loader
worklist = importlib.util.module_from_spec(WORKLIST_SPEC)
sys.modules[WORKLIST_SPEC.name] = worklist
WORKLIST_SPEC.loader.exec_module(worklist)


def aligned_string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    result = struct.pack("<i", len(encoded)) + encoded
    return result + b"\0" * (-len(result) % 4)


def string_array(values: list[str]) -> bytes:
    return struct.pack("<i", len(values)) + b"".join(
        aligned_string(value) for value in values
    )


def listing(
    track_id: str,
    display_name: str,
    artist_name: str,
    scenes: list[str],
    first_scenes: list[str],
    path_id: int,
    synced_id: str,
) -> bytes:
    return b"".join(
        [
            aligned_string(track_id),
            aligned_string(display_name),
            aligned_string(artist_name),
            string_array(scenes),
            string_array(first_scenes),
            struct.pack("<iq", 0, path_id),
            aligned_string(synced_id),
        ]
    )


class FakeObject:
    def __init__(self, raw: bytes) -> None:
        self.raw = raw

    def get_raw_data(self) -> bytes:
        return self.raw


class MusicTrackLibraryTests(unittest.TestCase):
    def test_reads_player_visible_track_metadata_and_consumes_object(self) -> None:
        raw = b"\0" * 28 + aligned_string("Library")
        raw += listing("default", "Train", "JW", [], [], 10, "")
        raw += struct.pack("<i", 1)
        raw += listing(
            "lecygne",
            "Hans Kindler - Rosario Bourdon",
            "Le Cygne (The Swan)",
            ["antibes:chezFelix"],
            [],
            11,
            "",
        )

        tree = extractor.read_music_track_library_raw(FakeObject(raw))

        self.assertEqual(tree["m_Name"], "Library")
        self.assertEqual(tree["_defaultTrackListing"]["DisplayName"], "Train")
        self.assertEqual(
            tree["Listings"][0]["ArtistName"], "Le Cygne (The Swan)"
        )
        self.assertEqual(tree["Listings"][0]["UseInScenes"], ["antibes:chezFelix"])

    def test_rejects_trailing_bytes_to_detect_layout_drift(self) -> None:
        raw = b"\0" * 28 + aligned_string("Library")
        raw += listing("default", "Train", "JW", [], [], 10, "")
        raw += struct.pack("<i", 0) + b"drift"
        with self.assertRaisesRegex(ValueError, "stopped at"):
            extractor.read_music_track_library_raw(FakeObject(raw))

    def test_worklist_includes_only_visible_music_metadata(self) -> None:
        base = {
            "asset_file": "resources.assets",
            "path_id": 28112,
            "game_object": "",
            "script": "Travelling.Audio.MusicTrackLibrary, travelling.scripts",
            "candidate": True,
        }
        rows = [
            {**base, "field_path": "Listings.[0].DisplayName", "source": "Track"},
            {**base, "field_path": "Listings.[0].ArtistName", "source": "Artist"},
            {**base, "field_path": "Listings.[0].UseInScenes.[0]", "source": "scene"},
        ]

        contexts = worklist.ordinary_contexts(rows)

        self.assertEqual([item["source"] for item in contexts], ["Track", "Artist"])
        self.assertTrue(all(item["domain"] == "ui" for item in contexts))


if __name__ == "__main__":
    unittest.main()
