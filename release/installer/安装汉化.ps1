param(
    [string]$GamePath = ''
)

$ErrorActionPreference = 'Stop'
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop

function Get-Sha256Hex {
    param([string]$Path)
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try {
            return ([System.BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '')
        }
        finally {
            $sha.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
}
# 脚本位于发布包的 installer\ 子目录（不对用户外露），包根目录取其上一级。
$releaseRoot = Split-Path -Parent $PSScriptRoot
$payloadRoot = Join-Path $releaseRoot 'payload'
$manifestPath = Join-Path $releaseRoot 'payload-manifest.json'

# 游戏目录：显式 -GamePath 优先；未指定时自动探测（Steam 库目录 + 历史默认路径）。
. (Join-Path $PSScriptRoot 'Resolve-GamePath.ps1')
if (-not [string]::IsNullOrWhiteSpace($GamePath)) {
    $gameRoot = [System.IO.Path]::GetFullPath($GamePath)
    if (-not (Test-Path -LiteralPath (Join-Path $gameRoot 'travelling.exe') -PathType Leaf)) {
        throw "未在目标目录找到 travelling.exe：$gameRoot"
    }
}
else {
    $gameRoot = Resolve-TravellingGamePath
    if (-not $gameRoot) {
        throw "未能自动定位《夜游漫记》Demo 的安装目录（已尝试 Steam 库目录与历史默认路径）。请手动指定，例如：一键安装.bat -GamePath `"E:\Games\steamapps\common\Travelling at Night Demo`""
    }
    Write-Host "已自动定位游戏目录：$gameRoot"
}
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "发布包缺少 payload-manifest.json。"
}

if (@(Get-Process -Name 'travelling' -ErrorAction SilentlyContinue).Count -gt 0) {
    throw "检测到《夜游漫记》仍在运行。请先完全退出游戏，再安装或升级汉化。"
}

$statePath = Join-Path $gameRoot '.travelling-cn-install.json'
if (Test-Path -LiteralPath $statePath -PathType Leaf) {
    throw "检测到现有汉化安装状态。为保留可恢复的原始文件，请先运行卸载脚本，再安装或升级补丁：$statePath"
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ([int]$manifest.schema_version -ne 2 -or [string]::IsNullOrWhiteSpace([string]$manifest.patch_version)) {
    throw "payload-manifest.json 的结构或补丁版本无效。"
}
$gameVersionPath = Join-Path $gameRoot 'version.txt'
$supportedGameVersion = [string]$manifest.supported_game_version
if ((Test-Path -LiteralPath $gameVersionPath) -and -not [string]::IsNullOrWhiteSpace($supportedGameVersion)) {
    $gameVersion = (Get-Content -LiteralPath $gameVersionPath -Raw).Trim()
    if ($gameVersion -ne $supportedGameVersion) {
        Write-Warning "当前游戏版本为 $gameVersion；本补丁验证版本为 $supportedGameVersion。将依靠原文精确匹配安全降级。"
    }
}
if (@($manifest.files).Count -eq 0) {
    throw "payload-manifest.json 不含任何待安装文件。"
}
if (@($manifest.outer_files).Count -eq 0) {
    throw "payload-manifest.json 不含外层文件完整性清单。"
}

# Schema v2 binds the installer, uninstaller, README and every redistributed
# license/source archive. Validate the exact outer-file set before touching the
# game directory, including this script itself.
$requiredOuter = @(
    'installer\安装汉化.ps1',
    'installer\卸载汉化.ps1',
    'installer\Resolve-GamePath.ps1',
    '一键安装.bat',
    '一键卸载.bat',
    'README_安装说明.md',
    '术语表与译名说明.md',
    '术语表与译名说明.txt',
    'licenses\BepInEx-MIT.txt',
    'licenses\NotoSansSC-OFL.txt',
    'licenses\THIRD_PARTY_NOTICES.md',
    'licenses\BepInExHarmony-MIT.txt',
    'licenses\HarmonyX-MIT.txt',
    'licenses\Harmony-original-MIT.txt',
    'licenses\MonoMod-MIT.txt',
    'licenses\MonoCecil-MIT.txt',
    'licenses\UnityDoorstop-LGPL-2.1.txt',
    'licenses\UnityDoorstop-v4.5.0-source.zip'
)
$releaseRoot = [System.IO.Path]::GetFullPath($releaseRoot)
$releasePrefix = $releaseRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
$declaredOuter = [System.Collections.Generic.Dictionary[string, object]]::new([System.StringComparer]::OrdinalIgnoreCase)
foreach ($file in $manifest.outer_files) {
    $relative = [string]$file.path
    if ([string]::IsNullOrWhiteSpace($relative) -or [System.IO.Path]::IsPathRooted($relative)) {
        throw "外层文件清单包含无效路径：$relative"
    }
    $source = [System.IO.Path]::GetFullPath((Join-Path $releaseRoot $relative))
    if (-not $source.StartsWith($releasePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "外层文件清单路径越出发布目录：$relative"
    }
    if ($relative.StartsWith('payload\', [System.StringComparison]::OrdinalIgnoreCase) -or
        $relative -eq 'payload-manifest.json' -or
        $declaredOuter.ContainsKey($relative)) {
        throw "外层文件清单包含重复或保留路径：$relative"
    }
    $declaredOuter.Add($relative, $file)
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "发布包缺少外层文件：$relative"
    }
    $sourceInfo = Get-Item -LiteralPath $source
    if ($sourceInfo.Length -ne [long]$file.size -or
        (Get-Sha256Hex $source) -ne [string]$file.sha256) {
        throw "发布包外层文件完整性校验失败：$relative"
    }
}
$requiredOuterSet = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
foreach ($relative in $requiredOuter) {
    [void]$requiredOuterSet.Add($relative)
}
if ($declaredOuter.Count -ne $requiredOuterSet.Count) {
    throw "外层文件清单成员数量无效。"
}
foreach ($relative in $requiredOuterSet) {
    if (-not $declaredOuter.ContainsKey($relative)) {
        throw "外层文件清单缺少必需文件：$relative"
    }
}
$actualOuter = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
Get-ChildItem -LiteralPath $releaseRoot -Recurse -File | ForEach-Object {
    $relative = $_.FullName.Substring($releaseRoot.Length + 1)
    if (-not $relative.StartsWith('payload\', [System.StringComparison]::OrdinalIgnoreCase) -and
        $relative -ne 'payload-manifest.json') {
        if (-not $actualOuter.Add($relative)) {
            throw "发布目录包含大小写重复的外层路径：$relative"
        }
    }
}
if (-not $actualOuter.SetEquals($declaredOuter.Keys)) {
    throw "发布目录的外层文件集合与清单不一致。"
}
$requiredPayload = @(
    'BepInEx\plugins\TravellingCN\TravellingCN.dll',
    'BepInEx\plugins\TravellingCN\catalog.zh-CN.json',
    'BepInEx\plugins\TravellingCN\link_targets.zh-CN.json',
    'BepInEx\plugins\TravellingCN\font\NotoSansCJKsc-Regular.otf'
)
$manifestPaths = @($manifest.files | ForEach-Object { [string]$_.path })
foreach ($required in $requiredPayload) {
    if ($manifestPaths -notcontains $required) {
        throw "payload-manifest.json 缺少必需文件：$required"
    }
}
$payloadRoot = [System.IO.Path]::GetFullPath($payloadRoot)
$payloadPrefix = $payloadRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
$gamePrefix = $gameRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
$existingBepInEx = Test-Path -LiteralPath (Join-Path $gameRoot 'BepInEx\core\BepInEx.dll') -PathType Leaf
if ($existingBepInEx) {
    $existingDoorstop = (Test-Path -LiteralPath (Join-Path $gameRoot 'winhttp.dll') -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $gameRoot 'doorstop_config.ini') -PathType Leaf)
    if (-not $existingDoorstop) {
        throw "检测到残缺的 BepInEx：存在核心 DLL，但缺少 winhttp.dll 或 doorstop_config.ini。为避免生成无法启动的安装，已停止。"
    }
}
if (-not $existingBepInEx) {
    foreach ($conflict in @('winhttp.dll', 'doorstop_config.ini')) {
        if (Test-Path -LiteralPath (Join-Path $gameRoot $conflict)) {
            throw "检测到现有注入器文件 $conflict，但未检测到 BepInEx。为避免覆盖其他 Mod 加载器，安装已停止。"
        }
    }
}

# Validate the complete manifest before touching the game directory.  This
# prevents a damaged/tampered file late in the manifest from leaving a
# half-installed loader behind.
$installPlan = [System.Collections.Generic.List[object]]::new()
$seenTargets = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
foreach ($file in $manifest.files) {
    $relative = [string]$file.path
    if ([System.IO.Path]::IsPathRooted($relative)) {
        throw "清单包含绝对路径，拒绝安装：$relative"
    }
    $isRuntime = -not $relative.StartsWith('BepInEx\plugins\TravellingCN\', [System.StringComparison]::OrdinalIgnoreCase)
    if ($existingBepInEx -and $isRuntime) {
        continue
    }

    $source = [System.IO.Path]::GetFullPath((Join-Path $payloadRoot $relative))
    $target = [System.IO.Path]::GetFullPath((Join-Path $gameRoot $relative))
    if (-not $source.StartsWith($payloadPrefix, [System.StringComparison]::OrdinalIgnoreCase) -or
        -not $target.StartsWith($gamePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "清单路径越出允许目录，拒绝安装：$relative"
    }
    if (-not $seenTargets.Add($target)) {
        throw "清单包含重复目标路径，拒绝安装：$relative"
    }
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "发布包缺少：$relative"
    }
    $actualSourceHash = Get-Sha256Hex $source
    if ($actualSourceHash -ne [string]$file.sha256) {
        throw "发布包校验失败：$relative"
    }
    $installPlan.Add([pscustomobject]@{
        relative = $relative
        source = $source
        target = $target
        sha256 = $actualSourceHash
    })
}

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupRoot = Join-Path $gameRoot ".travelling-cn-backup\$timestamp"
$stateEntries = [System.Collections.Generic.List[object]]::new()

$state = [pscustomobject]@{
    schema_version = 2
    patch_version = [string]$manifest.patch_version
    installation_complete = $false
    installed_at = (Get-Date).ToString('o')
    game_root = $gameRoot
    backup_root = $backupRoot
    files = $stateEntries
}

function Write-InstallState {
    $temporaryStatePath = "$statePath.tmp"
    $state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporaryStatePath -Encoding UTF8
    Move-Item -LiteralPath $temporaryStatePath -Destination $statePath -Force
}

# Create a recovery record before the first target is touched.  Each entry is
# persisted before its atomic replacement, so an interrupted install can be
# safely inspected or rolled back by the uninstaller.
Write-InstallState

try {
    foreach ($planned in $installPlan) {
        $relative = [string]$planned.relative
        $source = [string]$planned.source
        $target = [string]$planned.target
        $actualSourceHash = [string]$planned.sha256

        $targetDirectory = Split-Path -Parent $target
        New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
        $action = 'created'
        $backup = $null
        $originalHash = $null
        if (Test-Path -LiteralPath $target -PathType Leaf) {
            $originalHash = Get-Sha256Hex $target
            if ($originalHash -eq $actualSourceHash) {
                $action = 'unchanged'
            } else {
                $backup = Join-Path $backupRoot $relative
                New-Item -ItemType Directory -Path (Split-Path -Parent $backup) -Force | Out-Null
                Copy-Item -LiteralPath $target -Destination $backup -Force
                if ((Get-Sha256Hex $backup) -ne $originalHash) {
                    throw "安装前备份校验失败：$relative"
                }
                $action = 'replaced'
            }
        }

        $entry = [pscustomobject]@{
            path = $relative
            action = $action
            applied = ($action -eq 'unchanged')
            installed_sha256 = $actualSourceHash
            original_sha256 = $originalHash
            backup = $backup
        }
        $stateEntries.Add($entry)
        Write-InstallState

        if ($action -ne 'unchanged') {
            $stagedTarget = Join-Path $targetDirectory ('.travelling-cn-new-' + [Guid]::NewGuid().ToString('N'))
            try {
                Copy-Item -LiteralPath $source -Destination $stagedTarget
                if ((Get-Sha256Hex $stagedTarget) -ne $actualSourceHash) {
                    throw "安装暂存文件校验失败：$relative"
                }
                Move-Item -LiteralPath $stagedTarget -Destination $target -Force
            } finally {
                if (Test-Path -LiteralPath $stagedTarget -PathType Leaf) {
                    Remove-Item -LiteralPath $stagedTarget -Force -ErrorAction SilentlyContinue
                }
            }
            if ((Get-Sha256Hex $target) -ne $actualSourceHash) {
                throw "安装后文件校验失败：$relative"
            }
            $entry.applied = $true
            Write-InstallState
        }
    }

    $state.installation_complete = $true
    Write-InstallState
} catch {
    try { Write-InstallState } catch { }
    throw "汉化安装未完成：$($_.Exception.Message)`n恢复状态已保留在 $statePath。请关闭游戏后运行卸载脚本回滚，再重试安装。"
}

Write-Host "《夜游漫记》简体中文补丁安装完成。"
if ($existingBepInEx) {
    Write-Host "检测到现有 BepInEx，已仅安装 TravellingCN 插件，未覆盖加载器核心。"
}
Write-Host "启动游戏后可在 BepInEx\LogOutput.log 查看载入与命中统计。"
