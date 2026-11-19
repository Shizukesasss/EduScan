# EduScan

EduScan is the local-first attendance, SMS, grading, and SF2 reporting system for San Jose National High School. The browser captures camera frames; the local EduScan API compares faces with SFace references, maintains an LBPH model for diagnostics, and checks liveness. Camera frames are not sent to a cloud recognition provider.

## Quick start on Windows

Install [Git](https://git-scm.com/download/win), [Python 3.12](https://www.python.org/downloads/windows/), and [Node.js 22.12 or newer](https://nodejs.org/en/download). Keep your internet connection available while setup downloads dependencies. Then run the following in PowerShell.

```powershell
git clone https://github.com/Shizukesasss/EduScan.git
Set-Location .\EduScan
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

Double-click `Start EduScan.cmd` and click **Start EduScan**. The launcher also has **Restart EduScan**, **Close EduScan**, and **Start API Server**. After installation, the launcher runs independently of Codex.

Open the app at [http://127.0.0.1:5175](http://127.0.0.1:5175). On a fresh local demo, sign in as `admin` with `admin123` and set a new password when prompted. The demo also includes `teacher` / `teacher123` and `scanner` / `scanner123`. Use a webcam for enrollment and gate recognition.

### Choose your installation

| Use case | What to do |
| --- | --- |
| Local demo on one PC | Keep **Configured database** in the launcher. The fresh setup uses SQLite and bundles the report templates and public recognition models. |
| Offline gate station | Select **Offline (local SQLite)** and restart. This profile has its own database. To sync records and punches, configure the school connection and certificate first. [Managed offline station](docs/INSTALLATION.md#managed-offline-station) |
| Existing school installation | Configure the school's restricted database login in `backend/.env` and use the matching encrypted backup for the school's face samples, trained model, and keys. [PostgreSQL / Supabase setup](docs/POSTGRESQL_SETUP.md) · [Backup and recovery](docs/DISASTER_RECOVERY.md) |
| Hosted installation | Build the Vite frontend on Vercel with `VITE_API_URL` pointing to the persistent FastAPI host. [Vercel and persistent API setup](docs/INSTALLATION.md#vercel-frontend-and-persistent-api) |

If the app fails to open, check the [local API health endpoint](http://127.0.0.1:8000/api/health) and the `logs/` folder. For terminal controls, run `scripts\eduscan.cmd start` or `scripts\eduscan.cmd restart`. For development, `npm run dev` runs the API and Vite in the foreground on ports 8000 and 5173.

School records, biometric samples, trained models, generated reports, credentials, and encryption keys belong in the school's private installation and backups. Keep them out of Git.

## Documentation

- [Installation and update guide](docs/INSTALLATION.md) — clean clone, dependencies, MySQL, offline demonstration, and safe updates
- [Project structure and file guide](docs/PROJECT_STRUCTURE.md) — architecture, request flow, and the purpose of every maintained source file
- [RAD progress report](docs/RAD_PROGRESS_REPORT.txt) — completed work organized around Rapid Application Development phases
- [Disaster-recovery procedure](docs/DISASTER_RECOVERY.md) — encrypted backup, integrity verification, staged restoration, and recovery testing
- [SQLite to MySQL migration](docs/MYSQL_MIGRATION.md) — non-destructive copy, row-count verification, cutover, and rollback
- [PostgreSQL / Supabase setup](docs/POSTGRESQL_SETUP.md) and [recovery](docs/POSTGRES_RECOVERY.md) — database connection and controlled encrypted recovery
- [Android SMS Gateway setup](docs/ANDROID_SMS_GATEWAY.md) — offline LAN setup, connection tests, and troubleshooting

## Implemented system

- Actual camera capture for enrollment and gate recognition
- OpenCV Haar face extraction and LBPH training/prediction
- Minimum-quality and one-face-only enrollment checks
- Encrypted biometric samples and models outside the web root; versioned LBPH models with SHA-256 integrity records
- Audited biometric CRUD; deletion purges encrypted samples, sample rows, obsolete LBPH files, and obsolete model rows while retaining only the required non-biometric audit record
- Persistent SQLAlchemy database (SQLite by default; MySQL and PostgreSQL/Supabase supported through `DATABASE_URL`)
- Student, faculty, and non-teaching personnel attendance
- Accepted matches alternate automatically between time-in and time-out after the duplicate-scan cooldown, supporting repeated exits and re-entries
- Administrator-defined faculty and non-teaching duty schedules, late-grace classification, and schedule-aware automatic absence closing
- Multi-face gate frames are detected and each distinct enrolled person is matched independently
- Enlarged 16:9 gate camera workspace with a whole-frame multi-face guide and optional browser full-screen mode
- Administrator-managed teacher schedules and tardiness grace periods; teachers view their own schedules in Schedules and Reports
- Teacher Reports show read-only official SF2 snapshots generated by administrators for assigned classes; attendance report generation, downloads, and printing are administrator-managed
- Holidays, suspensions, weekends, excused absences, and authorized special schedules
- Automatic daily absence closing, temporary XLSX generation, and SMS dispatch at the authorized cutoff
- Per-section and per-personnel-schedule absence cutoffs so later or special schedules are not closed early
- Immutable gate events plus attributable teacher/admin correction records
- Real Android SMS Gateway local-server integration for time-in, time-out, tardiness, and absence notices
- Encrypted gateway password storage, event-idempotent outbox records, scheduled retries, and a configurable local sending limit
- Android delivery reconciliation with queued/accepted/processed/sent/delivered/failed/exhausted/cancelled states, authorized requeue/cancellation, and CSV delivery export
- Adviser-scoped, teacher-configurable quizzes, summative tests, periodic tests, overall grade input, server-validated scores, and DepEd transmutation display
- Raw-score grading with highest-possible scores, missing/excused/incomplete states, finalization locks, authorized reason-based reopening, class statistics, printable summaries, and XLSX exports
- XLSX exports follow the saved gradebook's activity maxima, components, weights, rounding, and grade conversion. Matching JHS setups retain their subject templates; custom setups and SHS use a flexible workbook with live formulas. Exporting never changes saved scores or grading policies.
- School-year, grading-period, quarter, subject, grade-level, and section organization with grade-change audit history
- Date-range student/personnel attendance exports with batched daily reads, isolated download files, registered report hashes, and records-officer review/approval history
- Administrative CRUD for accounts, students, employees, grade levels, sections, and subjects
- Restricted records-officer, privacy-officer, and ICT roles plus a unified before/after administrative audit
- Alphabetically arranged male/female SF2 placement from school records
- Separate full school-record disposal with an attributable, non-identifying disposal audit
- Passphrase-encrypted backup/restoration of SQLite, MySQL, or PostgreSQL together with the matching application secret, encryption key, biometric artifacts, models, and templates. See [PostgreSQL recovery](docs/POSTGRES_RECOVERY.md).
- Daily/weekly encrypted backup scheduling, rotation, off-device copies, run inventory, failure visibility, key fingerprint, model version, and file integrity hash
- Approval-driven retention previews, legal holds, expired operational-record cleanup, and disposal certificates without deleting official attendance/grade records outside an approved schedule
- Blink-based liveness gating, spoof-suspicion/unknown-face review records without retained review images, and a documented correction fallback
- Gate-station API/database/camera/SMS/model health indicators and a controlled recognition-loop restart
- Recorded database migrations and tested disaster-recovery procedure
- Real temporary attendance XLSX and official SF2 XLSX generation using the supplied template and sex-specific row blocks
- Operational attendance, enrollment, SMS gateway, and personnel schedule controls under System Setup

### Optional custom SF2 template

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -Sf2Template "C:\path\to\School Form 2 (SF2) Daily Attendance Report of Learners.xlsx"
```

## First-use sequence

1. Log in as administrator.
2. In System Setup, create each grade/section class schedule and each applicable faculty/non-teaching duty schedule, then set the late grace periods.
3. If the school uses SMS, open **System Setup → SMS delivery → Gateway settings**, enter the phone gateway URL and credentials, save, and send a test message.
4. Open **Gate Station → Station actions → Register person**. Enter the school record, confirm the documented authorization, and follow the camera prompts.
5. Enroll every authorized student/personnel member. The model is retrained after each enrollment.
6. Log in with the scanner account on the secured gate laptop, enable the camera, and start recognition. The accepted events alternate automatically between time-in and time-out.
7. Review Attendance and make corrections with reasons. The server closes absences automatically at the authorized cutoff; administrators can run the same controlled action manually for operational recovery.
8. In **Reports → Monthly SF2**, generate the monthly workbook using the bundled or school-supplied template. To compare a saved PDF with a submitted copy, open **Reports → Report history** and select **Verify PDF** beside the original.
9. Open Administration for accounts, school records, school-year and class setup, activity audit, data management, and backup and recovery according to your role. People & records can create a school record without camera enrollment. Review recognition issues in Attendance, service health in Overview, and SMS delivery and face controls in System Setup.

### Recognition check before a large school test

EduScan trains a local LBPH model after enrollment, but gate identity is decided by SFace feature comparisons; the LBPH distance is retained for audit. Enrollment currently requires pairwise SFace similarity of at least 0.65 among captured frames and among reusable stored references. Each reusable reference must also agree with the capture. Gate matching requires three corroborating stored references, a score of at least 0.413, and a lead of at least 0.05 over the next candidate. These are provisional conservative cutoffs, **not measured accuracy guarantees**. They can reject genuine people as uncertain. Before admitting people with automatic attendance, enroll authorized people one at a time, then use separate live camera sessions to test each person's recognition and blink check. Include people who have **not** been enrolled, similar-looking people where available, and groups of up to five. Record false matches, missed matches, ambiguous rejections, and scan time; investigate every false match before wider use. Uncertain or inconsistent results should be handled by verified staff assistance. Do not put face images, embeddings, or encryption keys in Git.

## Build verification

```powershell
npm run verify
.\backend\.venv\Scripts\python.exe -m compileall -q backend\app
```

For the automated suites, install the optional test runner (`.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt`), then run `node --test` and `.\backend\.venv\Scripts\python.exe -m pytest backend\tests`. The backend tests use isolated test databases; physical camera recognition, SMS delivery, and backup restoration still require a controlled device and recovery drill.

The tested recovery runbook is in `docs/DISASTER_RECOVERY.md`. Its isolated verification command is:

```powershell
.\scripts\test-disaster-recovery.ps1
```

## Android phone SMS gateway

Use [SMS Gateway for Android](https://github.com/capcom6/android-sms-gateway) in Local Server mode. Keep the phone and EduScan server on the same protected school network. The backend sends HTTP Basic-authenticated `POST /message` requests to the phone. Do not expose the gateway directly to the internet. Use a school-controlled SIM, confirm the carrier plan permits the intended institutional messages, reserve the phone IP, enable kiosk/battery-exemption settings, and monitor the outbox.

## Biometric storage

Each enrollment frame must contain exactly one clear human face. A bundled OpenCV YuNet detector checks facial landmark geometry and agreement with the LBPH crop before the frame can be saved. Missing or damaged detector files block enrollment. Animals, objects, and unverified frames are rejected by the enrollment checks; camera validation is required because face detection is probabilistic and is not a guarantee against every false positive or photo/video spoof.

Enrollment rejects exact duplicate crops and repeated SFace matches against other authorized enrollments. Re-enrollment excludes that person's own samples from the duplicate check. The station can enroll people when older sample files are missing, and it records which enrollments could not be checked. Unreadable files or failed integrity checks block the operation. PostgreSQL enrollment transactions are serialized so simultaneous requests use the same duplicate check. Verify identities with authorized camera captures under the station's lighting. Previously recorded duplicate enrollments require separate review.

LBPH does not produce a reusable single face vector suitable for a document column. EduScan stores quality-checked grayscale face crops as individually Fernet-encrypted files under `backend/data/biometrics`, and stores paths, hashes, consent state, and model metadata in SQL. The trained LBPH YAML is also Fernet-encrypted under `backend/data/models` and is decrypted only to a short-lived local file while OpenCV loads it. This keeps structured records in SQL while treating biometric artifacts as encrypted files. Back up `backend/data/.encryption_key` securely; losing it makes the samples and models unreadable.

## Deployment responsibility

The code keeps biometric operation available for controlled development and technical evaluation. Before processing real students at the gate, obtain the written determinations and approvals required by the school and applicable rules through the school's real-world process. EduScan does not record or grant those approvals.
