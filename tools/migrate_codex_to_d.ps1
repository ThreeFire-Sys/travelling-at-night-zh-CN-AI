$ErrorActionPreference = 'Stop'

$sourceHome = 'C:\Users\WenmingYi\.codex'
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

function Assert-ExactPath {
    param([string]$Actual, [string]$Expected)
    if (-not [string]::Equals($Actual, $Expected, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Safety check failed. Expected '$Expected', got '$Actual'."
    }
}

function Invoke-RobocopyChecked {
    param(
        [string]$Source,
        [string]$Destination,
        [switch]$Move
    )

    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    $arguments = @($Source, $Destination, '/E', '/COPY:DAT', '/DCOPY:DAT', '/R:3', '/W:2', '/XJ', '/MT:8')
    if ($Move) {
        $arguments += '/MOVE'
    }

    & robocopy @arguments
    $result = $LASTEXITCODE
    if ($result -gt 7) {
        throw "Robocopy failed with exit code $result while copying '$Source' to '$Destination'."
    }
}

function Move-ToDAndCreateJunction {
    param(
        [string]$Source,
        [string]$Target,
        [string]$Backup
    )

    if (-not (Test-Path -LiteralPath $Source)) {
        Write-Log "Skipping missing source: $Source"
        return
    }

    $sourceItem = Get-Item -LiteralPath $Source -Force
    if ($sourceItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        Write-Log "Already redirected: $Source"
        return
    }

    Invoke-RobocopyChecked -Source $Source -Destination $Target

    $oldPath = "$Source.migration-old"
    if (Test-Path -LiteralPath $oldPath) {
        throw "Safety check failed because '$oldPath' already exists."
    }

    Move-Item -LiteralPath $Source -Destination $oldPath
    New-Item -ItemType Junction -Path $Source -Target $Target | Out-Null
    Write-Log "Redirected $Source -> $Target"

    Invoke-RobocopyChecked -Source $oldPath -Destination $Backup -Move
    if (Test-Path -LiteralPath $oldPath) {
        Remove-Item -LiteralPath $oldPath -Force
    }
    Write-Log "Recovery copy retained at $Backup"
}

New-Item -ItemType Directory -Path 'D:\CodexData' -Force | Out-Null
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
New-Item -ItemType Directory -Path $targetCliBin -Force | Out-Null

Assert-ExactPath -Actual $sourceHome -Expected 'C:\Users\WenmingYi\.codex'
Assert-ExactPath -Actual $targetHome -Expected 'D:\CodexData\.codex'
Assert-ExactPath -Actual $sourceRuntimeCache -Expected 'C:\Users\WenmingYi\.cache\codex-runtimes'
Assert-ExactPath -Actual $targetRuntimeCache -Expected 'D:\CodexData\cache\codex-runtimes'

Write-Log 'Migration finalizer started. Close the Codex desktop app and every Codex CLI window.'
while (Get-Process -Name codex -ErrorAction SilentlyContinue) {
    Write-Host 'Waiting for Codex processes to exit...'
    Start-Sleep -Seconds 2
}

Write-Log 'All Codex processes have exited. Starting final sync.'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
Move-ToDAndCreateJunction `
    -Source $sourceHome `
    -Target $targetHome `
    -Backup (Join-Path $backupRoot "codex-home-$stamp")

Move-ToDAndCreateJunction `
    -Source $sourceRuntimeCache `
    -Target $targetRuntimeCache `
    -Backup (Join-Path $backupRoot "codex-runtimes-$stamp")

[Environment]::SetEnvironmentVariable('CODEX_HOME', $targetHome, 'User')
[Environment]::SetEnvironmentVariable('CODEX_SQLITE_HOME', $targetHome, 'User')
[Environment]::SetEnvironmentVariable('CODEX_INSTALL_DIR', $targetCliBin, 'User')
$env:CODEX_HOME = $targetHome
$env:CODEX_SQLITE_HOME = $targetHome
$env:CODEX_INSTALL_DIR = $targetCliBin

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$pathParts = @($targetCliBin)
if ($userPath) {
    $pathParts += $userPath.Split(';') | Where-Object {
        $_ -and -not [string]::Equals($_.TrimEnd('\\'), $targetCliBin.TrimEnd('\\'), [System.StringComparison]::OrdinalIgnoreCase)
    }
}
$newUserPath = $pathParts -join ';'
[Environment]::SetEnvironmentVariable('Path', $newUserPath, 'User')

$cli = Join-Path $targetCliBin 'codex.exe'
if (-not (Test-Path -LiteralPath $cli)) {
    throw "D-drive Codex CLI was not found at '$cli'."
}

$version = & $cli --version
Write-Log "D-drive CLI verified: $version"
Write-Log 'Migration completed. You can reopen the Codex desktop app now.'

Write-Host ''
Write-Host 'Migration completed successfully.' -ForegroundColor Green
Write-Host "Log: $logPath"
Write-Host 'Press Enter to close this window.'
[void](Read-Host)
