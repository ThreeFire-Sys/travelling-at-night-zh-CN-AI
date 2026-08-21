# Resolve-GamePath.ps1 —— 定位《夜游漫记》Demo 的安装目录。
# 供 安装汉化.ps1 / 卸载汉化.ps1 以点源方式引入。
# 解析顺序：显式 -GamePath 参数（调用方处理）→ Steam 自动探测（注册表
# SteamPath → libraryfolders.vdf 全部库目录 → appmanifest_2915730.acf 的
# installdir）→ 历史默认路径。-RequireStateFile 时只接受含
# .travelling-cn-install.json 的目录（卸载器用，防止把未打补丁的目录误当目标）。

function Resolve-TravellingGamePath {
    param(
        [switch]$RequireStateFile
    )
    $candidates = [System.Collections.Generic.List[string]]::new()
    foreach ($root in (Get-SteamLibraryRoots)) {
        $steamapps = Join-Path $root 'steamapps'
        $manifest = Join-Path $steamapps 'appmanifest_2915730.acf'
        if (Test-Path -LiteralPath $manifest -PathType Leaf) {
            $installDir = Get-AcfInstallDir $manifest
            if (-not [string]::IsNullOrWhiteSpace($installDir)) {
                $candidates.Add((Join-Path (Join-Path $steamapps 'common') $installDir))
            }
        }
        # 清单缺失时的兜底：库目录下的惯用目录名。
        $candidates.Add((Join-Path $steamapps 'common\Travelling at Night Demo'))
    }
    # 历史默认路径（v2.3.4 之前安装器写死的路径）。
    $candidates.Add('D:\Steam\steamapps\common\Travelling at Night Demo')

    $seen = @{}
    foreach ($candidate in $candidates) {
        $full = [System.IO.Path]::GetFullPath($candidate)
        $key = $full.ToUpperInvariant()
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true
        if (-not (Test-Path -LiteralPath (Join-Path $full 'travelling.exe') -PathType Leaf)) { continue }
        if ($RequireStateFile -and
            -not (Test-Path -LiteralPath (Join-Path $full '.travelling-cn-install.json') -PathType Leaf)) { continue }
        return $full
    }
    return $null
}

function Get-SteamLibraryRoots {
    $roots = [System.Collections.Generic.List[string]]::new()
    $steamPath = $null
    foreach ($key in 'HKCU:\Software\Valve\Steam', 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam') {
        try {
            $props = Get-ItemProperty -LiteralPath $key -ErrorAction Stop
            foreach ($name in 'SteamPath', 'InstallPath') {
                $value = $props.$name
                if (-not [string]::IsNullOrWhiteSpace([string]$value)) {
                    $steamPath = [string]$value
                    break
                }
            }
        }
        catch { }
        if ($steamPath) { break }
    }
    if (-not $steamPath) { return $roots }
    $roots.Add($steamPath)
    $vdf = Join-Path $steamPath 'steamapps\libraryfolders.vdf'
    if (Test-Path -LiteralPath $vdf -PathType Leaf) {
        $text = Get-Content -LiteralPath $vdf -Raw
        foreach ($m in [regex]::Matches($text, '"path"\s+"([^"]+)"')) {
            $p = $m.Groups[1].Value -replace '\\', '\'
            if (-not [string]::IsNullOrWhiteSpace($p) -and $p -ne $steamPath) { $roots.Add($p) }
        }
    }
    return $roots
}

function Get-AcfInstallDir {
    param([string]$ManifestPath)
    $text = Get-Content -LiteralPath $ManifestPath -Raw
    $m = [regex]::Match($text, '"installdir"\s+"([^"]+)"')
    if ($m.Success) { return $m.Groups[1].Value }
    return $null
}
