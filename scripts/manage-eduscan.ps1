param(
    [string]$Action = 'start'
)

$ErrorActionPreference = 'Stop'

if ($Action -notin @('start', 'restart')) {
    Write-Host 'Usage: eduscan.cmd [start|restart]' -ForegroundColor Yellow
    exit 2
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backendRoot = Join-Path $projectRoot 'backend'
$environmentFile = Join-Path $backendRoot '.env'
$startScript = Join-Path $PSScriptRoot 'start.ps1'
$apiPython = Join-Path $backendRoot '.venv\Scripts\python.exe'
$ports = @(8000, 5175)

function Test-RemoteDatabaseConfigured {
    $value = [System.Environment]::GetEnvironmentVariable('DATABASE_URL', 'Process')
    if ($null -eq $value) {
        if (-not (Test-Path -LiteralPath $environmentFile)) {
            return $false
        }

        # Match backend/app/config.py: the first active DATABASE_URL assignment
        # wins, and values are only trimmed (not quote/comment parsed).
        foreach ($rawLine in [System.IO.File]::ReadAllLines($environmentFile)) {
            $line = $rawLine.Trim()
            if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith('#') -or
                -not $line.Contains('=')) {
                continue
            }

            $separator = $line.IndexOf('=')
            $key = $line.Substring(0, $separator).Trim()
            if ($key -ceq 'DATABASE_URL') {
                $value = $line.Substring($separator + 1).Trim()
                break
            }
        }
    }

    if ([string]::IsNullOrWhiteSpace($value)) {
        return $false
    }

    return $value -notmatch '^(?i:sqlite)(?:\+[^:]+)?:'
}

function Confirm-RemoteDatabaseStartup {
    if (-not (Test-RemoteDatabaseConfigured)) {
        return $true
    }

    Write-Host ''
    Write-Host 'EduScan API startup applies database migrations and seeds users/reference data in the configured remote database.' -ForegroundColor Yellow
    $answer = Read-Host 'Continue? [y/N]'
    return $answer -match '^(?i:y|yes)$'
}

function Get-ListeningProcessIds {
    param([int]$Port)

    $connections = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    return @($connections | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 0 })
}

function Test-EduScanListener {
    param(
        [int]$Port,
        [Microsoft.Management.Infrastructure.CimInstance]$Process
    )

    if (-not $Process -or [string]::IsNullOrWhiteSpace($Process.CommandLine)) {
        return $false
    }

    $commandLine = $Process.CommandLine
    if ($Port -eq 8000) {
        if ([string]::IsNullOrWhiteSpace($Process.ExecutablePath)) {
            return $false
        }
        $actualPython = [System.IO.Path]::GetFullPath($Process.ExecutablePath)
        $expectedPython = [System.IO.Path]::GetFullPath($apiPython)
        # Managed venv launchers can report their shared base interpreter in
        # Win32_Process.ExecutablePath. Resolve the base executable through
        # this checkout's venv and accept it only for the expected API command.
        $basePython = & $apiPython -c "import sys; print(getattr(sys, '_base_executable', sys.executable))" 2>$null |
            Select-Object -First 1
        if ([string]::IsNullOrWhiteSpace($basePython)) {
            return $false
        }
        $basePython = [System.IO.Path]::GetFullPath($basePython.Trim())
        $matchesCheckoutPython = ($actualPython -ieq $expectedPython) -or ($actualPython -ieq $basePython)
        return $matchesCheckoutPython -and
            ($commandLine -match '(?i)-m\s+uvicorn\s+app\.main:app') -and
            ($commandLine -match '(?i)--port\s+8000')
    }

    if ($Port -eq 5175) {
        $expectedViteScript = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'node_modules\vite\bin\vite.js'))
        $scriptMatch = [regex]::Match($commandLine, '(?i)"(?<script>[^"]*\\vite\\bin\\vite\.js)"')
        if (-not $scriptMatch.Success) {
            return $false
        }

        try {
            # Node may report Vite through npm's node_modules\.bin\.. shim path.
            # Canonicalize that argument before comparing it with this checkout.
            $actualViteScript = [System.IO.Path]::GetFullPath($scriptMatch.Groups['script'].Value)
        } catch {
            return $false
        }

        return ($actualViteScript -ieq $expectedViteScript) -and
            ($commandLine -match '(?i)--port\s+5175')
    }

    return $false
}

function Stop-EduScanListeners {
    $owners = @()
    foreach ($port in $ports) {
        foreach ($ownerId in (Get-ListeningProcessIds -Port $port)) {
            $process = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $ownerId" -ErrorAction SilentlyContinue
            if (-not (Test-EduScanListener -Port $port -Process $process)) {
                throw "Port $port is owned by a process that cannot be verified as this EduScan checkout (PID $ownerId). Nothing was stopped."
            }
            $owners += [pscustomobject]@{ Port = $port; ProcessId = [int]$ownerId }
        }
    }

    $processIds = @($owners | Select-Object -ExpandProperty ProcessId -Unique)
    if ($processIds.Count -eq 0) {
        # Some restricted shells can reach a forwarded local service while
        # denying listener/process enumeration. Never start a second API then.
        foreach ($port in $ports) {
            $uri = if ($port -eq 8000) { 'http://127.0.0.1:8000/api/health' } else { 'http://127.0.0.1:5175/' }
            $reachable = $false
            try { Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 2 | Out-Null; $reachable = $true }
            catch { $reachable = $null -ne $_.Exception.Response }
            if ($reachable) {
                throw "Port $port responds, but this shell cannot verify its owning EduScan process. Close the existing EduScan instance from its original terminal before restarting."
            }
        }
        Write-Host 'No EduScan listeners are running; starting a fresh instance.'
        return
    }

    foreach ($processId in $processIds) {
        Stop-Process -Id $processId -Force -ErrorAction Stop
    }

    foreach ($port in $ports) {
        $attempt = 0
        while ((Get-ListeningProcessIds -Port $port).Count -gt 0 -and $attempt -lt 40) {
            Start-Sleep -Milliseconds 250
            $attempt++
        }
        if ((Get-ListeningProcessIds -Port $port).Count -gt 0) {
            throw "Port $port did not become free after stopping EduScan. Check the running process before retrying."
        }
    }
}

if (-not (Confirm-RemoteDatabaseStartup)) {
    Write-Host 'Cancelled. No EduScan processes were started or stopped.'
    exit 0
}

if ($Action -eq 'restart') {
    try {
        Stop-EduScanListeners
    } catch {
        Write-Host $_.Exception.Message -ForegroundColor Red
        exit 1
    }
}

try {
    & $startScript
    exit 0
} catch {
    Write-Host 'EduScan did not start.' -ForegroundColor Red
    Write-Host 'Check logs\api.stderr.log and logs\web.stderr.log for details.'
    exit 1
}
