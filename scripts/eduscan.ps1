[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'restart')]
    [string]$Action = 'start'
)

$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'manage-eduscan.ps1') -Action $Action
exit $LASTEXITCODE
