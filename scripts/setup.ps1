param(
  [string]$Sf2Template = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendRoot = Join-Path $projectRoot "backend"
$venvPython  = Join-Path $backendRoot ".venv\Scripts\python.exe"

function Test-Python312 {
  param([string]$Executable, [string[]]$Prefix = @())
  $previousPreference = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    & $Executable @Prefix -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)" 2>$null
    return $LASTEXITCODE -eq 0
  } finally {
    $ErrorActionPreference = $previousPreference
  }
}

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
  throw "Node.js/npm was not found. Install the Node.js LTS release, reopen PowerShell, and rerun setup."
}

# Python virtual environment
if (-not (Test-Path -LiteralPath $venvPython)) {
  $pythonCommand = Get-Command py -ErrorAction SilentlyContinue
  if ($pythonCommand -and (Test-Python312 -Executable $pythonCommand.Source -Prefix @('-3.12'))) {
    & $pythonCommand.Source -3.12 -m venv (Join-Path $backendRoot ".venv")
  } else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand -or -not (Test-Python312 -Executable $pythonCommand.Source)) {
      throw "Python 3.12 is required. Install it, reopen PowerShell, and rerun setup."
    }
    & $pythonCommand.Source -m venv (Join-Path $backendRoot ".venv")
  }
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
    throw "Python virtual environment creation failed."
  }
}

if (-not (Test-Python312 -Executable $venvPython)) { throw "backend\.venv must use Python 3.12. Remove that environment and rerun setup." }
& $venvPython -m pip install --upgrade pip --quiet
if ($LASTEXITCODE -ne 0) { throw "Updating pip failed. Check the network connection and rerun setup." }
& $venvPython -m pip install -r (Join-Path $backendRoot "requirements.txt") --quiet
if ($LASTEXITCODE -ne 0) { throw "Installing backend requirements failed. Check the pip error above and rerun setup." }

# Environment file
$environmentFile = Join-Path $backendRoot ".env"
if (-not (Test-Path -LiteralPath $environmentFile)) {
  Copy-Item -LiteralPath (Join-Path $backendRoot ".env.example") -Destination $environmentFile
  Write-Host "  Created backend\.env from .env.example - review it before starting EduScan."
}

# SF2 template
if ($Sf2Template) {
  $sourceTemplate = (Resolve-Path -LiteralPath $Sf2Template).Path
  $templateDirectory = Join-Path $backendRoot "data\templates"
  New-Item -ItemType Directory -Path $templateDirectory -Force | Out-Null
  Copy-Item -LiteralPath $sourceTemplate -Destination (Join-Path $templateDirectory "School Form 2 (SF2) Daily Attendance Report of Learners.xlsx") -Force
}

# Database bootstrap
# Seed a fresh local SQLite database when demo accounts are enabled.
# If DATABASE_URL points to PostgreSQL (or MySQL), seeding is skipped here -
# connect to your central server and EduScan's own migrations will apply the
# schema on first start.
$dbPath = Join-Path $backendRoot "data\eduscan.db"
$databaseUrl = [System.Environment]::GetEnvironmentVariable('DATABASE_URL', 'Process')
$demoAccounts = [System.Environment]::GetEnvironmentVariable('EDUSCAN_SEED_DEMO_ACCOUNTS', 'Process')
if (($null -eq $databaseUrl -or $null -eq $demoAccounts) -and (Test-Path -LiteralPath $environmentFile)) {
  foreach ($rawLine in [System.IO.File]::ReadAllLines($environmentFile)) {
    $line = $rawLine.Trim()
    if (-not $line -or $line.StartsWith('#') -or -not $line.Contains('=')) { continue }
    $separator = $line.IndexOf('=')
    $key = $line.Substring(0, $separator).Trim()
    if ($null -eq $databaseUrl -and $key -ceq 'DATABASE_URL') {
      $databaseUrl = $line.Substring($separator + 1).Trim()
    }
    if ($null -eq $demoAccounts -and $key -ceq 'EDUSCAN_SEED_DEMO_ACCOUNTS') {
      $demoAccounts = $line.Substring($separator + 1).Trim()
    }
  }
}
$useRemoteDatabase = $databaseUrl -match '^(?i:postgresql|mysql)(?:\+[^:]+)?:'

if (-not $useRemoteDatabase -and ($null -eq $demoAccounts -or $demoAccounts -eq 'true') -and -not (Test-Path -LiteralPath $dbPath)) {
  Write-Host ""
  Write-Host "  No local database found - seeding demo SQLite database..."
  Push-Location $backendRoot
  try {
    & $venvPython seed_demo.py
    if ($LASTEXITCODE -ne 0) {
      # This branch ran only when the database file was absent. Remove the
      # incomplete database so the next setup attempt can retry cleanly.
      if (Test-Path -LiteralPath $dbPath) { Remove-Item -LiteralPath $dbPath -Force }
      throw "Creating the local demo database failed. Check the error above and rerun setup."
    }
  } finally {
    Pop-Location
  }
  Write-Host "  Demo database ready at backend\data\eduscan.db"
  Write-Host "  Default logins: admin/admin123  teacher/teacher123  scanner/scanner123"
} elseif ($useRemoteDatabase) {
  Write-Host "  PostgreSQL/MySQL DATABASE_URL detected - skipping local seed."
  Write-Host "  Run the PostgreSQL maintenance migration before starting EduScan. MySQL retains startup migrations."
}

# npm dependencies
Push-Location $projectRoot
try {
  & npm.cmd ci --silent
  if ($LASTEXITCODE -ne 0) { throw "Installing frontend dependencies failed. Check the npm error above and rerun setup." }
} finally { Pop-Location }

Write-Host ""
Write-Host "Setup complete. Run:  .\scripts\start.ps1"
Write-Host "For centralized PostgreSQL setup, see:  docs\POSTGRESQL_SETUP.md"
