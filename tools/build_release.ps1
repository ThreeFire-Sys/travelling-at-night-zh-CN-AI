param(
    [string]$Version = '2.6.3',
    [string]$SupportedGameVersion = '2026.8.l.43',
    [string]$BakedAssetsDir = 'build\baked_assets',
    [string]$WorklistRoot = 'build\worklist_l43\worklist.jsonl',
    [string]$TranslationsRoot = 'translations_l43',
    [string]$MergedRoot = 'build\merged_l43'
)

$ErrorActionPreference = 'Stop'
$workspace = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$distRoot = Join-Path $workspace 'dist'
$packageName = "TravellingAtNight_ZH-CN_v$Version"
$packageRoot = Join-Path $distRoot $packageName
$stagedRoot = Join-Path $workspace 'build\current_test_install\TravellingAtNight_ZH-CN_current-test'
$zipPath = Join-Path $distRoot "$packageName.zip"
$checksumPath = "$zipPath.sha256"

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

# The release and installed candidate must share one build and QA path.
$candidateBuilder = Join-Path $PSScriptRoot 'build_current_test_install.ps1'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $candidateBuilder `
    -PatchVersion $Version `
    -SupportedGameVersion $SupportedGameVersion `
    -BakedAssetsDir $BakedAssetsDir `
    -WorklistRoot $WorklistRoot `
    -TranslationsRoot $TranslationsRoot `
    -MergedRoot $MergedRoot `
    -PluginProfile baked
if ($LASTEXITCODE -ne 0) { throw 'Release candidate build failed.' }
if (-not (Test-Path -LiteralPath $stagedRoot -PathType Container)) {
    throw "Staged package not found after build: $stagedRoot"
}

New-Item -ItemType Directory -Path $distRoot -Force | Out-Null
if (Test-Path -LiteralPath $packageRoot) {
    $resolvedPackage = [System.IO.Path]::GetFullPath($packageRoot)
    $resolvedDist = [System.IO.Path]::GetFullPath($distRoot)
    if (-not $resolvedPackage.StartsWith($resolvedDist + [System.IO.Path]::DirectorySeparatorChar)) {
        throw "Refusing to clean outside dist: $resolvedPackage"
    }
    Remove-Item -LiteralPath $packageRoot -Recurse -Force
}
Copy-Item -LiteralPath $stagedRoot -Destination $packageRoot -Recurse

foreach ($artifact in @($zipPath, $checksumPath)) {
    if (Test-Path -LiteralPath $artifact -PathType Leaf) {
        Remove-Item -LiteralPath $artifact -Force
    }
}

# Archive the top-level directory so the package keeps its versioned root.
Compress-Archive -LiteralPath $packageRoot -DestinationPath $zipPath -CompressionLevel Optimal
# If the AV blocks on-disk winhttp.dll staging, inject the bytes into the zip and patch the manifest instead.
$doorstopPayload = Join-Path $packageRoot 'payload\winhttp.dll'
if (-not (Test-Path -LiteralPath $doorstopPayload -PathType Leaf)) {
    python -B (Join-Path $workspace 'tools\inject_doorstop_into_zip.py') `
        $zipPath (Join-Path $workspace 'build\bepinex_runtime\winhttp.dll') "TravellingAtNight_ZH-CN_v$Version"
    if ($LASTEXITCODE -ne 0) { throw 'Doorstop winhttp.dll zip injection failed.' }
}
python -B (Join-Path $workspace 'tools\validate_release_package.py') `
    $zipPath --expected-version $Version
if ($LASTEXITCODE -ne 0) { throw 'Independent release ZIP validation failed.' }

$zipHash = Get-Sha256Hex $zipPath
"$zipHash  $([System.IO.Path]::GetFileName($zipPath))" | `
    Set-Content -LiteralPath $checksumPath -Encoding ASCII

Write-Host "Release directory: $packageRoot"
Write-Host "Release ZIP: $zipPath"
Write-Host "SHA256: $zipHash"
