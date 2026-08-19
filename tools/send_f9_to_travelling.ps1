$ErrorActionPreference = 'Stop'
$signature = @'
using System;
using System.Runtime.InteropServices;
public static class TravellingSmokeInput {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint flags, UIntPtr extraInfo);
}
'@
Add-Type -TypeDefinition $signature
$process = Get-Process -Name travelling -ErrorAction Stop | Select-Object -First 1
if ($process.MainWindowHandle -eq [IntPtr]::Zero) {
    throw 'travelling.exe has no usable main window.'
}
[TravellingSmokeInput]::SetForegroundWindow($process.MainWindowHandle) | Out-Null
Start-Sleep -Milliseconds 300
[TravellingSmokeInput]::keybd_event(0x78, 0, 0, [UIntPtr]::Zero)
[TravellingSmokeInput]::keybd_event(0x78, 0, 2, [UIntPtr]::Zero)
Write-Output $process.Id
