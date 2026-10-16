[CmdletBinding()]
param(
    [string]$DevicePath,
    [Parameter(Mandatory=$true)][int]$Exposure,
    [Parameter(Mandatory=$true)][int]$WhiteBalance,
    [switch]$ConfirmCameraOnlyControlWrite
)
$ErrorActionPreference = 'Stop'
if (-not $ConfirmCameraOnlyControlWrite) {
    throw 'Explicit camera-only control-write confirmation is required.'
}
Add-Type -Path (Join-Path $PSScriptRoot 'CameraBenchControls.cs')
$deviceName = 'Arducam B0477 (USB3 20MP)'
if ([string]::IsNullOrWhiteSpace($DevicePath)) {
    $paths = @([RoCellBench.CameraBenchControls]::FindDevicePaths($deviceName))
    if ($paths.Count -ne 1) {
        throw "Expected exactly one DirectShow path for the retained B0477; found $($paths.Count)."
    }
    $DevicePath = $paths[0]
}
[RoCellBench.CameraBenchControls]::RestoreAutomaticExposureAndWhiteBalance(
    $deviceName,
    $DevicePath,
    $Exposure,
    $WhiteBalance
) | ConvertTo-Json -Depth 6
