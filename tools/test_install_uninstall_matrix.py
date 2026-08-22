#!/usr/bin/env python3
"""Exercise the release installer/uninstaller in disposable Windows sandboxes.

This is an integration test: each case builds a schema-v2 synthetic package,
then invokes the real release scripts against a fake game directory.  It never
uses the default Steam path.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterator


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "release" / "installer" / "安装汉化.ps1"
UNINSTALLER = ROOT / "release" / "installer" / "卸载汉化.ps1"
RESOLVER = ROOT / "release" / "installer" / "Resolve-GamePath.ps1"
README = ROOT / "release" / "README_安装说明.md"
EVIDENCE_ROOT = ROOT / "build" / "final_qa" / "install_matrix"
STATE_NAME = ".travelling-cn-install.json"

OUTER_FILES = (
    "installer/安装汉化.ps1",
    "installer/卸载汉化.ps1",
    "installer/Resolve-GamePath.ps1",
    "README_安装说明.md",
    "术语表与译名说明.md",
    "术语表与译名说明.txt",
    "一键安装.bat",
    "一键卸载.bat",
    "licenses/BepInEx-MIT.txt",
    "licenses/NotoSansSC-OFL.txt",
    "licenses/THIRD_PARTY_NOTICES.md",
    "licenses/BepInExHarmony-MIT.txt",
    "licenses/HarmonyX-MIT.txt",
    "licenses/Harmony-original-MIT.txt",
    "licenses/MonoMod-MIT.txt",
    "licenses/MonoCecil-MIT.txt",
    "licenses/UnityDoorstop-LGPL-2.1.txt",
    "licenses/UnityDoorstop-v4.5.0-source.zip",
)

PAYLOAD: dict[str, bytes] = {
    "winhttp.dll": b"synthetic doorstop 1.2.5\n",
    "doorstop_config.ini": b"[UnityDoorstop]\nenabled=true\n",
    ".doorstop_version": b"4.5.0\n",
    "BepInEx/core/BepInEx.dll": b"synthetic BepInEx core\n",
    "BepInEx/plugins/TravellingCN/TravellingCN.dll": b"synthetic TravellingCN 1.2.5\n",
    "BepInEx/plugins/TravellingCN/catalog.zh-CN.json": b'{"fixture":"translation"}\n',
    "BepInEx/plugins/TravellingCN/link_targets.zh-CN.json": b'{"fixture":"link"}\n',
    "BepInEx/plugins/TravellingCN/font/NotoSansCJKsc-Regular.otf": b"synthetic font\n",
}


@dataclass
class Result:
    case: str
    status: str
    assertions: int
    detail: str


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def copy_script_for_sandbox(source: Path, destination: Path) -> None:
    """Copy a release script while neutralising only the host-wide process guard.

    The matrix always targets a disposable fake game directory, but the production
    guard intentionally checks the machine-wide ``travelling`` process.  A game
    instance owned by the user must not make this isolated QA suite unusable.  We
    require the exact production guard to be present, then disable it only in the
    copied sandbox fixture; every filesystem/integrity/rollback branch remains the
    real release implementation.
    """
    guard = "if (@(Get-Process -Name 'travelling' -ErrorAction SilentlyContinue).Count -gt 0) {"
    text = source.read_text(encoding="utf-8-sig")
    if text.count(guard) != 1:
        raise AssertionError(f"expected exactly one live-process guard in {source}")
    text = text.replace(guard, "if ($false) { # QA sandbox: do not inspect host processes")
    destination.write_text(text, encoding="utf-8-sig")


def build_package(case_root: Path) -> Path:
    package = case_root / "package"
    payload_root = package / "payload"
    installer_root = package / "installer"
    package.mkdir(parents=True)
    installer_root.mkdir()
    copy_script_for_sandbox(INSTALLER, installer_root / "安装汉化.ps1")
    copy_script_for_sandbox(UNINSTALLER, installer_root / "卸载汉化.ps1")
    shutil.copy2(RESOLVER, installer_root / "Resolve-GamePath.ps1")
    shutil.copy2(README, package / "README_安装说明.md")
    write_bytes(package / "术语表与译名说明.md", b"# synthetic terminology notes\n")

    for relative in OUTER_FILES[4:]:
        write_bytes(package / relative, f"synthetic fixture: {relative}\n".encode("utf-8"))
    for relative, data in PAYLOAD.items():
        write_bytes(payload_root / relative, data)

    files = [
        {
            "path": relative.replace("/", "\\"),
            "sha256": sha256(data),
            "size": len(data),
        }
        for relative, data in PAYLOAD.items()
    ]
    outer = []
    for relative in OUTER_FILES:
        path = package / relative
        outer.append(
            {
                "path": relative.replace("/", "\\"),
                "sha256": file_hash(path),
                "size": path.stat().st_size,
            }
        )
    manifest = {
        "schema_version": 2,
        "patch_version": "1.2.5-test",
        "files": files,
        "outer_files": outer,
    }
    (package / "payload-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8-sig"
    )
    return package


def make_game(case_root: Path) -> Path:
    game = case_root / "game"
    write_bytes(game / "travelling.exe", b"synthetic game marker\n")
    write_bytes(game / "version.txt", b"2026.8.j.33\n")
    return game


def decode_output(data: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "utf-16-le"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def run_script(script: Path, game: Path) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ.copy()
    environment["POWERSHELL_TELEMETRY_OPTOUT"] = "1"
    return subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-GamePath",
            str(game),
        ],
        cwd=script.parent,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def install(package: Path, game: Path, expected: int = 0) -> str:
    result = run_script(package / "installer" / "安装汉化.ps1", game)
    output = decode_output(result.stdout)
    if result.returncode != expected:
        raise AssertionError(
            f"installer exit {result.returncode}, expected {expected}: {output[-1200:]}"
        )
    return output


def uninstall(package: Path, game: Path, expected: int = 0) -> str:
    result = run_script(package / "installer" / "卸载汉化.ps1", game)
    output = decode_output(result.stdout)
    if result.returncode != expected:
        raise AssertionError(
            f"uninstaller exit {result.returncode}, expected {expected}: {output[-1200:]}"
        )
    return output


def assert_payload_absent(game: Path) -> int:
    assertions = 0
    for relative in PAYLOAD:
        assert not (game / relative).is_file(), relative
        assertions += 1
    return assertions


def assert_payload_exact(game: Path) -> int:
    assertions = 0
    for relative, data in PAYLOAD.items():
        assert (game / relative).read_bytes() == data, relative
        assertions += 1
    return assertions


def seed_existing_bepinex(game: Path) -> dict[str, bytes]:
    originals = {
        "winhttp.dll": b"pre-existing doorstop\n",
        "doorstop_config.ini": b"pre-existing config\n",
        "BepInEx/core/BepInEx.dll": b"pre-existing BepInEx\n",
    }
    for relative, data in originals.items():
        write_bytes(game / relative, data)
    return originals


def case_clean(package: Path, game: Path) -> int:
    install(package, game)
    assertions = assert_payload_exact(game)
    state = json.loads((game / STATE_NAME).read_text(encoding="utf-8-sig"))
    assert state["installation_complete"] is True
    assertions += 1
    uninstall(package, game)
    assertions += assert_payload_absent(game)
    assert not (game / STATE_NAME).exists()
    return assertions + 1


def case_existing_bepinex(package: Path, game: Path) -> int:
    originals = seed_existing_bepinex(game)
    install(package, game)
    state = json.loads((game / STATE_NAME).read_text(encoding="utf-8-sig"))
    assert state["files"]
    assert all(
        item["path"].lower().startswith("bepinex\\plugins\\travellingcn\\")
        for item in state["files"]
    )
    assertions = 2
    for relative, data in originals.items():
        assert (game / relative).read_bytes() == data
        assertions += 1
    uninstall(package, game)
    for relative, data in originals.items():
        assert (game / relative).read_bytes() == data
        assertions += 1
    for relative in PAYLOAD:
        if relative not in originals:
            assert not (game / relative).exists()
            assertions += 1
    assert not (game / STATE_NAME).exists()
    return assertions + 1


def case_unknown_winhttp_conflict(package: Path, game: Path) -> int:
    original = b"unrelated injector\n"
    write_bytes(game / "winhttp.dll", original)
    output = install(package, game, expected=1)
    assert (game / "winhttp.dll").read_bytes() == original
    assert not (game / STATE_NAME).exists()
    assert "BepInEx" in output or "Mod" in output
    return 3


def case_partial_bepinex_missing_config(package: Path, game: Path) -> int:
    write_bytes(game / "BepInEx/core/BepInEx.dll", b"partial core\n")
    write_bytes(game / "winhttp.dll", b"partial doorstop\n")
    output = install(package, game, expected=1)
    assert not (game / STATE_NAME).exists()
    assert not (game / "BepInEx/plugins/TravellingCN/TravellingCN.dll").exists()
    assert "BepInEx" in output
    return 3


def case_partial_bepinex_missing_winhttp(package: Path, game: Path) -> int:
    write_bytes(game / "BepInEx/core/BepInEx.dll", b"partial core\n")
    write_bytes(game / "doorstop_config.ini", b"partial config\n")
    output = install(package, game, expected=1)
    assert not (game / STATE_NAME).exists()
    assert not (game / "BepInEx/plugins/TravellingCN/TravellingCN.dll").exists()
    assert "BepInEx" in output
    return 3


def case_tampered_created_file_preserved(package: Path, game: Path) -> int:
    install(package, game)
    target = game / "BepInEx/plugins/TravellingCN/catalog.zh-CN.json"
    tampered = b'{"user":"modified after install"}\n'
    target.write_bytes(tampered)
    uninstall(package, game)
    assert target.read_bytes() == tampered
    assert (game / STATE_NAME).exists()
    # Other unmodified created files are still safely removed.
    assert not (game / "BepInEx/plugins/TravellingCN/TravellingCN.dll").exists()
    return 3


def case_tampered_replaced_file_preserved(package: Path, game: Path) -> int:
    seed_existing_bepinex(game)
    target = game / "BepInEx/plugins/TravellingCN/TravellingCN.dll"
    original = b"pre-existing user plugin\n"
    write_bytes(target, original)
    install(package, game)
    tampered = b"user modified replacement after install\n"
    target.write_bytes(tampered)
    uninstall(package, game)
    assert target.read_bytes() == tampered
    assert (game / STATE_NAME).exists()
    backups = list((game / ".travelling-cn-backup").rglob("TravellingCN.dll"))
    assert len(backups) == 1 and backups[0].read_bytes() == original
    return 3


@contextmanager
def exclusive_windows_handle(path: Path) -> Iterator[None]:
    if os.name != "nt":
        raise RuntimeError("exclusive lock case requires Windows")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    create_file.restype = ctypes.c_void_p
    # Permit concurrent readers so preflight hash and backup succeed, but deny
    # delete/write sharing so the final atomic replacement fails.
    handle = create_file(str(path), 0x80000000, 0x00000001, None, 3, 0x80, None)
    invalid = ctypes.c_void_p(-1).value
    if handle == invalid:
        raise OSError(ctypes.get_last_error(), f"CreateFileW failed for {path}")
    try:
        yield
    finally:
        if not kernel32.CloseHandle(handle):
            raise OSError(ctypes.get_last_error(), "CloseHandle failed")


def case_locked_failure_rollback_retry(package: Path, game: Path) -> int:
    originals = seed_existing_bepinex(game)
    locked = game / "BepInEx/plugins/TravellingCN/catalog.zh-CN.json"
    original_catalog = b'{"preexisting":"catalog"}\n'
    write_bytes(locked, original_catalog)
    with exclusive_windows_handle(locked):
        output = install(package, game, expected=1)
    assert "恢复" in output or "安装" in output
    assert (game / STATE_NAME).exists()
    interrupted_state = json.loads((game / STATE_NAME).read_text(encoding="utf-8-sig"))
    entries = {entry["path"].replace("\\", "/"): entry for entry in interrupted_state["files"]}
    catalog_entry = entries["BepInEx/plugins/TravellingCN/catalog.zh-CN.json"]
    assert catalog_entry["action"] == "replaced"
    assert catalog_entry["applied"] is False
    assert Path(catalog_entry["backup"]).read_bytes() == original_catalog
    dll_entry = entries["BepInEx/plugins/TravellingCN/TravellingCN.dll"]
    assert dll_entry["action"] == "created" and dll_entry["applied"] is True
    assertions = 6

    # Retrying without first rolling back must be rejected by the durable state
    # guard, so a second attempt cannot trample the recovery record.
    install(package, game, expected=1)
    assert (game / STATE_NAME).exists()
    assertions += 1

    uninstall(package, game)
    assert locked.read_bytes() == original_catalog
    assert not (game / STATE_NAME).exists()
    assertions += 2

    # A clean retry after releasing the lock must complete, and uninstall must
    # restore the pre-existing plugin file as well as preserve the loader.
    install(package, game)
    assert locked.read_bytes() == PAYLOAD["BepInEx/plugins/TravellingCN/catalog.zh-CN.json"]
    uninstall(package, game)
    assert locked.read_bytes() == original_catalog
    assertions += 2
    for relative, data in originals.items():
        assert (game / relative).read_bytes() == data
        assertions += 1
    assert not (game / STATE_NAME).exists()
    return assertions + 1


CASES: tuple[tuple[str, Callable[[Path, Path], int]], ...] = (
    ("clean_install_uninstall", case_clean),
    ("existing_bepinex_plugin_only", case_existing_bepinex),
    ("unknown_winhttp_conflict_rejected", case_unknown_winhttp_conflict),
    ("partial_bepinex_missing_config_rejected", case_partial_bepinex_missing_config),
    ("partial_bepinex_missing_winhttp_rejected", case_partial_bepinex_missing_winhttp),
    ("tampered_created_file_preserved", case_tampered_created_file_preserved),
    ("tampered_replaced_file_preserved", case_tampered_replaced_file_preserved),
    ("locked_failure_rollback_retry", case_locked_failure_rollback_retry),
)


def write_evidence(results: list[Result]) -> None:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    passed = sum(result.status == "passed" for result in results)
    assertions = sum(result.assertions for result in results)
    payload = {
        "schema_version": 1,
        "platform": sys.platform,
        "powershell": "Windows PowerShell 5.1",
        "scope": "disposable workspace sandboxes; real game directory untouched",
        "passed": passed,
        "failed": len(results) - passed,
        "assertions": assertions,
        "cases": [asdict(result) for result in results],
        "known_gap": (
            "The interruption path is induced by an exclusive Windows file lock. "
            "A hard power-loss/process-kill at every individual write boundary is not injected."
        ),
    }
    (EVIDENCE_ROOT / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# v1.2.5 安装/卸载沙箱矩阵",
        "",
        f"- 结果：{passed}/{len(results)} 场景通过，{assertions} 项断言。",
        "- 范围：仅工作区一次性假游戏目录；未操作真实 Steam 游戏目录。",
        "- 环境：Windows PowerShell 5.1。",
        "",
        "| 场景 | 结果 | 断言 | 说明 |",
        "|---|---:|---:|---|",
    ]
    for result in results:
        lines.append(
            f"| `{result.case}` | {result.status} | {result.assertions} | {result.detail} |"
        )
    lines.extend(
        [
            "",
            "## 已知缺口",
            "",
            "中断恢复由 Windows 独占文件锁触发真实 I/O 失败来覆盖，并完成回滚、解锁、重装、再卸载闭环；未逐一注入进程被强杀或断电发生在每个状态写入边界的情况。",
            "",
        ]
    )
    (EVIDENCE_ROOT / "results.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    results: list[Result] = []
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sandbox-", dir=EVIDENCE_ROOT) as temporary:
        root = Path(temporary)
        for name, function in CASES:
            case_root = root / name
            package = build_package(case_root)
            game = make_game(case_root)
            try:
                assertions = function(package, game)
            except Exception as error:  # evidence must include all matrix rows
                results.append(Result(name, "failed", 0, str(error).replace("|", "\\|")))
            else:
                results.append(Result(name, "passed", assertions, "预期保护与恢复行为均成立"))
    write_evidence(results)
    passed = sum(result.status == "passed" for result in results)
    assertions = sum(result.assertions for result in results)
    print(f"install matrix: {passed}/{len(results)} passed; assertions={assertions}")
    for result in results:
        print(f"  {result.status:6} {result.case}: {result.detail}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
