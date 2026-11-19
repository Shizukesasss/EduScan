$ErrorActionPreference = 'Stop'
try {
    $checkout = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
    $source = Join-Path $PSScriptRoot 'eduscan-launcher.cs'
    $buildDirectory = Join-Path $checkout 'logs\launcher'
    $launcher = Join-Path $buildDirectory 'EduScan Launcher.exe'
    $existing = Get-Item -LiteralPath $launcher -ErrorAction SilentlyContinue
    if (-not $existing -or $existing.LastWriteTimeUtc -lt (Get-Item -LiteralPath $source).LastWriteTimeUtc) {
        $compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
        if (-not (Test-Path -LiteralPath $compiler)) { throw 'The Windows .NET Framework compiler is missing.' }
        New-Item -ItemType Directory -Path $buildDirectory -Force | Out-Null
        & $compiler /nologo /target:winexe /reference:System.Windows.Forms.dll /reference:System.Drawing.dll "/out:$launcher" $source
        if ($LASTEXITCODE -ne 0) { throw 'Windows could not build the EduScan launcher.' }
    }
    Start-Process -FilePath $launcher -ArgumentList ('"' + $checkout + '"') -WorkingDirectory $checkout
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    [void][System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'EduScan Launcher')
    exit 1
}
