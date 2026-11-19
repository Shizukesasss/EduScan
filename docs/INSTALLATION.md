# EduScan installation and update guide

This guide is for a Windows laptop used as an EduScan server or gate station. Dependency installation needs internet access once. After installation, the web app, MySQL/SQLite, LBPH recognition, PDF reports, and the Android SMS Gateway Local Server can operate on the local laptop/LAN without internet access.

## Prerequisites

- Git for Windows
- Python 3.12 (the `py -3.12` command is recommended)
- Node.js 22.12+ (or 20.19+) with npm
- Microsoft Excel is optional. On Windows, EduScan uses Excel's print layout when Excel automation is available. The built-in renderer provides workbook PDFs on other hosts and when Excel export fails.
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

The separate `backend\seed_demo.py` command **replaces** the local SQLite demo database. Use it only for a disposable local demonstration, never to update an installation containing school records. Normal setup runs it only when no local database exists.

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

Open `http://127.0.0.1:5175`. The startup script waits for both the API and web app and reports a log path if either process fails. SQLite and MySQL apply pending migrations on startup. PostgreSQL verifies the migration ledger and uses a separate [maintenance command](POSTGRESQL_SETUP.md) to apply migrations before startup. In Command Prompt, `scripts\eduscan.cmd start` and `scripts\eduscan.cmd restart` use the managed launcher.

For a shared SQLite installation, set `EDUSCAN_SEED_DEMO_ACCOUNTS=false` before running setup and set `EDUSCAN_ENABLE_API_DOCS=false` before starting the API. Use the same [named administrator setup](POSTGRESQL_SETUP.md) for fresh databases running without demo accounts.

### Browser sessions

After updating both the API and web app, sign in again. The versioned database migrations create the session table. EduScan issues an eight-hour HttpOnly session cookie, and the web app clears the previous browser-stored credentials on load.

The supplied launcher uses matching loopback hosts for the web app and API. For a shared installation, serve both over HTTPS. The hosted frontend defaults to `/api` on the same origin. A separate API origin can be configured with `VITE_API_URL` when the web app and API are on the same site. Set `ALLOWED_ORIGINS` to the exact browser origin, including its port when applicable. If TLS terminates at a reverse proxy, configure the API to trust forwarded scheme information only from that proxy. Other HTTP hosts cannot issue or use sessions.

API integrations use a cookie jar and send `X-EduScan-Request: 1` on authentication and authenticated requests. Password and Google sign-in set the cookie, `GET /api/auth/me` verifies it, and `POST /api/auth/logout` revokes it. Local interactive API docs show the schema. Use a cookie-aware client to exercise authenticated routes.

The Git repository contains the app, pinned dependency manifests, workbook templates, and the public face-processing ONNX files. It does not contain `backend\.env`, generated reports, the local database, enrolled face files, the trained LBPH model, or the encryption and signing secrets. A new SQLite installation starts with demo school records but no enrolled faces. Enroll authorized people to train a new local model, or use the controlled encrypted backup and restore process to move an existing school's database and matching biometric artifacts together. Connecting to a shared PostgreSQL database without the corresponding private files and key leaves recognition unavailable.

### Storage quotas

Set these positive whole MiB values in `backend\.env` and restart the API to change the limits.

| Setting | Default | What it counts |
| --- | ---: | --- |
| `EDUSCAN_BIOMETRIC_STORAGE_MIB` | 1024 MiB | Encrypted face samples in the biometric directory |
| `EDUSCAN_REPORT_STORAGE_MIB` | 2048 MiB | Saved exports, including registered reports and daily attendance files |
| `EDUSCAN_BACKUP_STORAGE_MIB` | 4096 MiB | Encrypted `.edubak` archives in the local backup directory and, independently, each managed off-device destination |

When a new write would exceed its quota, EduScan returns HTTP 507 and preserves the existing files. Replacing an enrollment credits the samples it supersedes. Leave free disk space for models, report generation, file replacements, and expanded restore staging. See the [disaster-recovery procedure](DISASTER_RECOVERY.md) for the pre-restore backup requirement.

### API request rate limits

Set positive whole requests-per-minute values in `backend\.env` and restart the API to change these defaults.

| Setting | Sustained requests per minute | Maximum immediate burst |
| --- | ---: | ---: |
| `EDUSCAN_CAMERA_REQUESTS_PER_MINUTE` | 120 | 12 |
| `EDUSCAN_REPORT_REQUESTS_PER_MINUTE` | 30 | 30 |
| `EDUSCAN_BACKUP_REQUESTS_PER_MINUTE` | 6 | 6 |
| `EDUSCAN_PASSWORD_SIGN_IN_REQUESTS_PER_MINUTE` | 30 | 20 |
| `EDUSCAN_GOOGLE_SIGN_IN_REQUESTS_PER_MINUTE` | 30 | 20 |
| `EDUSCAN_RESET_REQUESTS_PER_MINUTE` | 12 | 12 |
| `EDUSCAN_RESET_CONFIRMATIONS_PER_MINUTE` | 30 | 15 |
| `EDUSCAN_SMS_REQUESTS_PER_MINUTE` | 20 | 20 |

Camera enrollment, recognition and test uploads share the camera budget. Report generation covers exports, print views and generated PDF previews. Backup creation, download and restore staging share the backup budget. Smaller configured rates also lower the burst ceiling. The API returns HTTP 429 with a `Retry-After` delay in seconds. The scanner waits that long before starting its next capture.

Password sign-in, Google sign-in, reset-code requests and reset confirmations have independent budgets. The existing account lockout, reset-code cooldown and guess limit still apply. SMS test, dispatch, requeue, reconciliation and gateway-check requests share the SMS budget. Cancellation has its own budget at the same rate.

Budgets are tracked in memory per client address and API process. For proxied deployments, configure the API server to accept forwarded client addresses only from trusted proxies. Multi-worker or multi-replica deployments can enforce an aggregate limit at their shared reverse proxy.

All outbound SMS send attempts in an API process share `EDUSCAN_SMS_GATEWAY_REQUESTS_PER_MINUTE`, which defaults to 30 per minute with a burst of up to 25. This includes failed gateway attempts, manual tests, attendance and enrollment notices, and scheduled retries. When that budget is exhausted, notifications stay queued without consuming a delivery retry. The configured 30-minute SMS delivery allowance also applies.

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

## Vercel frontend and persistent API

Use the repository root for the Vercel project. Set `VITE_API_URL` to the always-on API's HTTPS URL, including the `/api` suffix (for example, `https://api.example.edu/api`). The Vercel build requires that setting. Uploads go from the browser directly to the API host, where EduScan's own upload limits apply. Only the Vite app is deployed to Vercel.

On the persistent API host, create an ignored `backend/.env.production` from `backend/.env.example`. Set the restricted PostgreSQL `DATABASE_URL` and the deployment's stable `EDUSCAN_SECRET_KEY` and `EDUSCAN_ENCRYPTION_KEY`. For an existing installation, use the keys that belong to its data. Copy the verified file archive to the persistent data volume before starting the API. Keep the `biometrics`, `models`, `templates`, `exports/registered`, and `backups` subdirectories in their original layout. Report history can locate a relocated export by its original ID-based filename and validates the bytes against the stored hash.

For a Docker host, `docker compose -f compose.production.yaml up -d --build` runs one API worker with the attendance, SMS, and backup scheduler enabled. The named data volume mounts at `/var/lib/eduscan` and must be writable by UID 10001. The API binds to loopback on the host. Terminate HTTPS at the host's reverse proxy and set `FORWARDED_ALLOW_IPS` to the actual trusted proxy address as seen by the API. Keep the API host connected to the school's configured SMS gateway and any backup destination it uses. For PostgreSQL backups, the image includes PostgreSQL 17 client tools.

Run the PostgreSQL maintenance migration before starting the updated production API. Keep the owner URL in the maintenance process only. Run the access audit using the restricted runtime URL afterward.

## Managed offline station

Select **Offline (local SQLite)** in the Windows launcher when a station must keep working through an internet outage. Keep this profile running during normal operation so an outage requires no server switch. The standalone offline profile remains available for demonstrations.

For school sync, apply migration 0038 to the school database using the maintenance procedure in [PostgreSQL setup](POSTGRESQL_SETUP.md). Set `EDUSCAN_SYNC_DATABASE_URL` in the station's ignored `backend/.env` to the restricted runtime login. Use `sslmode=verify-full` and the CA certificate supplied by the database provider. Keep the database URL on the trusted station, outside browser settings.

On a station whose existing `DATABASE_URL` selects the school database, run `backend/.venv/Scripts/python.exe backend/tools/configure_station_sync.py --ca <provider-ca.pem>` from the repository root. The tool checks the remote schema and access grants over verified TLS before writing the offline sync setting. Add `--check` to verify prerequisites without writing. Restart using **Offline (local SQLite)** after configuring the station.

Before enabling sync, provision the local station with the school's academic structure, authorized operators with the same usernames as their school accounts, and the roster and encrypted face samples it needs. Use school-controlled passwords for local accounts. Keep the local SQLite database, encryption key, and biometric files together in the offline data directory.

The station retries pending student records and gate punches automatically. Check **System Setup → Gate network** for pending, synced, and conflict counts. Conflicts are kept for staff review. Face sample files and recognizer models remain on the station where they were enrolled. A separate station needs its own authorized capture or an approved biometric restore.

The station needs one successful policy check before its first gate capture with sync enabled. A cached unrestricted policy supports offline gate captures. A restricted policy pauses this loopback station, and the school database places incoming events in conflict if it requires a network check. Deploy restricted gate stations where the API can verify the request's approved network address. Configure only explicitly trusted reverse proxies to supply a client address.

Migration 0038 adds station receipts and lookup indexes. To roll back application behavior, stop the sync station and run the previous application version with sync disabled. Preserve the SQLite station database and the school receipt table for any later retry.

### Reporting query and schema review

Roster and biometric-enrollment lists fetch sample counts or summaries with the people they display. Gate history reads a bounded set of punches and their SMS records. The dashboard aggregates SMS status counts in one query. Attendance ranges, SF2, and Annex G group related attendance data by date and learner. Verify performance on the school's data before changing indexes beyond migration 0038.

The schema has foreign keys for scores, attendance, academic assignments, and verified school-year learner placements. It also retains denormalized fields. Gradebooks keep display labels beside academic IDs, and legacy person rows keep current grade and section beside the verified placement history. Report and audit rows keep snapshots of names and event details. Any normalization migration must preserve historical exports and the placement fallback for earlier records. Migration 0038 does not drop or backfill those fields.

## Common startup issues

- `running scripts is disabled`: use the process-scoped `Set-ExecutionPolicy` command above. It ends when that PowerShell window closes.
- Port 8000 or 5175 is occupied: close the older EduScan process and rerun `start.ps1`.
- MySQL connection refused: open Windows Services, start the `MySQL80` service, and recheck `DATABASE_URL` in `backend\.env`.
- Camera cannot start while OBS is open: close OBS's camera source, then manually enable the camera again. EduScan does not silently select another camera or take control from another application.
- Phone unreachable: verify the Local Server is running, both devices are on the same LAN, the saved IP is current, and the firewall permits that private-LAN connection.
