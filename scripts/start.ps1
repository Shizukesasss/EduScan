[CmdletBinding()]
param(
  [switch]$Wait
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
  $uri = if ($Port -eq 8000) { 'http://127.0.0.1:8000/api/health' } else { 'http://127.0.0.1:5175/' }
  $reachable = $false
  try { Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 2 | Out-Null; $reachable = $true }
  catch { $reachable = $null -ne $_.Exception.Response }
  if ($reachable) {
    throw "$ServiceName responds on port $Port, so a second instance will not be started. Close the existing instance before retrying."
  }
}

Assert-LocalPortAvailable -Port 8000 -ServiceName "EduScan API"
Assert-LocalPortAvailable -Port 5175 -ServiceName "EduScan web app"

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
$webOrigin = 'http://127.0.0.1:5175'
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
  $node = (Get-Command node.exe -ErrorAction Stop).Source
  $viteScript = Join-Path $projectRoot 'node_modules\vite\bin\vite.js'
  $api = Start-Process -FilePath $python -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" -WorkingDirectory $backendRoot -RedirectStandardOutput (Join-Path $logDirectory "api.stdout.log") -RedirectStandardError (Join-Path $logDirectory "api.stderr.log") -WindowStyle Hidden -PassThru
  $web = Start-Process -FilePath $node -ArgumentList ('"' + $viteScript + '" --host 127.0.0.1 --port 5175') -WorkingDirectory $projectRoot -RedirectStandardOutput (Join-Path $logDirectory "web.stdout.log") -RedirectStandardError (Join-Path $logDirectory "web.stderr.log") -WindowStyle Hidden -PassThru
  Wait-EduScanEndpoint -Uri "http://127.0.0.1:8000/api/health" -Process $api -ServiceName "EduScan API" -ErrorLog "logs\api.stderr.log"
  Wait-EduScanEndpoint -Uri "http://127.0.0.1:5175" -Process $web -ServiceName "EduScan web app" -ErrorLog "logs\web.stderr.log"
  Write-Host "EduScan API ready (PID $($api.Id)): http://127.0.0.1:8000/api/health"
  Write-Host "EduScan web app ready (PID $($web.Id)): http://127.0.0.1:5175"
  Write-Host "Logs: $logDirectory"
} catch {
  if ($api) { Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue }
  if ($web) { Stop-Process -Id $web.Id -Force -ErrorAction SilentlyContinue }
  throw 'EduScan startup failed. Check logs\api.stderr.log and logs\web.stderr.log.'
}





if ($Wait) {
  try {
    Write-Host "EduScan is running in foreground. Press Ctrl+C to stop."
    Wait-Process -Id $api.Id, $web.Id
  } finally {
    if ($api) { Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue }
    if ($web) { Stop-Process -Id $web.Id -Force -ErrorAction SilentlyContinue }
  }
}

