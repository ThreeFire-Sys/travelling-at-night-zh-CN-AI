param(
    [string]$PatchVersion = '1.2.10',
    [string]$SupportedGameVersion = '2026.8.j.66',
    [string]$BakedAssetsDir = '',
    [string]$WorklistRoot = 'build\worklist_j66\worklist.jsonl',
    [string]$TranslationsRoot = 'build\translations_j66_candidate',
    [string]$MergedRoot = 'build\merged_j66_reviewed',
    [ValidateSet('runtime', 'baked')]
    [string]$PluginProfile = 'runtime'
)

$ErrorActionPreference = 'Stop'
$workspace = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$stagingRoot = Join-Path $workspace 'build\current_test_install'
$packageRoot = Join-Path $stagingRoot 'TravellingAtNight_ZH-CN_current-test'
$payloadRoot = Join-Path $packageRoot 'payload'
$runtimeRoot = Join-Path $workspace 'build\bepinex_runtime'
$worklistPath = Join-Path $workspace $WorklistRoot
$translationsRoot = Join-Path $workspace $TranslationsRoot
$mergedRoot = Join-Path $workspace $MergedRoot
$catalogPath = Join-Path $mergedRoot 'catalog.zh-CN.json'
$linkTargetsPath = Join-Path $mergedRoot 'link_targets.zh-CN.json'
$patternsPath = Join-Path $mergedRoot 'patterns.zh-CN.json'
$pluginPath = Join-Path $workspace 'src\TravellingCN\bin\Release\netstandard2.1\TravellingCN.dll'
$licenseSourceRoot = Join-Path $workspace 'build\licenses'

function Invoke-Checked {
    param([string]$FailureMessage, [scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) { throw $FailureMessage }
}

Invoke-Checked 'j.66 translation merge or structural QA failed.' {
    python -B (Join-Path $workspace 'tools\merge_and_validate_translations.py') `
        $worklistPath $translationsRoot $mergedRoot `
        --link-targets (Join-Path $workspace 'glossary\link_targets.csv')
}

$translationTests = @(
    'test_translation_text_integrity.py',
    'test_control_markup_integrity.py',
    'test_steam_official_terms.py',
    'test_spatial_viewpoint.py',
    'test_dialogue_semantic_red_flags.py'
)
foreach ($test in $translationTests) {
    Invoke-Checked "Focused QA failed: $test" {
        python -B (Join-Path $workspace "tools\$test") --translations $translationsRoot
    }
}

if ($PluginProfile -ne 'baked') {
    Invoke-Checked 'Focused QA failed: test_dynamic_label_coverage.py' {
        python -B (Join-Path $workspace 'tools\test_dynamic_label_coverage.py') `
            --worklist $worklistPath --translations $translationsRoot --catalog $catalogPath
    }
}
Invoke-Checked 'Focused QA failed: test_global_semantic_consistency.py' {
    python -B (Join-Path $workspace 'tools\test_global_semantic_consistency.py') `
        --translations $translationsRoot `
        --report (Join-Path $workspace 'build\reviews\global_semantic_consistency_j66.json')
}
Invoke-Checked 'Focused QA failed: test_mechanism_glossary_coverage.py' {
    python -B (Join-Path $workspace 'tools\test_mechanism_glossary_coverage.py') `
        --worklist $worklistPath --translations $translationsRoot `
        --report (Join-Path $workspace 'build\reviews\mechanism_glossary_coverage_j66.json')
}
Invoke-Checked 'Focused QA failed: test_quote_provenance.py' {
    python -B (Join-Path $workspace 'tools\test_quote_provenance.py') `
        --worklist $worklistPath --translations $translationsRoot `
        --report (Join-Path $workspace 'build\reviews\quote_provenance_j66.json')
}
Invoke-Checked 'Focused QA failed: test_conversation_description_provenance.py' {
    python -B (Join-Path $workspace 'tools\test_conversation_description_provenance.py') `
        --worklist $worklistPath --translations $translationsRoot `
        --report (Join-Path $workspace 'build\reviews\conversation_description_provenance_j66.json')
}
foreach ($test in @('test_runtime_features.py', 'test_conversation_titles.py')) {
    if ($PluginProfile -eq 'baked' -and $test -eq 'test_runtime_features.py') {
        continue  # 瘦身插件用 test_slim_plugin.py 校验
    }
    Invoke-Checked "Focused QA failed: $test" {
        python -B (Join-Path $workspace "tools\$test")
    }
}
if ($PluginProfile -eq 'baked') {
    Invoke-Checked 'Focused QA failed: test_slim_plugin.py' {
        python -B (Join-Path $workspace 'tools\test_slim_plugin.py')
    }
}

Invoke-Checked 'Focused QA failed: test_rendered_link_fallback.py' {
    python -B (Join-Path $workspace 'tools\test_rendered_link_fallback.py') `
        --worklist $worklistPath --catalog $catalogPath --links $linkTargetsPath
}
Invoke-Checked 'Focused QA failed: test_decorated_splice_lookup.py' {
    python -B (Join-Path $workspace 'tools\test_decorated_splice_lookup.py')
}

Invoke-Checked 'Terminology and Chinese consistency QA failed.' {
    python -B (Join-Path $workspace 'tools\audit_translation_consistency.py') `
        (Join-Path $mergedRoot 'review_catalog.jsonl') `
        (Join-Path $workspace 'glossary\glossary.csv') `
        --json-output (Join-Path $mergedRoot 'consistency_report.json') --fail-on error
}

Invoke-Checked 'TravellingCN plugin build failed.' {
    dotnet build (Join-Path $workspace 'src\TravellingCN\TravellingCN.csproj') -c Release --no-restore
}
if (-not (Test-Path -LiteralPath $pluginPath -PathType Leaf)) {
    throw "Plugin output missing after build: $pluginPath"
}

$managedRoot = 'D:\Steam\steamapps\common\Travelling at Night Demo\travelling_Data\Managed'
$methodInspector = Join-Path $workspace 'tools\inspect_managed_methods.csproj'
$travellingSignatures = & dotnet run --project $methodInspector -- --signatures `
    (Join-Path $managedRoot 'travelling.scripts.dll') `
    SetSubtitleTextContent StartTyping PlayText RestartFromIndexPreservingState `
    ComposeDisplayText ComposeWrapped ApplyPaperStripStyle get_RawLabel `
    ResolveQualityTokensAndColourizeLinks BracketsToColourizedLinks `
    WrapTextAtSpecifiedMaxWidth ForCurrentCulture
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect j.66 travelling.scripts.dll patch targets.' }
$dialogueSignatures = & dotnet run --project $methodInspector -- --signatures `
    (Join-Path $managedRoot 'DialogueSystem.dll') get_Name
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect j.66 DialogueSystem.dll patch targets.' }
$signatureText = (@($travellingSignatures) + @($dialogueSignatures)) -join "`n"
$requiredPatchTargets = @(
    'Travelling.UI.Dialogue.TravellingSubtitlePanel::SetSubtitleTextContent(PixelCrushers.DialogueSystem.Subtitle,System.Boolean)',
    'Travelling.UI.Dialogue.TravellingTypewriter::StartTyping(System.String,System.Int32)',
    'Travelling.UI.Dialogue.TravellingTypewriter::PlayText(System.String,System.Int32)',
    'Travelling.UI.Dialogue.TravellingTypewriter::RestartFromIndexPreservingState(System.String,System.Int32)',
    'Travelling.Interactables.WorldPopup::ComposeDisplayText()',
    'Travelling.Interactables.WorldPopup::ComposeWrapped(System.Collections.Generic.IEnumerable`1<System.String>,System.Int32)',
    'Travelling.Interactables.WorldPopup::ApplyPaperStripStyle()',
    'Travelling.PCQualities.Skill::get_RawLabel()',
    'Travelling.Utility.TravellingUtility::WrapTextAtSpecifiedMaxWidth(TMPro.TextMeshProUGUI,System.Single)',
    'Travelling.Loc::ForCurrentCulture(System.String)',
    'Travelling.Loc::ForCurrentCulture(System.String,System.String[])',
    'PixelCrushers.DialogueSystem.CharacterInfo::get_Name()'
)
foreach ($requiredTarget in $requiredPatchTargets) {
    if (-not $signatureText.Contains($requiredTarget)) {
        throw "j.66 runtime patch target missing: $requiredTarget"
    }
}
$linkOverloadPattern = 'ResolveQualityTokensAndColourizeLinks\(System\.String,Travelling\.UI\.Info\.LinkStyle,System\.Boolean,'
if ([regex]::Matches($signatureText, $linkOverloadPattern).Count -lt 2) {
    throw 'j.66 quality-link overload coverage is incomplete.'
}
$bracketOverloadPattern = 'BracketsToColourizedLinks\(System\.String,Travelling\.UI\.Info\.LinkStyle,System\.Boolean,System\.Predicate'
if ([regex]::Matches($signatureText, $bracketOverloadPattern).Count -lt 1) {
    throw 'j.66 generic bracket-link overload coverage is incomplete.'
}

$requiredInputs = @(
    (Join-Path $runtimeRoot 'winhttp.dll'),
    (Join-Path $runtimeRoot 'doorstop_config.ini'),
    $catalogPath,
    $linkTargetsPath,
    $patternsPath,
    (Join-Path $workspace 'build\NotoSansCJKsc-Regular.otf'),
    (Join-Path $workspace 'build\NotoSansSC-OFL.txt'),
    (Join-Path $workspace 'build\BepInEx-LICENSE.txt'),
    (Join-Path $workspace 'docs\THIRD_PARTY_NOTICES.md')
)
foreach ($required in $requiredInputs) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Missing test-install build input: $required"
    }
}

if (Test-Path -LiteralPath $packageRoot) {
    $resolvedPackage = [System.IO.Path]::GetFullPath($packageRoot)
    $resolvedStaging = [System.IO.Path]::GetFullPath($stagingRoot)
    if (-not $resolvedPackage.StartsWith($resolvedStaging + [System.IO.Path]::DirectorySeparatorChar)) {
        throw "Refusing to clean outside test staging root: $resolvedPackage"
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

if ($BakedAssetsDir -ne '') {
    # v2.0 资产级汉化：把烘焙过的序列化资产纳入 payload（travelling_Data 下）。
    # 烘焙报告必须干净——任何位点漂移都意味着资产与目录不再同步。
    $bakedRoot = [System.IO.Path]::GetFullPath((Join-Path $workspace $BakedAssetsDir))
    $bakeReportPath = Join-Path $bakedRoot 'bake_report.json'
    if (-not (Test-Path -LiteralPath $bakeReportPath -PathType Leaf)) {
        throw "Baked assets report missing: $bakeReportPath"
    }
    $bakeReport = Get-Content -LiteralPath $bakeReportPath -Raw | ConvertFrom-Json
    if (@($bakeReport.mismatches).Count -ne 0) {
        throw "Baked assets contain mismatches; rebuild the bake before packaging."
    }
    $bakedFiles = Get-ChildItem -LiteralPath $bakedRoot -File | Where-Object {
        $_.Name -ne 'bake_report.json' -and $_.Name -ne 'raw_labels.json' -and $_.Name -ne 'lang_swap.json'
    }
    if (@($bakedFiles).Count -eq 0) {
        throw "Baked assets directory is empty: $bakedRoot"
    }
    $bakedPayloadRoot = Join-Path $payloadRoot 'travelling_Data'
    New-Item -ItemType Directory -Path $bakedPayloadRoot -Force | Out-Null
    foreach ($bakedFile in $bakedFiles) {
        Copy-Item -LiteralPath $bakedFile.FullName -Destination $bakedPayloadRoot -Force
    }
    $rawLabelsPath = Join-Path $bakedRoot 'raw_labels.json'
    if (Test-Path -LiteralPath $rawLabelsPath -PathType Leaf) {
        Copy-Item -LiteralPath $rawLabelsPath -Destination $pluginRoot -Force
    }
    # F9 热切换的双向映射表随插件分发（v2.1.0 LanguageSwap）。
    $langSwapPath = Join-Path $bakedRoot 'lang_swap.json'
    if (Test-Path -LiteralPath $langSwapPath -PathType Leaf) {
        Copy-Item -LiteralPath $langSwapPath -Destination $pluginRoot -Force
    }
}

$licenseRoot = Join-Path $packageRoot 'licenses'
New-Item -ItemType Directory -Path $licenseRoot -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $workspace 'build\BepInEx-LICENSE.txt') -Destination (Join-Path $licenseRoot 'BepInEx-MIT.txt')
Copy-Item -LiteralPath (Join-Path $workspace 'build\NotoSansSC-OFL.txt') -Destination (Join-Path $licenseRoot 'NotoSansSC-OFL.txt')
Copy-Item -LiteralPath (Join-Path $workspace 'docs\THIRD_PARTY_NOTICES.md') -Destination (Join-Path $licenseRoot 'THIRD_PARTY_NOTICES.md')
foreach ($licenseFile in @(
    'BepInExHarmony-MIT.txt', 'HarmonyX-MIT.txt', 'Harmony-original-MIT.txt',
    'MonoMod-MIT.txt', 'MonoCecil-MIT.txt', 'UnityDoorstop-LGPL-2.1.txt',
    'UnityDoorstop-v4.5.0-source.zip'
)) {
    Copy-Item -LiteralPath (Join-Path $licenseSourceRoot $licenseFile) -Destination $licenseRoot
}

Copy-Item -LiteralPath (Join-Path $workspace 'release\README_安装说明.md') -Destination $packageRoot
$installerRoot = Join-Path $packageRoot 'installer'
New-Item -ItemType Directory -Force -Path $installerRoot | Out-Null
Copy-Item -LiteralPath (Join-Path $workspace 'release\installer\安装汉化.ps1') -Destination $installerRoot
Copy-Item -LiteralPath (Join-Path $workspace 'release\installer\卸载汉化.ps1') -Destination $installerRoot
Copy-Item -LiteralPath (Join-Path $workspace 'release\一键安装.bat') -Destination $packageRoot
Copy-Item -LiteralPath (Join-Path $workspace 'release\一键卸载.bat') -Destination $packageRoot
Copy-Item -LiteralPath (Join-Path $workspace 'release\README_安装说明.md') -Destination $packageRoot
Copy-Item -LiteralPath (Join-Path $workspace 'docs\USER_GLOSSARY.md') -Destination (Join-Path $packageRoot '术语表与译名说明.md')
Copy-Item -LiteralPath (Join-Path $workspace 'docs\USER_GLOSSARY.md') -Destination (Join-Path $packageRoot '术语表与译名说明.txt')

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
    patch_version = $PatchVersion
    supported_game_version = $SupportedGameVersion
    translation_count = (Get-Content -LiteralPath $worklistPath | Measure-Object).Count
    files = @($files)
    outer_files = @($outerFiles)
}
$manifestJson = $manifest | ConvertTo-Json -Depth 6
$manifestPath = Join-Path $packageRoot 'payload-manifest.json'
[System.IO.File]::WriteAllText(
    $manifestPath,
    $manifestJson,
    [System.Text.UTF8Encoding]::new($true)
)

Write-Host "Current test-install package staged: $packageRoot"
Write-Host 'No release ZIP was generated.'

