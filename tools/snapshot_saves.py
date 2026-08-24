#!/usr/bin/env python3
"""Snapshot the player's save directory into build/repro_saves/ for stable
bug-reproduction probes.

The in-game scenario probe (Diagnostics.AutoProbeScenario) loads the most
recent save. Playing further moves that target, so before a reproduction run
we snapshot the current saves; to restore the exact reproduction state, copy
the snapshot back over the save directory.

Usage:
  python tools/snapshot_saves.py            # 快照到 build/repro_saves/current/
  python tools/snapshot_saves.py --restore  # 从快照还原回存档目录（谨慎！）
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAVE_DIR = Path.home() / "AppData/LocalLow/Weather Factory/Travelling"
SNAPSHOT_DIR = ROOT / "build" / "repro_saves" / "current"
PATTERNS = ("save_*.dat", "saveSlotMetadata.json")


def copy_saves(src: Path, dst: Path) -> int:
    dst.mkdir(parents=True, exist_ok=True)
    count = 0
    for pattern in PATTERNS:
        for file in src.glob(pattern):
            shutil.copy2(file, dst / file.name)
            count += 1
    return count


def main() -> int:
    restore = "--restore" in sys.argv
    if restore:
        if not SNAPSHOT_DIR.exists():
            print(f"没有快照可还原：{SNAPSHOT_DIR}")
            return 1
        count = copy_saves(SNAPSHOT_DIR, SAVE_DIR)
        print(f"已从快照还原 {count} 个文件 -> {SAVE_DIR}")
        return 0
    count = copy_saves(SAVE_DIR, SNAPSHOT_DIR)
    print(f"已快照 {count} 个文件 -> {SNAPSHOT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
