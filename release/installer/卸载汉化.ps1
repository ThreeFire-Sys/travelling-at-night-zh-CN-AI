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

# 游戏目录：显式 -GamePath 优先；未指定时自动探测（只接受含安装状态文件的目录）。
. (Join-Path $PSScriptRoot 'Resolve-GamePath.ps1')
if (-not [string]::IsNullOrWhiteSpace($GamePath)) {
    $gameRoot = [System.IO.Path]::GetFullPath($GamePath)
}
else {
    $gameRoot = Resolve-TravellingGamePath -RequireStateFile
    if (-not $gameRoot) {
        throw "未能自动定位已安装汉化的游戏目录（未找到安装状态文件）。请手动指定，例如：一键卸载.bat -GamePath `"E:\Games\steamapps\common\Travelling at Night Demo`""
    }
    Write-Host "已自动定位游戏目录：$gameRoot"
}
$statePath = Join-Path $gameRoot '.travelling-cn-install.json'
if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
    throw "未找到安装状态文件：$statePath"
}

if (@(Get-Process -Name 'travelling' -ErrorAction SilentlyContinue).Count -gt 0) {
    throw "检测到《夜游漫记》仍在运行。请先完全退出游戏，再卸载汉化。"
}

$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$skipped = [System.Collections.Generic.List[string]]::new()
$gamePrefix = $gameRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
$recordedGameRoot = [System.IO.Path]::GetFullPath([string]$state.game_root)
if (-not [string]::Equals(
    $recordedGameRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar),
    $gameRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar),
    [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "安装状态属于另一个游戏目录，拒绝卸载：$recordedGameRoot"
}
$allowedBackupRoot = [System.IO.Path]::GetFullPath((Join-Path $gameRoot '.travelling-cn-backup'))
$allowedBackupPrefix = $allowedBackupRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
$uninstallPlan = [System.Collections.Generic.List[object]]::new()
$seenTargets = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)

# Validate every recorded path before modifying any target.  A damaged state
# file must not be able to trigger a partial uninstall before its bad entry is
# discovered.
foreach ($file in $state.files) {
    $relative = [string]$file.path
    if ([System.IO.Path]::IsPathRooted($relative)) {
        throw "安装状态包含绝对路径，拒绝卸载：$relative"
    }
    $target = [System.IO.Path]::GetFullPath((Join-Path $gameRoot $relative))
    if (-not $target.StartsWith($gamePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "安装状态路径越出游戏目录，拒绝卸载：$relative"
    }
    if (-not $seenTargets.Add($target)) {
        throw "安装状态包含重复目标路径，拒绝卸载：$relative"
    }
    $action = [string]$file.action
    if ($action -notin @('created', 'replaced', 'unchanged')) {
        throw "安装状态包含未知操作，拒绝卸载：$relative ($action)"
    }
    $backup = $null
    if ($action -eq 'replaced' -and $file.backup) {
        $backup = [System.IO.Path]::GetFullPath([string]$file.backup)
        if (-not $backup.StartsWith($allowedBackupPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "安装状态中的备份路径越出允许目录，拒绝卸载：$relative"
        }
    }
    $uninstallPlan.Add([pscustomobject]@{
        relative = $relative
        target = $target
        action = $action
        applied = if ($null -ne $file.applied) { [bool]$file.applied } else { $true }
        installed_sha256 = [string]$file.installed_sha256
        original_sha256 = [string]$file.original_sha256
        backup = $backup
    })
}

foreach ($planned in $uninstallPlan) {
    try {
        $targetExists = Test-Path -LiteralPath $planned.target -PathType Leaf
        $currentHash = if ($targetExists) {
            Get-Sha256Hex $planned.target
        } else { $null }

        if ($planned.action -eq 'unchanged') {
            continue
        }

        if ($planned.action -eq 'created') {
            if (-not $targetExists) {
                continue
            }
            if ($currentHash -ne $planned.installed_sha256) {
                $skipped.Add($planned.relative)
                continue
            }
            Remove-Item -LiteralPath $planned.target -Force
            continue
        }

        if (-not $planned.backup -or -not (Test-Path -LiteralPath $planned.backup -PathType Leaf)) {
            $skipped.Add($planned.relative)
            continue
        }
        $backupHash = Get-Sha256Hex $planned.backup
        if ($planned.original_sha256 -and $backupHash -ne $planned.original_sha256) {
            $skipped.Add($planned.relative)
            continue
        }
        if ($targetExists -and $planned.original_sha256 -and $currentHash -eq $planned.original_sha256) {
            continue
        }
        if ($targetExists -and $currentHash -ne $planned.installed_sha256) {
            $skipped.Add($planned.relative)
            continue
        }

        $targetDirectory = Split-Path -Parent $planned.target
        New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
        $stagedRestore = Join-Path $targetDirectory ('.travelling-cn-restore-' + [Guid]::NewGuid().ToString('N'))
        try {
            Copy-Item -LiteralPath $planned.backup -Destination $stagedRestore
            if ((Get-Sha256Hex $stagedRestore) -ne $backupHash) {
                throw "备份暂存校验失败"
            }
            Move-Item -LiteralPath $stagedRestore -Destination $planned.target -Force
        } finally {
            if (Test-Path -LiteralPath $stagedRestore -PathType Leaf) {
                Remove-Item -LiteralPath $stagedRestore -Force -ErrorAction SilentlyContinue
            }
        }
    } catch {
        $skipped.Add($planned.relative)
        Write-Warning "处理 $($planned.relative) 时失败：$($_.Exception.Message)"
    }
}

if ($skipped.Count -eq 0) {
    Remove-Item -LiteralPath $statePath -Force
    if ($state.installation_complete -eq $false) {
        Write-Host "未完成的汉化安装已回滚；安装前被替换的文件已恢复。备份目录保留，便于人工核对。"
    } else {
        Write-Host "汉化补丁已卸载；安装前被替换的文件已恢复。备份目录保留，便于人工核对。"
    }
} else {
    Write-Warning "以下文件无法安全恢复（可能已被修改、备份缺失，或安装状态异常），未删除或覆盖："
    $skipped | ForEach-Object { Write-Warning "  $_" }
    Write-Warning "安装状态文件已保留。"
}
