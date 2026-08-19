param(
    [string]$Version = '1.2.5'
)

$ErrorActionPreference = 'Stop'
$workspace = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$packageName = "TravellingAtNight_ZH-CN_v$Version"
$packageRoot = Join-Path $workspace "dist\$packageName"
$payloadRoot = Join-Path $packageRoot 'payload'
$runtimeRoot = Join-Path $workspace 'build\bepinex_runtime'
$worklistPath = Join-Path $workspace 'build\worklist_j33_final\worklist.jsonl'
$translationsRoot = Join-Path $workspace 'build\translations_j33_v125_r2'
$mergedRoot = Join-Path $workspace 'build\merged_j33_v125_r2'
$extractionDiagnosticsPath = Join-Path $workspace 'build\extracted_j33_final\diagnostics.json'
$catalogPath = Join-Path $mergedRoot 'catalog.zh-CN.json'
$linkTargetsPath = Join-Path $mergedRoot 'link_targets.zh-CN.json'
$patternsPath = Join-Path $mergedRoot 'patterns.zh-CN.json'
$reviewCatalogPath = Join-Path $mergedRoot 'review_catalog.jsonl'
$qaReportPath = Join-Path $mergedRoot 'qa_report.json'
$consistencyReportPath = Join-Path $mergedRoot 'consistency_report.json'
$finalQaRoot = Join-Path $workspace 'build\final_qa_v125'
$qaFindingsPath = Join-Path $finalQaRoot 'findings.json'
$qaDispositionsPath = Join-Path $workspace 'qa\dispositions_v125.json'
$qaDispositionSummaryJsonPath = Join-Path $finalQaRoot 'disposition_summary.json'
$qaDispositionSummaryMarkdownPath = Join-Path $finalQaRoot 'disposition_summary.md'
$pluginPath = Join-Path $workspace 'src\TravellingCN\bin\Release\netstandard2.1\TravellingCN.dll'
$thirdPartyLicenseRoot = Join-Path $workspace 'build\licenses'
$thirdPartyLicenseFiles = @(
    'BepInExHarmony-MIT.txt',
    'HarmonyX-MIT.txt',
    'Harmony-original-MIT.txt',
    'MonoMod-MIT.txt',
    'MonoCecil-MIT.txt',
    'UnityDoorstop-LGPL-2.1.txt',
    'UnityDoorstop-v4.5.0-source.zip'
)

python -B (Join-Path $workspace 'tools\merge_and_validate_translations.py') `
    $worklistPath `
    $translationsRoot `
    $mergedRoot `
    --link-targets (Join-Path $workspace 'glossary\link_targets.csv')
if ($LASTEXITCODE -ne 0) { throw '翻译合并或结构 QA 失败。' }

python -B (Join-Path $workspace 'tools\test_translation_text_integrity.py') --translations $translationsRoot
if ($LASTEXITCODE -ne 0) { throw '专项 QA 失败：test_translation_text_integrity.py' }
python -B (Join-Path $workspace 'tools\test_control_markup_integrity.py') --translations $translationsRoot
if ($LASTEXITCODE -ne 0) { throw '专项 QA 失败：test_control_markup_integrity.py' }
python -B (Join-Path $workspace 'tools\test_conversation_titles.py')
if ($LASTEXITCODE -ne 0) { throw '专项 QA 失败：test_conversation_titles.py' }
python -B (Join-Path $workspace 'tools\test_rendered_link_fallback.py') --worklist $worklistPath --catalog $catalogPath --links $linkTargetsPath
if ($LASTEXITCODE -ne 0) { throw '专项 QA 失败：test_rendered_link_fallback.py' }
python -B (Join-Path $workspace 'tools\test_steam_official_terms.py') --translations $translationsRoot
if ($LASTEXITCODE -ne 0) { throw '专项 QA 失败：test_steam_official_terms.py' }
python -B (Join-Path $workspace 'tools\test_spatial_viewpoint.py') --translations $translationsRoot
if ($LASTEXITCODE -ne 0) { throw '专项 QA 失败：test_spatial_viewpoint.py' }
python -B (Join-Path $workspace 'tools\test_runtime_features.py')
if ($LASTEXITCODE -ne 0) { throw '专项 QA 失败：test_runtime_features.py' }

python -B (Join-Path $workspace 'tools\audit_translation_consistency.py') `
    $reviewCatalogPath `
    (Join-Path $workspace 'glossary\glossary.csv') `
    --json-output $consistencyReportPath `
    --fail-on error
if ($LASTEXITCODE -ne 0) { throw '术语与中文一致性 QA 失败。' }

$qaReport = Get-Content -LiteralPath $qaReportPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([int]$qaReport.expected -ne [int]$qaReport.translated -or
    [int]$qaReport.errors -ne 0 -or
    @($qaReport.unmapped_link_targets).Count -ne 0) {
    throw '翻译目录未达到可构建条件。'
}

python -B (Join-Path $workspace 'tools\generate_qa_findings.py') `
    --structural-report $qaReportPath `
    --consistency-report $consistencyReportPath `
    --extraction-diagnostics $extractionDiagnosticsPath `
    --worklist $worklistPath `
    --catalog $catalogPath `
    --output $qaFindingsPath
if ($LASTEXITCODE -ne 0) { throw '最终 QA findings 生成失败。' }

python -B (Join-Path $workspace 'tools\validate_qa_dispositions.py') `
    --findings $qaFindingsPath `
    --dispositions $qaDispositionsPath `
    --output-json $qaDispositionSummaryJsonPath `
    --output-md $qaDispositionSummaryMarkdownPath
if ($LASTEXITCODE -ne 0) { throw '最终 QA disposition 严格校验失败。' }

foreach ($required in @(
    (Join-Path $runtimeRoot 'winhttp.dll'),
    (Join-Path $runtimeRoot 'doorstop_config.ini'),
    $catalogPath,
    $linkTargetsPath,
    $patternsPath,
    (Join-Path $workspace 'build\NotoSansCJKsc-Regular.otf'),
    (Join-Path $workspace 'build\NotoSansSC-OFL.txt'),
    (Join-Path $workspace 'build\BepInEx-LICENSE.txt'),
    (Join-Path $workspace 'docs\THIRD_PARTY_NOTICES.md')
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "缺少构建输入：$required"
    }
}
foreach ($licenseFile in $thirdPartyLicenseFiles) {
    $requiredLicense = Join-Path $thirdPartyLicenseRoot $licenseFile
    if (-not (Test-Path -LiteralPath $requiredLicense -PathType Leaf)) {
        throw "缺少第三方许可证或对应源代码：$requiredLicense"
    }
}

dotnet build (Join-Path $workspace 'src\TravellingCN\TravellingCN.csproj') -c Release --no-restore
if ($LASTEXITCODE -ne 0) { throw 'TravellingCN 插件构建失败。' }
if (-not (Test-Path -LiteralPath $pluginPath -PathType Leaf)) {
    throw "插件构建完成后仍未找到输出：$pluginPath"
}

if (Test-Path -LiteralPath $packageRoot) {
    $resolvedPackage = [System.IO.Path]::GetFullPath($packageRoot)
    $resolvedDist = [System.IO.Path]::GetFullPath((Join-Path $workspace 'dist'))
    if (-not $resolvedPackage.StartsWith($resolvedDist + [System.IO.Path]::DirectorySeparatorChar)) {
        throw "拒绝清理工作区外目录：$resolvedPackage"
    }
    Remove-Item -LiteralPath $resolvedPackage -Recurse -Force
}

New-Item -ItemType Directory -Path $payloadRoot -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $runtimeRoot 'winhttp.dll') -Destination $payloadRoot
Copy-Item -LiteralPath (Join-Path $runtimeRoot 'doorstop_config.ini') -Destination $payloadRoot
Copy-Item -LiteralPath (Join-Path $runtimeRoot '.doorstop_version') -Destination $payloadRoot
Copy-Item -LiteralPath (Join-Path $runtimeRoot 'changelog.txt') -Destination $payloadRoot
Copy-Item -LiteralPath (Join-Path $runtimeRoot 'BepInEx') -Destination $payloadRoot -Recurse

$pluginRoot = Join-Path $payloadRoot 'BepInEx\plugins\TravellingCN'
New-Item -ItemType Directory -Path (Join-Path $pluginRoot 'font') -Force | Out-Null
Copy-Item -LiteralPath $pluginPath -Destination $pluginRoot -Force
Copy-Item -LiteralPath $catalogPath -Destination $pluginRoot -Force
Copy-Item -LiteralPath $linkTargetsPath -Destination $pluginRoot -Force
Copy-Item -LiteralPath $patternsPath -Destination $pluginRoot -Force
Copy-Item -LiteralPath (Join-Path $workspace 'build\NotoSansCJKsc-Regular.otf') -Destination (Join-Path $pluginRoot 'font') -Force
Copy-Item -LiteralPath (Join-Path $workspace 'build\NotoSansSC-OFL.txt') -Destination (Join-Path $pluginRoot 'font\OFL.txt') -Force

$licenseRoot = Join-Path $packageRoot 'licenses'
New-Item -ItemType Directory -Path $licenseRoot -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $workspace 'build\BepInEx-LICENSE.txt') -Destination (Join-Path $licenseRoot 'BepInEx-MIT.txt')
Copy-Item -LiteralPath (Join-Path $workspace 'build\NotoSansSC-OFL.txt') -Destination (Join-Path $licenseRoot 'NotoSansSC-OFL.txt')
Copy-Item -LiteralPath (Join-Path $workspace 'docs\THIRD_PARTY_NOTICES.md') -Destination (Join-Path $licenseRoot 'THIRD_PARTY_NOTICES.md')
foreach ($licenseFile in $thirdPartyLicenseFiles) {
    Copy-Item -LiteralPath (Join-Path $thirdPartyLicenseRoot $licenseFile) -Destination $licenseRoot
}
$installerRoot = Join-Path $packageRoot 'installer'
New-Item -ItemType Directory -Force -Path $installerRoot | Out-Null
Copy-Item -LiteralPath (Join-Path $workspace 'release\installer\安装汉化.ps1') -Destination $installerRoot
Copy-Item -LiteralPath (Join-Path $workspace 'release\installer\卸载汉化.ps1') -Destination $installerRoot
Copy-Item -LiteralPath (Join-Path $workspace 'release\README_安装说明.md') -Destination $packageRoot
Copy-Item -LiteralPath (Join-Path $workspace 'docs\USER_GLOSSARY.md') -Destination (Join-Path $packageRoot '术语表与译名说明.md')

$files = Get-ChildItem -LiteralPath $payloadRoot -Recurse -File | ForEach-Object {
    [pscustomobject]@{
        path = $_.FullName.Substring($payloadRoot.Length + 1)
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
        size = $_.Length
    }
}
$outerFiles = Get-ChildItem -LiteralPath $packageRoot -Recurse -File | Where-Object {
    -not $_.FullName.StartsWith($payloadRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase) -and
    $_.Name -ne 'payload-manifest.json'
} | ForEach-Object {
    [pscustomobject]@{
        path = $_.FullName.Substring($packageRoot.Length + 1)
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
        size = $_.Length
    }
}
$manifest = [pscustomobject]@{
    schema_version = 2
    patch_version = $Version
    supported_game_version = '2026.8.j.33'
    unity_version = '6000.4.0f1'
    bepinex_version = '5.4.23.5'
    bepinex_archive_sha256 = '82F9878551030F54657792C0740D9D51A09500EEAE1FBA21106B0C441E6732C4'
    noto_sans_sc_sha256 = '2C76254F6FC379FDDFCE0A7E84FB5385BB135D3E399294F6EEB6680D0365B74B'
    translation_count = [int]$qaReport.translated
    translation_qa_errors = [int]$qaReport.errors
    translation_qa_warnings = [int]$qaReport.warnings
    source_hashes = [pscustomobject]@{
        travelling_exe = 'A6E696D168F2F6A39325A6585CCC0F09C2F28F90F38941D88F6A8ABE5A283EF3'
        resources_assets = 'FF5E032DD0C909E89D24A1075375B3D0D024A33B9BF8BF3E8DE36C56E722A7D7'
        travelling_scripts_dll = 'BDC19B413A5EFA2C646D99576CD7B2459894068156DF65386FB196E962508670'
        dialogue_system_dll = '6CAB0C45F3CD31F317DB28DD200CD4B978489CADD5575654E46F66ACC73F14EF'
    }
    files = @($files)
    outer_files = @($outerFiles)
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $packageRoot 'payload-manifest.json') -Encoding UTF8

$zipPath = Join-Path $workspace "dist\$packageName.zip"
$zipChecksumPath = "$zipPath.sha256"
if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
if (Test-Path -LiteralPath $zipChecksumPath) { Remove-Item -LiteralPath $zipChecksumPath -Force }
Compress-Archive -LiteralPath $packageRoot -DestinationPath $zipPath -CompressionLevel Optimal

python -B (Join-Path $workspace 'tools\validate_release_package.py') `
    $zipPath `
    --expected-version $Version
if ($LASTEXITCODE -ne 0) { throw '发布 ZIP 独立校验失败。' }

$zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash
"$zipHash  $([System.IO.Path]::GetFileName($zipPath))" | `
    Set-Content -LiteralPath $zipChecksumPath -Encoding ASCII

Write-Host "发布包：$zipPath"
Write-Host "校验和：$zipChecksumPath"
