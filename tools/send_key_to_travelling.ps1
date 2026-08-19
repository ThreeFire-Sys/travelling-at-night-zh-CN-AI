param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Enter', 'Escape', 'Space', 'F7', 'F9', 'Tab', 'Up', 'Down', 'Left', 'Right', 'LeftClick')]
    [string]$Key,
    [ValidateRange(0, 100)]
    [int]$XPercent = 50,
    [ValidateRange(0, 100)]
    [int]$YPercent = 50
)

$ErrorActionPreference = 'Stop'
$signature = @'
using System;
using System.Runtime.InteropServices;
public static class TravellingSmokeInputGeneric {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr hWnd, int command);
    [DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint flags, UIntPtr extraInfo);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extraInfo);
    public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
}
'@
Add-Type -TypeDefinition $signature
$process = Get-Process -Name travelling -ErrorAction Stop | Select-Object -First 1
if ($process.MainWindowHandle -eq [IntPtr]::Zero) {
    throw 'travelling.exe has no usable main window.'
}
[TravellingSmokeInputGeneric]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)
[TravellingSmokeInputGeneric]::ShowWindowAsync($process.MainWindowHandle, 9) | Out-Null
[TravellingSmokeInputGeneric]::BringWindowToTop($process.MainWindowHandle) | Out-Null
[TravellingSmokeInputGeneric]::SetForegroundWindow($process.MainWindowHandle) | Out-Null
[TravellingSmokeInputGeneric]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 300
if ($Key -eq 'LeftClick') {
    $rect = New-Object TravellingSmokeInputGeneric+RECT
    if (-not [TravellingSmokeInputGeneric]::GetWindowRect($process.MainWindowHandle, [ref]$rect)) {
        throw 'Could not read travelling.exe window bounds.'
    }
    $x = [int]($rect.Left + (($rect.Right - $rect.Left) * $XPercent / 100.0))
    $y = [int]($rect.Top + (($rect.Bottom - $rect.Top) * $YPercent / 100.0))
    [TravellingSmokeInputGeneric]::SetCursorPos($x, $y) | Out-Null
    [TravellingSmokeInputGeneric]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
    [TravellingSmokeInputGeneric]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
} else {
    $virtualKeys = @{ Enter = 0x0D; Escape = 0x1B; Space = 0x20; F7 = 0x76; F9 = 0x78; Tab = 0x09; Up = 0x26; Down = 0x28; Left = 0x25; Right = 0x27 }
    $vk = [byte]$virtualKeys[$Key]
    [TravellingSmokeInputGeneric]::keybd_event($vk, 0, 0, [UIntPtr]::Zero)
    [TravellingSmokeInputGeneric]::keybd_event($vk, 0, 2, [UIntPtr]::Zero)
}
Write-Output $process.Id
