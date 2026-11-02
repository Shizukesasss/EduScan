param(
  [string]$Sf2Template = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendRoot = Join-Path $projectRoot "backend"
$venvPython  = Join-Path $backendRoot ".venv\Scripts\python.exe"

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
  throw "Node.js/npm was not found. Install the Node.js LTS release, reopen PowerShell, and rerun setup."
}

# ── Python virtual environment ────────────────────────────────────────────────
if (-not (Test-Path -LiteralPath $venvPython)) {
  $pythonCommand = Get-Command py -ErrorAction SilentlyContinue
  if ($pythonCommand) {
    & $pythonCommand.Source -3.12 --version > $null 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Python 3.12 is required. Install it, reopen PowerShell, and rerun setup." }
    & $pythonCommand.Source -3.12 -m venv (Join-Path $backendRoot ".venv")
  } else {
    $pythonCommand = Get-Command python -ErrorAction Stop
    & $pythonCommand.Source -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)"
    if ($LASTEXITCODE -ne 0) { throw "Python 3.12 is required. Install it, reopen PowerShell, and rerun setup." }
    & $pythonCommand.Source -m venv (Join-Path $backendRoot ".venv")
  }
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
    throw "Python virtual environment creation failed."
  }
}

& $venvPython -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)"
if ($LASTEXITCODE -ne 0) { throw "backend\.venv must use Python 3.12. Remove that environment and rerun setup." }
& $venvPython -m pip install --upgrade pip --quiet
if ($LASTEXITCODE -ne 0) { throw "Updating pip failed. Check the network connection and rerun setup." }
& $venvPython -m pip install -r (Join-Path $backendRoot "requirements.txt") --quiet
if ($LASTEXITCODE -ne 0) { throw "Installing backend requirements failed. Check the pip error above and rerun setup." }

# ── Environment file ──────────────────────────────────────────────────────────
$environmentFile = Join-Path $backendRoot ".env"
if (-not (Test-Path -LiteralPath $environmentFile)) {
  Copy-Item -LiteralPath (Join-Path $backendRoot ".env.example") -Destination $environmentFile
  Write-Host "  Created backend\.env from .env.example — review it before starting EduScan."
}

# ── SF2 template ──────────────────────────────────────────────────────────────
if ($Sf2Template) {
  $sourceTemplate = (Resolve-Path -LiteralPath $Sf2Template).Path
  $templateDirectory = Join-Path $backendRoot "data\templates"
  New-Item -ItemType Directory -Path $templateDirectory -Force | Out-Null
  Copy-Item -LiteralPath $sourceTemplate -Destination (Join-Path $templateDirectory "School Form 2 (SF2) Daily Attendance Report of Learners.xlsx") -Force
}

# ── Database bootstrap ────────────────────────────────────────────────────────
# If DATABASE_URL in .env points to SQLite and the database file does not yet
# exist, run the seed script automatically so the app is ready out of the box.
# If DATABASE_URL points to PostgreSQL (or MySQL), seeding is skipped here —
# connect to your central server and EduScan's own migrations will apply the
# schema on first start.
$dbPath = Join-Path $backendRoot "data\eduscan.db"
$usePostgres = $false
if (Test-Path -LiteralPath $environmentFile) {
  $envContent = Get-Content -LiteralPath $environmentFile -Raw
  if ($envContent -match "DATABASE_URL\s*=\s*(postgresql|mysql)") {
    $usePostgres = $true
  }
}

if (-not $usePostgres -and -not (Test-Path -LiteralPath $dbPath)) {
  Write-Host ""
  Write-Host "  No local database found — seeding demo SQLite database..."
  Push-Location $backendRoot
  try {
    & $venvPython seed_demo.py
    if ($LASTEXITCODE -ne 0) { throw "Creating the local demo database failed. Check the error above and rerun setup." }
  } finally {
    Pop-Location
  }
  Write-Host "  Demo database ready at backend\data\eduscan.db"
  Write-Host "  Default logins: admin/admin123  teacher/teacher123  scanner/scanner123"
} elseif ($usePostgres) {
  Write-Host "  PostgreSQL/MySQL DATABASE_URL detected — skipping local seed."
  Write-Host "  EduScan will apply schema migrations to your central server on first start."
}

# ── npm dependencies ──────────────────────────────────────────────────────────
Push-Location $projectRoot
try {
  & npm.cmd ci --silent
  if ($LASTEXITCODE -ne 0) { throw "Installing frontend dependencies failed. Check the npm error above and rerun setup." }
} finally { Pop-Location }

Write-Host ""
Write-Host "Setup complete. Run:  .\scripts\start.ps1"
Write-Host "For centralized PostgreSQL setup, see:  docs\POSTGRESQL_SETUP.md"
