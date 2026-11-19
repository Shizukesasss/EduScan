[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'restart', 'stop', 'start-api', 'restart-api')]
    [string]$Action = 'start',
    [switch]$Offline
)

$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'manage-eduscan.ps1') -Action $Action -Offline:$Offline
exit $LASTEXITCODE
