$ErrorActionPreference = 'Stop'

$sourceHome = 'C:\Users\WenmingYi\.codex'
$partialHome = 'C:\Users\WenmingYi\.codex.migration-old'
$targetHome = 'D:\CodexData\.codex'
$sourceRuntimeCache = 'C:\Users\WenmingYi\.cache\codex-runtimes'
$targetRuntimeCache = 'D:\CodexData\cache\codex-runtimes'
$backupRoot = 'D:\CodexData\migration-backup'
$targetCliBin = 'D:\CodexCLI\bin'
$logPath = 'D:\CodexData\migration.log'

$denySids = @(
    'S-1-5-21-3459557241-1196890855-1604428564-3196225180',
    'S-1-5-21-1529685663-583622271-3454455084-1370928706'
)

function Write-Log {
    param([string]$Message)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
}

function Invoke-RobocopyChecked {
    param([string]$Source, [string]$Destination, [string[]]$ExtraArguments = @())
    if (-not (Test-Path -LiteralPath $Source)) { return }
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    $arguments = @($Source, $Destination, '/E', '/COPY:DAT', '/DCOPY:DAT', '/R:2', '/W:1', '/XJ', '/ZB', '/NP', '/NFL', '/NDL')
    $arguments += $ExtraArguments
    & robocopy.exe @arguments | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "Robocopy failed with exit code ${LASTEXITCODE}: $Source -> $Destination"
    }
}

function Remove-BackedUpTree {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }

    & takeown.exe /F $Path /A /R /D Y | Out-Null
    foreach ($sid in $denySids) {
        & icacls.exe $Path /remove:d "*$sid" /T /C /Q | Out-Null
    }
    & icacls.exe $Path /inheritance:e /grant:r 'BUILTIN\Administrators:(OI)(CI)F' /T /C /Q | Out-Null
    Remove-Item -LiteralPath $Path -Recurse -Force
    if (Test-Path -LiteralPath $Path) {
        throw "Old C-drive tree still exists after removal: $Path"
    }
    Write-Log "Removed backed-up C-drive tree: $Path"
}

try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Administrator elevation is required.'
    }

    if (-not (Test-Path -LiteralPath $targetHome)) { throw "Missing target: $targetHome" }
    if (-not (Test-Path -LiteralPath $backupRoot)) { throw "Missing backup root: $backupRoot" }

    Write-Log 'ACL-fix finalizer started.'
    Invoke-RobocopyChecked -Source $sourceHome -Destination $targetHome -ExtraArguments @('/XO')
    Invoke-RobocopyChecked -Source $partialHome -Destination $targetHome -ExtraArguments @('/XO')
    Write-Log 'Final incremental home sync completed.'

    Remove-BackedUpTree -Path $sourceHome
    Remove-BackedUpTree -Path $partialHome
    New-Item -ItemType Junction -Path $sourceHome -Target $targetHome | Out-Null
    Write-Log "Created compatibility junction: $sourceHome -> $targetHome"

    if (Test-Path -LiteralPath $sourceRuntimeCache) {
        Invoke-RobocopyChecked -Source $sourceRuntimeCache -Destination $targetRuntimeCache -ExtraArguments @('/XO')
        $runtimeBackup = Join-Path $backupRoot ("codex-runtimes-c-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
        Invoke-RobocopyChecked -Source $sourceRuntimeCache -Destination $runtimeBackup
        Write-Log "Created runtime recovery copy: $runtimeBackup"
        Remove-BackedUpTree -Path $sourceRuntimeCache
        New-Item -ItemType Junction -Path $sourceRuntimeCache -Target $targetRuntimeCache | Out-Null
        Write-Log "Created runtime-cache junction: $sourceRuntimeCache -> $targetRuntimeCache"
    }

    [Environment]::SetEnvironmentVariable('CODEX_HOME', $targetHome, 'User')
    [Environment]::SetEnvironmentVariable('CODEX_SQLITE_HOME', $targetHome, 'User')
    [Environment]::SetEnvironmentVariable('CODEX_INSTALL_DIR', $targetCliBin, 'User')
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $rest = @($userPath.Split(';') | Where-Object {
        $_ -and -not [string]::Equals($_.TrimEnd('\'), $targetCliBin.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)
    })
    [Environment]::SetEnvironmentVariable('Path', (@($targetCliBin) + $rest -join ';'), 'User')

    $version = & (Join-Path $targetCliBin 'codex.exe') --version
    Write-Log "D-drive CLI verified: $version"
    Write-Log 'Migration completed successfully after ACL repair.'
    exit 0
}
catch {
    Write-Log ("ERROR: " + $_.Exception.Message)
    exit 1
}
