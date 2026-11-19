param(
    [string]$Action = 'start',
    [switch]$ShowDatabasePrompt,
    [switch]$OpenBrowser,
    [switch]$Offline
)

$ErrorActionPreference = 'Stop'

if ($Action -notin @('start', 'restart', 'stop', 'start-api', 'restart-api')) {
    Write-Host 'Supported actions: start, restart, stop, start-api, restart-api.' -ForegroundColor Yellow
    exit 2
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backendRoot = Join-Path $projectRoot 'backend'
$environmentFile = Join-Path $backendRoot '.env'
$startScript = Join-Path $PSScriptRoot 'start.ps1'
$apiPython = Join-Path $backendRoot '.venv\Scripts\python.exe'
$logDirectory = Join-Path $projectRoot 'logs'
$apiOnly = $Action -in @('start-api', 'restart-api')
. (Join-Path $PSScriptRoot 'eduscan-processes.ps1')

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
    if ($Offline -or -not (Test-RemoteDatabaseConfigured)) {
        return $true
    }

    Write-Host ''
    $message = 'EduScan API startup seeds reference data in the configured remote database. PostgreSQL runs migrations separately with maintenance credentials. MySQL can apply migrations on startup. Demo users are created only if explicitly enabled.'
    if ($ShowDatabasePrompt) {
        Add-Type -AssemblyName System.Windows.Forms
        $answer = [System.Windows.Forms.MessageBox]::Show(
            $message + "`n`nContinue?", 'EduScan remote database',
            'YesNo', 'Warning', 'Button2', 'DefaultDesktopOnly'
        )
        return $answer -eq 'Yes'
    }

    Write-Host $message -ForegroundColor Yellow
    $answer = Read-Host 'Continue? [y/N]'
    return $answer -match '^(?i:y|yes)$'
}

function Get-ListeningProcessIds {
    param([int]$Port)

    try {
        $connections = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    } catch { return }
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
        $checkoutAppDirectory = '--app-dir\s+"?' + [regex]::Escape($backendRoot) + '(?:"|\s|$)'
        $matchesCheckoutPython = ($actualPython -ieq $expectedPython) -or
            (($actualPython -ieq $basePython) -and ($commandLine -match $checkoutAppDirectory))
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
    $ports = @(8000)
    if (-not $apiOnly) {
        $ports = @(5175, 8000)
        foreach ($stateFile in (Get-ChildItem -LiteralPath $logDirectory -Filter 'service-*.json' -File -ErrorAction SilentlyContinue)) {
            if ($stateFile.BaseName -match '^service-(\d{1,5})$') {
                $port = [int]$Matches[1]
                if ($port -notin $ports -and (Get-EduScanProcess -Directory $logDirectory -Port $port)) { $ports += $port }
            }
        }
    }

    $owners = @()
    foreach ($port in $ports) {
        $record = Get-EduScanProcess -Directory $logDirectory -Port $port
        if ($record) {
            $owners += $record.Process
            continue
        }
        $listenerIds = @(Get-ListeningProcessIds -Port $port)
        if ($listenerIds.Count -eq 0 -and (Test-EduScanPort -Port $port)) {
            throw "Port $port responds, but this launcher cannot verify the process that owns it. Close it from its original terminal and try again."
        }
        foreach ($ownerId in $listenerIds) {
            $process = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $ownerId" -ErrorAction SilentlyContinue
            if (-not (Test-EduScanListener -Port $port -Process $process)) {
                throw "Port $port is owned by a process that cannot be verified as this EduScan checkout (PID $ownerId). Nothing was stopped."
            }
            $owners += Get-Process -Id $ownerId -ErrorAction Stop
        }
    }

    if ($owners.Count -eq 0) {
        Write-Host 'EduScan is already closed.'
        return
    }

    foreach ($process in ($owners | Sort-Object Id -Unique)) {
        Stop-EduScanProcess -Process $process
    }

    foreach ($port in $ports) {
        $attempt = 0
        while ($attempt -lt 40 -and (Test-EduScanPort -Port $port)) {
            Start-Sleep -Milliseconds 250
            $attempt++
        }
        if (Test-EduScanPort -Port $port) {
            throw "Port $port did not become free after stopping EduScan. Check the running process before retrying."
        }
    }
    Write-Host 'EduScan services stopped.'
}

try {
    if ($Action -eq 'stop') {
        Stop-EduScanListeners
        exit 0
    }

    $webOnly = $false
    if ($Action -in @('start', 'start-api')) {
        $runningApi = Get-EduScanProcess -Directory $logDirectory -Port 8000
        if ($runningApi -and (Test-EduScanPort -Port 8000)) {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 5
            if (-not $health.ok) { throw 'The running EduScan API is unhealthy. Choose Restart EduScan.' }
            if ($runningApi.Offline -ne [bool]$Offline) {
                throw 'Choose Restart EduScan to switch the running app to the selected database mode.'
            }
            if ($apiOnly) {
                Write-Host 'The EduScan API is already running at http://127.0.0.1:8000/api/health.'
                exit 0
            }
            $runningWeb = Get-EduScanProcess -Directory $logDirectory -Port 5175
            if ($runningWeb -and (Test-EduScanPort -Port 5175)) {
                Write-Host 'EduScan is already running at http://127.0.0.1:5175/.'
                if ($OpenBrowser) { Start-Process 'http://127.0.0.1:5175/' }
                exit 0
            }
            $webOnly = $true
        }
    }

    if (-not $webOnly -and -not (Confirm-RemoteDatabaseStartup)) {
        Write-Host 'Cancelled. No EduScan processes were started or stopped.'
        exit 0
    }
    if ($Action -in @('restart', 'restart-api')) { Stop-EduScanListeners }

    & $startScript -ApiOnly:$apiOnly -WebOnly:$webOnly -Offline:$Offline -OpenBrowser:$OpenBrowser
    exit 0
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
