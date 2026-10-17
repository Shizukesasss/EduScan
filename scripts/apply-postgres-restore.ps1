$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendRoot = Join-Path $projectRoot "backend"
$python = Join-Path $backendRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "The backend virtual environment is missing." }
if (Test-NetConnection -ComputerName 127.0.0.1 -Port 8000 -InformationLevel Quiet -WarningAction SilentlyContinue) {
  throw "Stop EduScan before applying a PostgreSQL restore. Stop any other scanners sharing this database too."
}
$confirmation = Read-Host "Stop all EduScan scanners using this database, then type APPLY POSTGRES RESTORE"
if ($confirmation -cne "APPLY POSTGRES RESTORE") { throw "Restore cancelled." }
$securePassphrase = Read-Host "New passphrase for the automatic safety backup (12 or more characters)" -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassphrase)
try {
  $env:EDUSCAN_RESTORE_CONFIRM = $confirmation
  $env:EDUSCAN_BACKUP_PASSPHRASE = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
  if ($env:EDUSCAN_BACKUP_PASSPHRASE.Length -lt 12) { throw "The passphrase is too short." }
  & $python (Join-Path $backendRoot "tools\apply_postgres_restore.py")
  if ($LASTEXITCODE -ne 0) { throw "Restore stopped. Keep the safety backup and review the error before retrying." }
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
  Remove-Item Env:EDUSCAN_RESTORE_CONFIRM -ErrorAction SilentlyContinue
  Remove-Item Env:EDUSCAN_BACKUP_PASSPHRASE -ErrorAction SilentlyContinue
}
