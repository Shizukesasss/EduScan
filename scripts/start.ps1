[CmdletBinding()]
param(
  [switch]$Wait
)

$ErrorActionPreference = "Stop"
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
}

Assert-LocalPortAvailable -Port 8000 -ServiceName "EduScan API"
Assert-LocalPortAvailable -Port 5174 -ServiceName "EduScan web app"

$logDirectory = Join-Path $projectRoot "logs"
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$api = Start-Process -FilePath $python -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" -WorkingDirectory $backendRoot -RedirectStandardOutput (Join-Path $logDirectory "api.stdout.log") -RedirectStandardError (Join-Path $logDirectory "api.stderr.log") -WindowStyle Hidden -PassThru
$web = Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev", "--", "--host", "127.0.0.1", "--port", "5174" -WorkingDirectory $projectRoot -RedirectStandardOutput (Join-Path $logDirectory "web.stdout.log") -RedirectStandardError (Join-Path $logDirectory "web.stderr.log") -WindowStyle Hidden -PassThru

function Wait-EduScanEndpoint {
  param(
    [string]$Uri,
    [System.Diagnostics.Process]$Process,
    [string]$ServiceName,
    [string]$ErrorLog
  )
  for ($attempt = 0; $attempt -lt 30; $attempt++) {
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
  throw "$ServiceName did not become ready within 15 seconds. Read $ErrorLog for the error."
}

try {
  Wait-EduScanEndpoint -Uri "http://127.0.0.1:8000/api/health" -Process $api -ServiceName "EduScan API" -ErrorLog "logs\api.stderr.log"
  Wait-EduScanEndpoint -Uri "http://127.0.0.1:5174" -Process $web -ServiceName "EduScan web app" -ErrorLog "logs\web.stderr.log"
} catch {
  Stop-Process -Id $api.Id -ErrorAction SilentlyContinue
  Stop-Process -Id $web.Id -ErrorAction SilentlyContinue
  throw
}

Write-Host "EduScan API ready (PID $($api.Id)): http://127.0.0.1:8000/api/health"
Write-Host "EduScan web app ready (PID $($web.Id)): http://127.0.0.1:5174"
Write-Host "Logs: $logDirectory"

if ($Wait) {
  try {
    Write-Host "EduScan is running in foreground. Press Ctrl+C to stop."
    Wait-Process -Id $api.Id, $web.Id
  } finally {
    Stop-Process -Id $api.Id -ErrorAction SilentlyContinue
    Stop-Process -Id $web.Id -ErrorAction SilentlyContinue
  }
}

