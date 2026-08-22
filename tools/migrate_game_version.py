#!/usr/bin/env python3
"""游戏版本更新后的一键补丁迁移管线（HANDOFF §89 流程固化）。

Steam 更新游戏后运行：

    python tools/migrate_game_version.py <游戏目录> --patch-version 2.6.2

自动走完：提取 → 工作清单 → rebase 复用旧译 → 合并 → 烘焙 → 回读校验 →
重建 lang_swap/label_fidelity → 更新 extracted_current 快照 → 打包 → 安装。

若新版本有新增/修订文本（内容哈希变化），rebase 会缺译中断：脚本把新旧对照
写到 tmp/<tag>_missing_diffs.json 并退出码 2；补译成 supplement jsonl 后带
--supplement 续跑（已完成的步骤自动跳过/复用）。

前置条件：游戏目录的资产须为 vanilla（Steam 刚更新完即为此态；若装着旧补丁，
先跑卸载）。安装阶段会删除游戏目录的 BepInEx/winhttp.dll/doorstop_config.ini/
.travelling-cn-install.json 再全新安装（§89/§90 确立的顺序）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
TOOLS = WORKSPACE / "tools"


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"\n>>> {' '.join(str(c) for c in cmd[:4])} ...")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kwargs)
    tail = (result.stdout or "").strip().splitlines()[-6:]
    for line in tail:
        encoding = sys.stdout.encoding or "utf-8"
        safe_line = line.encode(encoding, errors="backslashreplace").decode(encoding)
        print("   ", safe_line)
    if result.returncode != 0:
        encoding = sys.stdout.encoding or "utf-8"
        safe_error = (result.stderr or "")[-600:].encode(
            encoding, errors="backslashreplace"
        ).decode(encoding)
        print(safe_error)
        raise SystemExit(f"步骤失败（exit {result.returncode}）：{cmd[1]}")
    return result


def py(tool: str) -> list[str]:
    return [sys.executable, "-X", "utf8", str(TOOLS / tool)]


def latest_translations_dir() -> Path:
    """工作区根的 translations_k* 目录取编号最大者（最近审校线）。"""
    import re
    cands = []
    for d in WORKSPACE.iterdir():
        m = re.fullmatch(r"translations_k(\d+)", d.name)
        if m and d.is_dir():
            cands.append((int(m.group(1)), d))
    if not cands:
        raise SystemExit("未找到 translations_k* 审校目录")
    return max(cands)[1]


def assert_vanilla_assets(game_root: Path) -> None:
    data_dir = next(p for p in game_root.iterdir() if p.is_dir() and p.name.endswith("_Data"))
    probe = data_dir / "resources.assets"
    if probe.exists():
        blob = probe.read_bytes()
        if "下一项选择会动用".encode("utf-8") in blob:
            raise SystemExit("游戏资产仍是烘焙中文版——请先卸载旧补丁（或让 Steam 校验还原）再迁移。")


def archive_stale_manifest_if_safe(state_file: Path, game_root: Path, game_version: str) -> None:
    """归档 Steam 更新后无法由旧卸载器闭环的清单；绝不静默删除仍在生效的补丁文件。"""
    manifest = json.loads(state_file.read_text(encoding="utf-8-sig"))
    still_installed: list[str] = []
    for item in manifest.get("files", []):
        # unchanged 表示旧安装器没有创建或替换此文件；即使哈希相同也不属于需卸载内容。
        if item.get("action") not in {"created", "replaced"}:
            continue
        wanted = (item.get("installed_sha256") or "").upper()
        if not wanted:
            continue
        path = game_root / item["path"]
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest().upper() == wanted:
            still_installed.append(item["path"])
    if still_installed:
        preview = "、".join(still_installed[:5])
        raise SystemExit(
            "旧卸载器保留了仍与旧补丁哈希相同的文件，拒绝移除安装清单："
            f"{preview}。请先处理卸载异常。"
        )

    old_patch = str(manifest.get("patch_version") or "unknown").replace("/", "_")
    safe_game_version = game_version.replace("/", "_")
    archive = game_root / f".travelling-cn-install.obsolete-{old_patch}-{safe_game_version}.json"
    serial = 1
    while archive.exists():
        archive = game_root / f".travelling-cn-install.obsolete-{old_patch}-{safe_game_version}-{serial}.json"
        serial += 1
    state_file.replace(archive)
    print(f"旧清单已归档（未删除）：{archive.name}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("game_root", type=Path)
    ap.add_argument("--patch-version", required=True, help="补丁版本号，如 2.6.2")
    ap.add_argument("--translations", type=Path, default=None, help="旧版审校译文目录（默认自动取最新 translations_k*）")
    ap.add_argument("--supplement", type=Path, default=None, help="增补译文 jsonl（rebase 缺译后续跑用）")
    ap.add_argument("--skip-install", action="store_true")
    args = ap.parse_args()

    game_root = args.game_root.resolve()
    version_file = game_root / "version.txt"
    if not version_file.exists():
        raise SystemExit(f"未找到 {version_file}")
    game_version = version_file.read_text(encoding="utf-8").strip()
    version_parts = game_version.split(".")
    if len(version_parts) < 2:
        raise SystemExit(f"无法从 version.txt 解析构建标识：{game_version}")
    tag = "".join(version_parts[-2:])  # 2026.8.k.97 -> k97
    print(f"游戏版本：{game_version}（标签 {tag}）")

    assert_vanilla_assets(game_root)

    extracted = WORKSPACE / "build" / f"extracted_{tag}"
    worklist = WORKSPACE / "build" / f"worklist_{tag}"
    rebased = WORKSPACE / "build" / f"worklist_{tag}_rebased"
    merged = WORKSPACE / "build" / f"merged_{tag}"
    translations = (args.translations or latest_translations_dir()).resolve()
    print(f"旧译来源：{translations}")

    # 1. 提取
    if not (extracted / "all_string_fields.jsonl").exists():
        run(py("extract_unity_text.py") + [str(game_root), str(extracted)])
    else:
        print(f"复用已有提取：{extracted}")

    # 2. 工作清单
    if not (worklist / "worklist.jsonl").exists():
        run(py("prepare_worklist.py") + [str(extracted / "all_string_fields.jsonl"), str(worklist)])
    else:
        print(f"复用已有清单：{worklist}")

    # 3. rebase 复用旧译
    if not rebased.exists():
        rebase_cmd = py("rebase_translations_to_worklist.py") + [str(worklist), str(translations), str(rebased)]
        if args.supplement:
            rebase_cmd += ["--supplement", str(args.supplement)]
        result = subprocess.run(rebase_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        print((result.stdout or "").strip()[-400:])
        if result.returncode != 0:
            # 缺译：生成新旧对照清单供补译
            missing_out = WORKSPACE / "tmp" / f"{tag}_missing_diffs.json"
            write_missing_diffs(worklist, translations, missing_out)
            print(f"\n有文本在新版被修订/新增，需要补译。对照清单：{missing_out}")
            print("补译成 supplement jsonl 后加 --supplement 重跑本脚本。")
            return 2
    else:
        print(f"复用已有 rebase：{rebased}")

    # 4. 合并
    if not (merged / "review_catalog.jsonl").exists():
        run(py("merge_and_validate_translations.py") + [str(worklist / "worklist.jsonl"), str(rebased), str(merged)])
    else:
        print(f"复用已有合并：{merged}")

    # 5. 烘焙（游戏目录即 vanilla 源）
    run(py("bake_translations.py") + [str(game_root), str(merged / "review_catalog.jsonl"), str(WORKSPACE / "build" / "baked_assets")])

    # 6. 回读校验
    run(py("verify_baked_assets.py") + [str(game_root), str(merged / "review_catalog.jsonl"), str(WORKSPACE / "build" / "baked_assets")])

    # 7. 重建运行时映射
    run(py("build_lang_swap_map.py") + [str(merged / "review_catalog.jsonl"), str(WORKSPACE / "glossary" / "runtime_supplement.csv"), str(WORKSPACE / "build" / "baked_assets" / "lang_swap.json")])
    run(py("build_label_fidelity.py") + [str(extracted / "all_string_fields.jsonl"), str(merged / "review_catalog.jsonl"), str(WORKSPACE / "build" / "baked_assets" / "label_fidelity.json")])

    # 8. 更新 extracted_current 快照（烘焙器 supplement 位点查询依赖）
    current = WORKSPACE / "build" / "extracted_current"
    if current.exists():
        shutil.rmtree(current)
    shutil.copytree(extracted, current)
    print(f"extracted_current 已更新 -> {extracted.name}")

    # 9. slim 静态检查 + 打包
    run(py("test_slim_plugin.py"))
    run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(TOOLS / "build_current_test_install.ps1"),
         "-PatchVersion", args.patch_version,
         "-SupportedGameVersion", game_version,
         "-BakedAssetsDir", r"build\baked_assets",
         "-WorklistRoot", str(worklist / "worklist.jsonl"),
         "-TranslationsRoot", str(rebased),
         "-MergedRoot", str(merged),
         "-PluginProfile", "baked"])

    if args.skip_install:
        print("\n已跳过安装（--skip-install）。包在 build/current_test_install/。")
        return 0

    # 10. 安装：若存在旧安装状态，先跑卸载器（还原 vanilla 资产、清除旧文件），
    # 再全新安装——绝不能用"删清单+强装"的套路：那会让安装器把已烘焙资产判为
    # unchanged，斩断 vanilla 还原链，用户卸载后中文资产留在原地、没有插件
    # 字体全部豆腐块（v2.5.3 用户实测事故）。
    state_file = game_root / ".travelling-cn-install.json"
    if state_file.exists():
        print("检测到旧安装状态，先运行卸载器……")
        uninstall = WORKSPACE / "build" / "current_test_install" / "TravellingAtNight_ZH-CN_current-test" / "installer" / "卸载汉化.ps1"
        run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
             str(uninstall), "-GamePath", str(game_root)])
        if state_file.exists():
            # Steam 更新后的 15 个资产会同时不匹配旧 original/installed 哈希，旧卸载器
            # 会安全保留清单。此时只在确认没有任何旧补丁文件仍按安装哈希存在后归档
            # 清单；BepInEx 的用户配置/日志也保留，让新安装器自行做冲突检查。
            archive_stale_manifest_if_safe(state_file, game_root, game_version)
    pkg = WORKSPACE / "build" / "current_test_install" / "TravellingAtNight_ZH-CN_current-test"
    run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(pkg / "installer" / "安装汉化.ps1"), "-GamePath", str(game_root)])

    manifest = json.loads((game_root / ".travelling-cn-install.json").read_text(encoding="utf-8-sig"))
    bad = 0
    total = 0
    for f in manifest["files"]:
        if f.get("action") == "unchanged" or not f.get("applied", True):
            continue
        total += 1
        p = game_root / f["path"]
        want = (f.get("installed_sha256") or "").upper()
        if not p.exists() or (want and hashlib.sha256(p.read_bytes()).hexdigest().upper() != want):
            print("   异常:", f["path"])
            bad += 1
    print(f"\n装机核验：{total} 文件，异常 {bad}")
    if bad:
        raise SystemExit("装机核验失败")
    print(f"\n迁移完成：补丁 v{args.patch_version} / 游戏 {game_version}。")
    print("下一步：开 Diagnostics 探针跑回归（AutoProbeNewGame / AutoProbeSoak / AutoProbeSwap），")
    print("确认全绿后关探针，交用户验收。")
    return 0


def write_missing_diffs(worklist: Path, translations: Path, out_path: Path) -> None:
    """rebase 缺译时生成新旧对照（按资产位点关联前身，附旧译）。"""
    wl_new = {}
    for line in (worklist / "worklist.jsonl").open(encoding="utf-8"):
        if line.strip():
            d = json.loads(line)
            wl_new[d["id"]] = d
    old_by_site = {}
    old_by_id = {}
    # 前身位点取自旧版 merged 目录（含 contexts）；旧译取自 translations 目录
    import glob
    merged_dirs = sorted(glob.glob(str(WORKSPACE / "build" / "merged_k*")), key=os.path.getmtime)
    if merged_dirs:
        for line in open(Path(merged_dirs[-1]) / "review_catalog.jsonl", encoding="utf-8"):
            if line.strip():
                d = json.loads(line)
                for c in d.get("contexts", []):
                    old_by_site[(c.get("asset_file"), c.get("path_id"), c.get("field_path"))] = d
    for chunk in sorted(translations.glob("chunk_*.jsonl")):
        for line in chunk.open(encoding="utf-8"):
            if line.strip():
                d = json.loads(line)
                old_by_id[d["id"]] = d
    missing = []
    for wid, d in wl_new.items():
        if wid in old_by_id:
            continue
        old = None
        for c in d.get("contexts", []):
            key = (c.get("asset_file"), c.get("path_id"), c.get("field_path"))
            if key in old_by_site:
                old = old_by_site[key]
                break
        missing.append({
            "id": wid,
            "domain": d.get("domain"),
            "new": d.get("source"),
            "old": (old or {}).get("source"),
            "old_translation": (old or {}).get("translation"),
            "contexts": d.get("contexts", []),
        })
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(missing, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"待补译 {len(missing)} 条")


if __name__ == "__main__":
    sys.exit(main())
