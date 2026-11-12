[CmdletBinding()]
param(
  [switch]$Wait,
  [switch]$OpenBrowser,
  [switch]$ApiOnly,
  [ValidateRange(1, 65535)]
  [int]$WebPort = 5175
)

$ErrorActionPreference = "Stop"
$ProgressPreference = 'SilentlyContinue'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendRoot = Join-Path $projectRoot "backend"
$python = Join-Path $backendRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
  throw "Backend environment is missing. Run .\scripts\setup.ps1 first."
}

function Assert-LocalPortAvailable {
  param([int]$Port, [string]$ServiceName)
  $client = [Net.Sockets.TcpClient]::new()
  try {
    $connection = $client.ConnectAsync("127.0.0.1", $Port)
    if ($connection.Wait(400) -and $client.Connected) {
      throw "$ServiceName cannot start because port $Port is already in use. Close the other program or EduScan instance, then run this script again."
    }
  } catch [AggregateException] {
    # Connection refused means the port is available.
  } finally {
    $client.Dispose()
  }
  # Restricted shells can miss a listener even while its HTTP endpoint is
  # reachable. Refuse to launch another process that could reserve more DB slots.
  $uri = if ($Port -eq 8000) { 'http://127.0.0.1:8000/api/health' } else { "http://127.0.0.1:$Port/" }
  $reachable = $false
  try { Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 2 | Out-Null; $reachable = $true }
  catch { $reachable = $null -ne $_.Exception.Response }
  if ($reachable) {
    throw "$ServiceName responds on port $Port, so a second instance will not be started. Close the existing instance before retrying."
  }
}

Assert-LocalPortAvailable -Port 8000 -ServiceName "EduScan API"
if (-not $ApiOnly) {
  Assert-LocalPortAvailable -Port $WebPort -ServiceName "EduScan web app"
}

$logDirectory = Join-Path $projectRoot "logs"
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$allowedOrigins = [System.Environment]::GetEnvironmentVariable('ALLOWED_ORIGINS', 'Process')
if ($null -eq $allowedOrigins) {
  $dotenvFile = Join-Path $backendRoot '.env'
  if (Test-Path -LiteralPath $dotenvFile) {
    foreach ($rawLine in [System.IO.File]::ReadAllLines($dotenvFile)) {
      $line = $rawLine.Trim()
      if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith('#') -or -not $line.Contains('=')) { continue }
      $separator = $line.IndexOf('=')
      if ($line.Substring(0, $separator).Trim() -ceq 'ALLOWED_ORIGINS') {
        $allowedOrigins = $line.Substring($separator + 1).Trim()
        break
      }
    }
  }
}
if ($null -eq $allowedOrigins) { $allowedOrigins = 'http://127.0.0.1:5173,http://127.0.0.1:5174' }
$webOrigin = "http://127.0.0.1:$WebPort"
if (@($allowedOrigins -split ',' | ForEach-Object { $_.Trim() }) -notcontains $webOrigin) {
  if ([string]::IsNullOrWhiteSpace($allowedOrigins)) { $allowedOrigins = $webOrigin }
  else { $allowedOrigins = "$allowedOrigins,$webOrigin" }
}
$env:ALLOWED_ORIGINS = $allowedOrigins
$api = $null
$web = $null


function Wait-EduScanEndpoint {
  param(
    [string]$Uri,
    [System.Diagnostics.Process]$Process,
    [string]$ServiceName,
    [string]$ErrorLog
  )
  $startupTime = [System.Diagnostics.Stopwatch]::StartNew()
  while ($startupTime.Elapsed.TotalSeconds -lt 60) {
    if ($Process.HasExited) {
      throw "$ServiceName stopped during startup. Read $ErrorLog for the error."
    }
    try {
      $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 2
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
        return
      }
    } catch {
      # The service may still be applying migrations or compiling the frontend.
    }
    Start-Sleep -Milliseconds 500
  }
  throw "$ServiceName did not become ready within 60 seconds. Read $ErrorLog for the error."
}

function Stop-EduScanProcess {
  param([System.Diagnostics.Process]$Process)
  if ($Process -and -not $Process.HasExited) {
    # The Windows virtual environment can launch Python as a child process.
    $ErrorActionPreference = 'SilentlyContinue'
    taskkill.exe /PID $Process.Id /T /F 2>$null | Out-Null
  }
}

$ready = $false
# Keep dev services attached to the invoking console so they receive Ctrl+C.
$processWindow = if ($Wait) { @{ NoNewWindow = $true } } else { @{ WindowStyle = 'Hidden' } }
try {
  if (-not $ApiOnly) {
    $node = (Get-Command node.exe -ErrorAction Stop).Source
    $viteScript = Join-Path $projectRoot 'node_modules\vite\bin\vite.js'
  }
  Write-Host "Starting the EduScan API on port 8000..."
  $api = Start-Process -FilePath $python -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" -WorkingDirectory $backendRoot -RedirectStandardOutput (Join-Path $logDirectory "api.stdout.log") -RedirectStandardError (Join-Path $logDirectory "api.stderr.log") @processWindow -PassThru
  if (-not $ApiOnly) {
    $web = Start-Process -FilePath $node -ArgumentList ('"' + $viteScript + '" --host 127.0.0.1 --strictPort --port ' + $WebPort) -WorkingDirectory $projectRoot -RedirectStandardOutput (Join-Path $logDirectory "web.stdout.log") -RedirectStandardError (Join-Path $logDirectory "web.stderr.log") @processWindow -PassThru
    Wait-EduScanEndpoint -Uri $webOrigin -Process $web -ServiceName "EduScan web app" -ErrorLog "logs\web.stderr.log"
    Write-Host "EduScan web app ready (PID $($web.Id)): $webOrigin"
  }
  Wait-EduScanEndpoint -Uri "http://127.0.0.1:8000/api/health" -Process $api -ServiceName "EduScan API" -ErrorLog "logs\api.stderr.log"
  Write-Host "EduScan API ready (PID $($api.Id)): http://127.0.0.1:8000/api/health"
  Write-Host "Logs: $logDirectory"
  $ready = $true
  if ($OpenBrowser -and $web) {
    try {
      Start-Process -FilePath $webOrigin
    } catch {
      Write-Warning "Could not open the browser automatically. Open $webOrigin to use EduScan."
    }
  }
  if ($Wait) {
    Write-Host "EduScan is running in foreground. Press Ctrl+C to stop."
    while (-not $api.HasExited -and (-not $web -or -not $web.HasExited)) {
      Start-Sleep -Milliseconds 500
    }
    if ($api.HasExited) {
      throw "EduScan API stopped. Check logs\api.stderr.log."
    }
    throw "EduScan web app stopped. Check logs\web.stderr.log."
  }
} finally {
  if ($Wait -or -not $ready) {
    Stop-EduScanProcess $web
    Stop-EduScanProcess $api
  }
}

