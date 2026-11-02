# EduScan installation and update guide

This guide is for a Windows laptop used as an EduScan server or gate station. Dependency installation needs internet access once. After installation, the web app, MySQL/SQLite, LBPH recognition, XLSX reports, and the Android SMS Gateway Local Server can operate on the local laptop/LAN without internet access.

## Prerequisites

- Git for Windows
- Python 3.12 (the `py -3.12` command is recommended)
- Node.js 22.12+ (or 20.19+) with npm
- A webcam
- Optional: MySQL Community Server 8.x and its command-line client tools
- Optional: an Android phone with a SIM and SMS Gateway for Android in Local Server mode

Verify the required commands in PowerShell:

```powershell
git --version
py -3.12 --version
node --version
npm --version
```

## Fresh clone and automatic dependency setup

```powershell
Set-Location "$HOME\Documents"
git clone https://github.com/Shizukesasss/EduScan.git
Set-Location ".\EduScan"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& ".\scripts\setup.ps1"
```

The setup script creates `backend\.venv`, installs pinned Python requirements, installs the locked npm dependency tree, creates `backend\.env` from the safe example when missing, and preserves existing configuration/data on later runs. If Python, pip, npm, or database seeding fails, setup stops with an error; fix that error before starting EduScan.

To supply another official SF2 workbook during setup:

```powershell
& ".\scripts\setup.ps1" -Sf2Template "C:\path\School Form 2 (SF2) Daily Attendance Report of Learners.xlsx"
```

## Database choice

SQLite is the zero-configuration local default and is suitable for a single-laptop demonstration. MySQL is supported for the intended multi-client school deployment, centralized account records, managed database service, and independent database administration. Password security and role-based authorization are implemented by EduScan for either backend; choosing MySQL does not replace application access control.

For MySQL, complete MySQL Configurator, keep the service running, and then use the interactive migration/configuration tool:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& ".\scripts\configure-eduscan-mysql.ps1"
```

The script prompts securely for the MySQL root password and EduScan backup passphrase, creates/restricts the application account, preserves a safety backup, copies existing SQLite records when applicable, verifies row counts, and updates `backend\.env`. Do not commit that file. Normal same-laptop use should connect through `127.0.0.1`; public internet exposure of MySQL is unnecessary.

## Start EduScan

```powershell
& ".\scripts\start.ps1"
```

Open `http://127.0.0.1:5175`. The startup script waits for both the API and web app, applies pending versioned migrations, and reports a useful log path if either process fails. In Command Prompt, `scripts\eduscan.cmd start` and `scripts\eduscan.cmd restart` use the managed launcher; a remote database prompts before startup migrations and seed data.

The Git repository contains the app, pinned dependency manifests, workbook templates, and the public face-processing ONNX files. It does not contain `backend\.env`, generated reports, the local database, enrolled face files, the trained LBPH model, or the encryption and signing secrets. A new SQLite installation starts with demo school records but no enrolled faces. Enroll authorized people to train a new local model, or use the controlled encrypted backup and restore process to move an existing school's database and matching biometric artifacts together. Connecting to a shared PostgreSQL database without the corresponding private files and key leaves recognition unavailable.

## Pull a newer version

Commit or copy aside your own source-code changes first. Runtime data and secrets under `backend\data` and `backend\.env` are ignored and are not replaced by Git.

```powershell
Set-Location "C:\path\to\EduScan"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& ".\scripts\update.ps1"
```

The update command permits only a fast-forward pull and reruns the idempotent dependency setup. Start EduScan normally afterward. If the working tree contains source changes, the script stops instead of overwriting them.

## Offline demonstration checklist

1. Run setup while internet is available.
2. Start EduScan once and change every bootstrap password.
3. Confirm the MySQL service starts automatically, if MySQL is selected.
4. Put the laptop and Android phone on the same local hotspot/Wi-Fi and reserve the phone IP.
5. Use System Setup to check the gateway and send a real test SMS.
6. Enroll authorized faces and confirm the scanner reports recognition ready before leaving for the demonstration.
7. Create an encrypted backup and copy it to approved off-device storage.
8. Disconnect internet and verify `http://127.0.0.1:5175`, scanner camera permission, report generation, and local phone reachability. A hosted PostgreSQL database still requires its network connection.

Internet is still needed for Git pulls, npm/pip installation, and any non-local documentation links. The Android phone needs cellular signal/credit for SMS, but the laptop-to-phone API connection uses only the local network.

## Common startup issues

- `running scripts is disabled`: use the process-scoped `Set-ExecutionPolicy` command above. It ends when that PowerShell window closes.
- Port 8000 or 5175 is occupied: close the older EduScan process and rerun `start.ps1`.
- MySQL connection refused: open Windows Services, start the `MySQL80` service, and recheck `DATABASE_URL` in `backend\.env`.
- Camera cannot start while OBS is open: close OBS's camera source, then manually enable the camera again. EduScan does not silently select another camera or take control from another application.
- Phone unreachable: verify the Local Server is running, both devices are on the same LAN, the saved IP is current, and the firewall permits that private-LAN connection.
