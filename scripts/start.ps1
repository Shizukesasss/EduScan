[CmdletBinding()]
param(
  [switch]$Wait,
  [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendRoot = Join-Path $projectRoot "backend"
$python = Join-Path $backendRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
  throw "Backend environment is missing. Run .\scripts\setup.ps1 first."
}

function Test-EduScanEndpoint {
  param([string]$Uri)
  try {
    $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 2
    return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
  } catch {
    return $false
  }
}

function Find-RunningEduScanService {
  param([int]$Port, [string]$ServiceName, [string]$Uri)
  for ($attempt = 0; $attempt -lt 10; $attempt++) {
    if (Test-EduScanEndpoint -Uri $Uri) { return $true }

    $client = [Net.Sockets.TcpClient]::new()
    $portInUse = $false
    try {
      $connection = $client.ConnectAsync("127.0.0.1", $Port)
      $portInUse = $connection.Wait(400) -and $client.Connected
    } catch [AggregateException] {
      # Connection refused means the port is available.
    } finally {
      $client.Dispose()
    }

    if (-not $portInUse) { return $false }
    Start-Sleep -Milliseconds 500
  }
  throw "$ServiceName cannot start because port $Port is in use, but its endpoint did not become reachable. Wait for the other EduScan instance to finish starting, or close the program using that port."
}

$startupMutex = [System.Threading.Mutex]::new($false, "Local\EduScanStartup")
$startupMutexAcquired = $false
try {
  $startupMutexAcquired = $startupMutex.WaitOne([TimeSpan]::FromSeconds(90))
} catch [System.Threading.AbandonedMutexException] {
  # A launcher closed unexpectedly; take over its startup lock.
  $startupMutexAcquired = $true
}
if (-not $startupMutexAcquired) {
  $startupMutex.Dispose()
  throw "Another EduScan launcher is still starting. Wait a moment, then try again."
}

try {
    $apiAlreadyRunning = Find-RunningEduScanService -Port 8000 -ServiceName "EduScan API" -Uri "http://127.0.0.1:8000/api/health"
    $webAlreadyRunning = Find-RunningEduScanService -Port 5174 -ServiceName "EduScan web app" -Uri "http://127.0.0.1:5174"

$logDirectory = Join-Path $projectRoot "logs"
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$api = $null
$web = $null
if (-not $apiAlreadyRunning) {
  $api = Start-Process -FilePath $python -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload" -WorkingDirectory $backendRoot -RedirectStandardOutput (Join-Path $logDirectory "api.stdout.log") -RedirectStandardError (Join-Path $logDirectory "api.stderr.log") -WindowStyle Hidden -PassThru
}
if (-not $webAlreadyRunning) {
    $web = Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev", "--", "--host", "127.0.0.1", "--port", "5174", "--strictPort" -WorkingDirectory $projectRoot -RedirectStandardOutput (Join-Path $logDirectory "web.stdout.log") -RedirectStandardError (Join-Path $logDirectory "web.stderr.log") -WindowStyle Hidden -PassThru
}

function Wait-EduScanEndpoint {
  param(
    [string]$Uri,
    [System.Diagnostics.Process]$Process,
    [string]$ServiceName,
    [string]$ErrorLog
  )
  for ($attempt = 0; $attempt -lt 30; $attempt++) {
    if ($null -ne $Process -and $Process.HasExited) {
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
  throw "$ServiceName did not become ready within 15 seconds. Read $ErrorLog for the error."
}

try {
  Wait-EduScanEndpoint -Uri "http://127.0.0.1:8000/api/health" -Process $api -ServiceName "EduScan API" -ErrorLog "logs\api.stderr.log"
  Wait-EduScanEndpoint -Uri "http://127.0.0.1:5174" -Process $web -ServiceName "EduScan web app" -ErrorLog "logs\web.stderr.log"
} catch {
  if ($null -ne $api) { Stop-Process -Id $api.Id -ErrorAction SilentlyContinue }
  if ($null -ne $web) { Stop-Process -Id $web.Id -ErrorAction SilentlyContinue }
  throw
}
  } finally {
    if ($startupMutexAcquired) { $startupMutex.ReleaseMutex() }
    $startupMutex.Dispose()
  }

if ($null -ne $api) {
  Write-Host "EduScan API ready (PID $($api.Id)): http://127.0.0.1:8000/api/health"
} else {
  Write-Host "EduScan API already running: http://127.0.0.1:8000/api/health"
}
if ($null -ne $web) {
  Write-Host "EduScan web app ready (PID $($web.Id)): http://127.0.0.1:5174"
} else {
  Write-Host "EduScan web app already running: http://127.0.0.1:5174"
}
Write-Host "Logs: $logDirectory"

if ($OpenBrowser) {
  Start-Process "http://127.0.0.1:5174"
}

if ($Wait) {
  try {
    Write-Host "EduScan is running in foreground. Press Ctrl+C to stop."
    $ownedProcesses = @($api, $web) | Where-Object { $null -ne $_ }
    if ($ownedProcesses.Count -gt 0) {
      Wait-Process -Id $ownedProcesses.Id
    } else {
      while ($true) { Start-Sleep -Seconds 1 }
    }
  } finally {
    if ($null -ne $api) { Stop-Process -Id $api.Id -ErrorAction SilentlyContinue }
    if ($null -ne $web) { Stop-Process -Id $web.Id -ErrorAction SilentlyContinue }
  }
}

