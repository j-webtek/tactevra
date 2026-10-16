[CmdletBinding()]
param([string]$DevicePath)
$ErrorActionPreference = 'Stop'
# A separate bench utility; never import its JSON as commissioned evidence.
Add-Type -Path (Join-Path $PSScriptRoot 'CameraBenchControls.cs')
$deviceName = 'Arducam B0477 (USB3 20MP)'
if ([string]::IsNullOrWhiteSpace($DevicePath)) {
    $paths = @([RoCellBench.CameraBenchControls]::FindDevicePaths($deviceName))
    if ($paths.Count -ne 1) {
        throw "Expected exactly one DirectShow path for the retained B0477; found $($paths.Count)."
    }
    $DevicePath = $paths[0]
}
[RoCellBench.CameraBenchControls]::Read($deviceName, $DevicePath) | ConvertTo-Json -Depth 6
