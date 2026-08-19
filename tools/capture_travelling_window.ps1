param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$signature = @'
using System;
using System.Runtime.InteropServices;
public static class TravellingWindowCapture {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr hWnd, int command);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdc, uint flags);
    [DllImport("user32.dll")] public static extern void keybd_event(byte key, byte scan, uint flags, UIntPtr extra);
}
'@
Add-Type -TypeDefinition $signature
$process = Get-Process -Name travelling -ErrorAction Stop | Select-Object -First 1
$handle = $process.MainWindowHandle
if ($handle -eq [IntPtr]::Zero) { throw 'travelling.exe has no usable main window.' }

# A synthetic Alt press permits SetForegroundWindow across process boundaries
# under the normal Windows foreground-lock rules.  Capture follows in this same
# process so another helper shell cannot steal focus between the two actions.
[TravellingWindowCapture]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)
[TravellingWindowCapture]::ShowWindowAsync($handle, 9) | Out-Null
[TravellingWindowCapture]::BringWindowToTop($handle) | Out-Null
[TravellingWindowCapture]::SetForegroundWindow($handle) | Out-Null
[TravellingWindowCapture]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 800

$rect = New-Object TravellingWindowCapture+RECT
if (-not [TravellingWindowCapture]::GetWindowRect($handle, [ref]$rect)) {
    throw 'Could not read travelling.exe window bounds.'
}
$width = $rect.Right - $rect.Left
$height = $rect.Bottom - $rect.Top
if ($width -le 0 -or $height -le 0) { throw "Invalid game window size: ${width}x${height}" }

$bitmap = New-Object System.Drawing.Bitmap $width, $height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
try {
    $hdc = $graphics.GetHdc()
    try {
        $printed = [TravellingWindowCapture]::PrintWindow($handle, $hdc, 2)
    } finally {
        $graphics.ReleaseHdc($hdc)
    }
    if (-not $printed) {
        $graphics.CopyFromScreen($rect.Left, $rect.Top, 0, 0, $bitmap.Size)
    }
    $bitmap.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Png)
} finally {
    $graphics.Dispose()
    $bitmap.Dispose()
}
Write-Output "$OutputPath|${width}x${height}|printWindow=$printed"
