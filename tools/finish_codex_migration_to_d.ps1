$ErrorActionPreference = 'Stop'

$sourceHome = 'C:\Users\WenmingYi\.codex'
$partialHome = 'C:\Users\WenmingYi\.codex.migration-old'
$targetHome = 'D:\CodexData\.codex'
$sourceRuntimeCache = 'C:\Users\WenmingYi\.cache\codex-runtimes'
$targetRuntimeCache = 'D:\CodexData\cache\codex-runtimes'
$targetCliBin = 'D:\CodexCLI\bin'
$backupRoot = 'D:\CodexData\migration-backup'
$logPath = 'D:\CodexData\migration.log'

function Write-Log {
    param([string]$Message)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Write-Host $line
    Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
}

function Invoke-RobocopyChecked {
    param(
        [string]$Source,
        [string]$Destination,
        [string[]]$ExtraArguments = @()
    )
    if (-not (Test-Path -LiteralPath $Source)) {
        return
    }
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    $arguments = @($Source, $Destination, '/E', '/COPY:DAT', '/DCOPY:DAT', '/R:3', '/W:2', '/XJ', '/ZB', '/MT:8')
    $arguments += $ExtraArguments
    & robocopy @arguments
    $result = $LASTEXITCODE
    if ($result -gt 7) {
        throw "Robocopy failed with exit code $result while copying '$Source' to '$Destination'."
    }
}

function Remove-OldTree {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    & icacls.exe $Path /grant:r 'BUILTIN\Administrators:(OI)(CI)F' /T /C /Q | Out-Host
    Remove-Item -LiteralPath $Path -Recurse -Force
    Write-Log "Removed migrated C-drive tree: $Path"
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'This finalizer must run as Administrator.'
}

New-Item -ItemType Directory -Path $targetHome -Force | Out-Null
New-Item -ItemType Directory -Path $targetRuntimeCache -Force | Out-Null
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null

Write-Log 'Elevated migration finalizer started. Close the Codex desktop app and every Codex CLI window.'
while (Get-Process -Name codex -ErrorAction SilentlyContinue) {
    Write-Host 'Waiting for all Codex processes to exit...'
    Start-Sleep -Seconds 2
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
Write-Log 'All Codex processes have exited. Copying only newer or missing C-drive state to D.'

# /XO protects newer D-drive state while recovering any newer session files left on C.
Invoke-RobocopyChecked -Source $sourceHome -Destination $targetHome -ExtraArguments @('/XO')
Invoke-RobocopyChecked -Source $partialHome -Destination $targetHome -ExtraArguments @('/XO')

# Keep full recovery copies on D before removing the old C-drive trees.
$homeBackup = Join-Path $backupRoot "codex-home-c-$stamp"
$partialBackup = Join-Path $backupRoot "codex-home-partial-c-$stamp"
Invoke-RobocopyChecked -Source $sourceHome -Destination $homeBackup
Invoke-RobocopyChecked -Source $partialHome -Destination $partialBackup

Remove-OldTree -Path $sourceHome
Remove-OldTree -Path $partialHome
New-Item -ItemType Junction -Path $sourceHome -Target $targetHome | Out-Null
Write-Log "Created compatibility junction: $sourceHome -> $targetHome"

if (Test-Path -LiteralPath $sourceRuntimeCache) {
    Invoke-RobocopyChecked -Source $sourceRuntimeCache -Destination $targetRuntimeCache -ExtraArguments @('/XO')
    $runtimeBackup = Join-Path $backupRoot "codex-runtimes-c-$stamp"
    Invoke-RobocopyChecked -Source $sourceRuntimeCache -Destination $runtimeBackup
    Remove-OldTree -Path $sourceRuntimeCache
    New-Item -ItemType Junction -Path $sourceRuntimeCache -Target $targetRuntimeCache | Out-Null
    Write-Log "Created runtime-cache junction: $sourceRuntimeCache -> $targetRuntimeCache"
}

[Environment]::SetEnvironmentVariable('CODEX_HOME', $targetHome, 'User')
[Environment]::SetEnvironmentVariable('CODEX_SQLITE_HOME', $targetHome, 'User')
[Environment]::SetEnvironmentVariable('CODEX_INSTALL_DIR', $targetCliBin, 'User')

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$pathParts = @($targetCliBin)
if ($userPath) {
    $pathParts += $userPath.Split(';') | Where-Object {
        $_ -and -not [string]::Equals($_.TrimEnd('\\'), $targetCliBin.TrimEnd('\\'), [StringComparison]::OrdinalIgnoreCase)
    }
}
[Environment]::SetEnvironmentVariable('Path', ($pathParts -join ';'), 'User')

$cli = Join-Path $targetCliBin 'codex.exe'
if (-not (Test-Path -LiteralPath $cli)) {
    throw "D-drive CLI not found: $cli"
}
$env:CODEX_HOME = $targetHome
$version = & $cli --version
Write-Log "D-drive CLI verified: $version"
Write-Log 'Migration completed successfully. Reopen Codex.'

Write-Host ''
Write-Host 'Migration completed successfully.' -ForegroundColor Green
Write-Host "Recovery copies: $backupRoot"
Write-Host "Log: $logPath"
Write-Host 'Press Enter to close this window.'
[void](Read-Host)
