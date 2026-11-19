[CmdletBinding()]
param(
  [switch]$Wait,
  [switch]$OpenBrowser,
  [switch]$ApiOnly,
  [switch]$WebOnly,
  [switch]$Offline,
  [ValidateRange(1, 65535)]
  [int]$WebPort = 5175
)

$ErrorActionPreference = "Stop"
$ProgressPreference = 'SilentlyContinue'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendRoot = Join-Path $projectRoot "backend"
. (Join-Path $PSScriptRoot 'eduscan-processes.ps1')

function Assert-LocalPortAvailable {
  param([int]$Port, [string]$ServiceName)
  if (Test-EduScanPort -Port $Port) {
    throw "$ServiceName cannot start because port $Port is already in use. Close the other program or EduScan instance, then run this script again."
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

if ($WebOnly -and ($ApiOnly -or $Wait)) { throw 'Web-only startup cannot be combined with API-only or foreground startup.' }
if (-not $WebOnly) {
  $python = Join-Path $backendRoot '.venv\Scripts\python.exe'
  if (-not (Test-Path -LiteralPath $python)) {
    throw 'Backend environment is missing. Run .\scripts\setup.ps1 first.'
  }
  Assert-LocalPortAvailable -Port 8000 -ServiceName 'EduScan API'
}
if (-not $ApiOnly) {
  Assert-LocalPortAvailable -Port $WebPort -ServiceName "EduScan web app"
}

$launchEnvironment = @{}
if ($Offline -and -not $WebOnly) {
  # Keep the local database, generated files, and keys together in a separate folder.
  $launchEnvironment = @{
    DATABASE_URL = 'sqlite:///./data/eduscan-offline/eduscan.db'
    EDUSCAN_DATA_DIR = Join-Path $backendRoot 'data\eduscan-offline'
    EDUSCAN_SEED_DEMO_ACCOUNTS = 'true'
    EDUSCAN_DEPED_ONLY = 'false'
    EDUSCAN_DEPED_PASSWORD_RECOVERY = 'false'
    EDUSCAN_SECRET_KEY = ' '
    EDUSCAN_ENCRYPTION_KEY = ' '
    GOOGLE_CLIENT_ID = ' '
    SMTP_HOST = ' '
    SMS_GATEWAY_ENABLED = 'false'
  }
}
if ($Offline) { $launchEnvironment['VITE_API_URL'] = 'http://127.0.0.1:8000/api' }

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
$launchEnvironment['ALLOWED_ORIGINS'] = $allowedOrigins
$previousEnvironment = @{}
$api = $null
$apiServer = $null
$web = $null
$apiErrorLog = Join-Path $logDirectory 'api.stderr.log'


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

function Get-EduScanApiServer {
  # A Windows venv can keep a launcher process waiting on Uvicorn's Python process.
  $startupLine = Select-String -LiteralPath $apiErrorLog -Pattern 'Started server process \[(\d+)\]' -ErrorAction SilentlyContinue |
    Select-Object -First 1
  if ($startupLine) {
    $serverId = [int]$startupLine.Matches[0].Groups[1].Value
    $server = Get-Process -Id $serverId -ErrorAction SilentlyContinue
    if ($server -and $server.StartTime -ge $api.StartTime) { return $server }
  }
  return $api
}

$ready = $false
# Keep dev services attached to the invoking console so they receive Ctrl+C.
$processWindow = if ($Wait) { @{ NoNewWindow = $true } } else { @{ WindowStyle = 'Hidden' } }
try {
  if (-not $ApiOnly) {
    $node = (Get-Command node.exe -ErrorAction Stop).Source
    $viteScript = Join-Path $projectRoot 'node_modules\vite\bin\vite.js'
  }
  foreach ($name in $launchEnvironment.Keys) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    [Environment]::SetEnvironmentVariable($name, $launchEnvironment[$name], 'Process')
  }
  if (-not $WebOnly) {
    if ($Offline) { Write-Host 'Offline mode uses this computer''s separate SQLite database.' }
    Write-Host "Starting the EduScan API on port 8000..."
    $api = Start-Process -FilePath $python -ArgumentList '-m', 'uvicorn', 'app.main:app', '--no-proxy-headers', '--app-dir', ('"' + $backendRoot + '"'), '--host', '127.0.0.1', '--port', '8000' -WorkingDirectory $backendRoot -RedirectStandardOutput (Join-Path $logDirectory "api.stdout.log") -RedirectStandardError $apiErrorLog @processWindow -PassThru
  }
  if (-not $ApiOnly) {
    $web = Start-Process -FilePath $node -ArgumentList ('"' + $viteScript + '" --host 127.0.0.1 --strictPort --port ' + $WebPort) -WorkingDirectory $projectRoot -RedirectStandardOutput (Join-Path $logDirectory "web.stdout.log") -RedirectStandardError (Join-Path $logDirectory "web.stderr.log") @processWindow -PassThru
    Save-EduScanProcess -Directory $logDirectory -Port $WebPort -Process $web -Offline ([bool]$Offline)
    Wait-EduScanEndpoint -Uri $webOrigin -Process $web -ServiceName "EduScan web app" -ErrorLog "logs\web.stderr.log"
    Write-Host "EduScan web app ready (PID $($web.Id)): $webOrigin"
  }
  if ($api) {
    Wait-EduScanEndpoint -Uri "http://127.0.0.1:8000/api/health" -Process $api -ServiceName "EduScan API" -ErrorLog "logs\api.stderr.log"
    $apiServer = Get-EduScanApiServer
    Save-EduScanProcess -Directory $logDirectory -Port 8000 -Process $apiServer -Offline ([bool]$Offline)
    Write-Host "EduScan API ready (PID $($apiServer.Id)): http://127.0.0.1:8000/api/health"
  }
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
  try {
    if ($Wait -or -not $ready) {
      try { Stop-EduScanProcess $web } finally {
        if ($api -and -not $api.HasExited) {
          if (-not $apiServer) { $apiServer = Get-EduScanApiServer }
          Stop-EduScanProcess $apiServer
        }
      }
    }
  } finally {
    foreach ($name in $previousEnvironment.Keys) {
      [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process')
    }
  }
}

