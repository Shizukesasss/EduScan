# EduScan project structure

This guide explains how EduScan is organized, how a request moves through the system, and what each maintained project file is responsible for. Runtime databases, encrypted biometric artifacts, generated reports, logs, dependency folders, and local secrets are intentionally excluded from Git.

## System overview

EduScan is a local-first client-server application with layered responsibilities:

1. The React JavaScript client, built with Vite and plain CSS, renders role-based administrator, teacher, gate-scanner, records-officer, privacy-officer, and ICT interfaces.
2. `src/api/client.js` sends authenticated HTTP requests to the local FastAPI server.
3. FastAPI endpoints validate requests, enforce roles, and delegate work to backend services.
4. Service modules implement attendance, LBPH biometrics, SMS, spreadsheet reporting, imports, backups, disposal, and scheduling.
5. SQLAlchemy persists structured records in SQLite by default or in a configured MySQL or PostgreSQL server through `DATABASE_URL`. The current school deployment uses PostgreSQL on Supabase.
6. Encrypted face samples and LBPH model artifacts are stored outside the web root, while their metadata and audit history are stored in SQL.

The normal single-laptop deployment uses these local addresses:

- Web client: `http://127.0.0.1:5174`
- Backend API: `http://127.0.0.1:8000/api`
- API documentation: `http://127.0.0.1:8000/docs`

Local database deployments can run without internet after dependencies are installed. A Supabase deployment needs a network connection to its database. Android SMS delivery needs a local network connection to the gateway phone and cellular SMS service. Manrope headings and Inter body text are bundled under `public/fonts/`, with system-font fallbacks.

## Request and data flow

```text
Browser interface
    -> src/api/client.js
    -> FastAPI routes in backend/app/main.py
    -> role checks and Pydantic request validation
    -> backend service module
    -> SQLAlchemy / SQLite, MySQL, or PostgreSQL and encrypted local artifacts
    -> JSON, XLSX, or file response
    -> browser interface
```

Gate recognition follows a specialized path:

```text
Camera frame
    -> browser JPEG capture
    -> POST /api/biometrics/recognize-many
    -> Haar face detection
    -> LBPH prediction for each detected face
    -> duplicate suppression, confidence checks, and blink-based liveness state
    -> duplicate cooldown and automatic time-in/time-out alternation
    -> optional guardian SMS outbox and Android gateway dispatch
```

## Root files

- `.gitignore` — excludes dependencies, build output, local environment files, databases, biometric artifacts, logs, caches, and secrets while retaining the approved SF2 template.
- `README.md` — primary installation, operation, verification, SMS, biometric-storage, and deployment guide.
- `index.html` — Vite HTML entry document containing the React root element and favicon reference.
- `package.json` — frontend package metadata, runtime dependencies, and development commands.
- `package-lock.json` — locks exact npm dependency versions for repeatable installation.
- `vite.config.js` — enables React support in the Vite development and build pipeline.

## Public assets

- `public/favicon.svg` — browser-tab icon.
- `public/icons.svg` — reusable static icon asset retained in the public bundle.
- `public/logo.png` — school/EduScan logo used by login, administrator, teacher, and scanner headers.
- `public/fonts/` — locally bundled Manrope and Inter fonts and their licenses.

## Frontend entry and shared files

- `src/main.jsx` — mounts the React application and loads the active global stylesheet.
- `src/App.jsx` — declares application routes and client-side role guards for all six application-account roles.
- `src/api/client.js` — central API helper, authentication token storage, JSON/FormData handling, camera-frame capture, and local date/time formatting.
- `src/styles/index.css` — active global design system and responsive styles, including the enlarged scanner camera, multi-face guide, and full-screen presentation.
- `src/App.css` — original Vite starter stylesheet retained for reference; it is not imported by the current entry point.
- `src/index.css` — original Vite starter stylesheet retained for reference; the current entry point imports `src/styles/index.css` instead.
- `src/assets/hero.png` — retained local image asset that is not currently referenced by a page.
- `src/assets/react.svg` — retained Vite starter asset that is not currently referenced.
- `src/assets/vite.svg` — retained Vite starter asset that is not currently referenced.

## Frontend layouts

- `src/layouts/PublicLayout.jsx` — minimal outlet wrapper for login and the gate-scanner route.
- `src/layouts/AdminLayout.jsx` — permission-filtered operations navigation for administrators and the restricted records/privacy/ICT roles.
- `src/layouts/TeacherLayout.jsx` — teacher navigation shell for advisory reporting, attendance, roster, and interventions.

## Frontend pages

- `src/pages/Login/Login.jsx` — authenticates a user and redirects them to the interface allowed for their role.
- `src/pages/Account/AccountSecurity.jsx` — enforces first-use/reset password replacement and supports later owner-initiated password changes.
- `src/pages/Dashboard/Dashboard.jsx` — administrator summary of daily attendance, gate events, SMS status, and reporting shortcuts.
- `src/pages/Scanner/Scanner.jsx` — controls camera access, liveness-aware multi-face recognition, service health indicators, controlled recognition restart, recent events, enrollment access, and normal/full-screen presentation.
- `src/pages/Attendance/Attendance.jsx` — displays all-school or adviser-scoped attendance, groups secondary actions, downloads deduplicated alphabetical logs, runs daily closing or audited clean-slate reset, and records attributable corrections.
- `src/pages/Grading/Grading.jsx` — shared class-record workspace. Teachers enter scores for authorized classes; administrators can view records and review teacher adjustment requests, without directly editing scores or grading policies.
- `src/pages/Reports/Reports.jsx` — date-range student/personnel summaries, official SF2 generation, and hashed report review/approval history.
- `src/pages/Oversight/Oversight.jsx` — unified audit, recognition review, SMS reconciliation, retention/legal-hold, service-health, and backup-schedule workspace filtered by role.
- `src/pages/Setup/SystemSetup.jsx` — attendance rules, class and personnel duty schedules, special calendars, SMS gateway configuration and non-sending reachability diagnostics, privacy/legal evidence, access rules, and correction procedures.
- `src/pages/Administration/Administration.jsx` — administrative CRUD for people, accounts, academic references, roster imports, full record disposal, backups, and restoration.
- `src/pages/Teacher/SF2Dashboard.jsx` — teacher landing page combining subject selection, attendance, analytics, learner profiles, and SF2 access. Class-record editing is in the shared grading page.
- `src/pages/Teacher/MyAdvisory.jsx` — teacher roster view and learner profile access.
- `src/pages/Teacher/MySchedules.jsx` — adviser-scoped class schedule creation, editing, meeting-day selection, time-range setup, late-grace configuration, and removal.
- `src/pages/Teacher/TruancyInterventions.jsx` — identifies repeated absence/tardiness cases and records intervention actions.

## Frontend components

- `src/components/Scanner/StudentRegistrationModal.jsx` — captures official person details, authorization confirmation, enrollment frames, and LBPH training requests.
- `src/components/Setup/BiometricEnrollmentManager.jsx` — lists biometric enrollments and provides audited view, replace, retrain, and delete operations.
- `src/components/Teacher/SubjectSelector.jsx` — selects the current teacher class/subject context and schedule.
- `src/components/Teacher/SectionAttendance.jsx` — renders section attendance with learner status interactions.
- `src/components/Teacher/AdviserAnalyticsWidget.jsx` — summarizes advisory attendance patterns.
- `src/components/Grading/GradingSheet.jsx` — renders the class-record spreadsheet and respects the parent page's read-only permissions.
- `src/components/Grading/AssessmentConfig.jsx` — teacher assessment configuration.
- `src/components/Grading/GradebookActions.jsx` — permission-aware class-record actions and exports.
- `src/components/Grading/AdjustmentRequestsModal.jsx` and `GlobalAdjustmentsTab.jsx` — teacher adjustment requests and authorized review.
- `src/components/Grading/GradebookSummary.jsx`, `CalculationBreakdown.jsx`, `AuditHistory.jsx`, and `ValidationChecklist.jsx` — class totals, calculation details, history, and completion checks.
- `src/services/gradingCalculations.js` and `gradingWorkflow.js` — grading previews and validated score-update payloads; the backend remains authoritative.
- `src/components/Teacher/SF2ReportGenerator.jsx` — restricts advisers to assigned sections and provides official SF2 generation plus grouped template and temporary-log support actions.
- `src/components/Teacher/StudentProfileModal.jsx` — displays an individual learner profile from the roster.

## Backend foundation

- `backend/requirements.txt` — pinned Python dependencies for FastAPI, SQLAlchemy, OpenCV LBPH, encryption, HTTP, and XLSX processing.
- `backend/.env.example` — documented environment-variable template; copy to `.env` locally and never commit actual secrets.
- `backend/app/__init__.py` — marks the backend application directory as a Python package.
- `backend/app/main.py` — creates the FastAPI application, starts migrations and background scheduling, seeds references, and defines authenticated API endpoints.
- `backend/app/config.py` — loads environment settings, resolves data paths, creates per-installation application/encryption secrets, and safely applies only SQLite staged restores during startup.
- `backend/app/database.py` — creates the SQLAlchemy engine/session and applies SQLite foreign-key, WAL, and busy-timeout reliability settings.
- `backend/app/migrations.py` — registers every SQLAlchemy model, applies idempotent versioned schema changes, repairs partially upgraded attendance schemas, and records revisions in `schema_migrations`.
- `backend/app/models.py` — SQLAlchemy tables for accounts, people, class/personnel schedules, academics, attendance, biometrics, SMS, grades, imports, disposal, settings, and interventions.
- `backend/app/models_grading.py` and `schemas_grading.py` — policy-based class records, assessments, scores, adjustment requests, and their validation contracts. Older grading tables and endpoints remain for compatibility; they are not removed by source cleanup.
- `backend/app/schemas.py` — Pydantic request and response models used to validate API data.
- `backend/app/auth.py` — password hashing, token creation/validation, current-user resolution, role enforcement, and initial account seeding.

## Backend services

- `backend/app/services/__init__.py` — marks the services directory as a Python package.
- `backend/app/services/attendance.py` — instructional-day rules, adviser/report scoping, unique-ID deduplication, schedules, gate events, day resets, absence closing, and corrections. Daily views and range exports share the same batch reader and attendance-row calculation.
- `backend/app/services/biometrics.py` — image decoding, face/eye checks, encrypted sample storage, LBPH training/model integrity, multi-face prediction, liveness state, non-image review entries, and audited biometric cleanup.
- `backend/app/services/sms.py` — message templates, number normalization, private-LAN validation, diagnostics, idempotent outbox creation, Android dispatch/delivery reconciliation/cancellation, masking, rate limits, and scheduled retries.
- `backend/app/services/sf2.py` — validates the official template, generates all-school or adviser-section logs, fills attendance and transferee remarks, separates male/female blocks, alphabetizes names, and writes tardy marks.
- `backend/app/services/roster.py` — validates approved XLSX rosters including enrollment/transfer fields, normalizes records, imports people, hashes the source file, and records import audits.
- `backend/app/services/backup.py` — backs up SQLite, MySQL, or PostgreSQL with matching secrets/artifacts, encrypts and hashes the package, records inventory/model/key metadata, and verifies/stages two-phase restoration. PostgreSQL recovery is documented in `docs/POSTGRES_RECOVERY.md`.
- `backend/app/services/audit.py` — creates redacted before/after snapshots and unified attributable system-audit entries.
- `backend/app/services/grading.py` — class-record persistence, ownership, score validation, workflow, adjustments, and calculated results. `grading_engine.py` contains the policy-driven calculations.
- `backend/app/services/reports.py` — generates printable/XLSX attendance and grade summaries and registers immutable report metadata/hashes.
- `backend/app/services/export_files.py` — allocates separate output folders for concurrent report requests while preserving download filenames.
- `backend/app/services/gate_exports.py` — coalesces daily-log updates and retains failed jobs for retry while the backend process runs.
- `backend/app/services/retention.py` — previews approved retention eligibility, applies legal holds, performs bounded operational cleanup, and issues disposal certificates.
- `backend/app/services/disposal.py` — performs authorized linked-record deletion while preserving a non-identifying disposal audit.
- `backend/app/services/scheduler.py` — runs attendance closing, pending export retries, SMS dispatch, and due encrypted backups every 30 seconds. Job failures are logged independently so one failure does not stop the remaining jobs.
- `backend/app/services/settings_store.py` — stores JSON configuration and Fernet-encrypted secrets in the system-settings table.

## Tests, scripts, and project records

- `backend/tests/test_smoke.py` — isolated integration tests covering biometrics, multi-face recognition, re-entry, reporting scope, transfers, clean-slate reset, legacy migration repair, the capcom6 Android gateway request contract and reachability check, grades, roster/SF2, disposal, and backup/restore.
- `backend/tests/test_attendance_sync.py` — attendance-row parity, teacher scope, and batch-query limits for daily and range reporting.
- `backend/tests/test_reporting_reliability.py` — concurrent exports, stable download snapshots, failure logging, and background retry behavior.
- `backend/tests/test_grading_regressions.py` and `test_grading_api.py` — grading policy, incomplete-score, export, teacher-editing, and admin read-only regressions.
- `backend/tests/test_audit_repairs.py` — legacy class access, assignment persistence, safe startup, disposal rollback, and maintenance-script safety.
- `backend/tests/test_postgres_backup.py` — encrypted backup/recovery against a disposable local PostgreSQL cluster.
- `backend/tools/migrate_sqlite_to_mysql.py` — copies an upgraded SQLite data set into an empty MySQL schema and verifies every application-table row count before cutover.
- `backend/tools/apply_mysql_restore.py` — applies a verified staged MySQL dump while the API is offline, after first creating an encrypted safety backup, then swaps matching local secrets/artifacts.
- `backend/tools/apply_postgres_restore.py` and `scripts/apply-postgres-restore.ps1` — controlled PostgreSQL recovery with hash verification, a safety backup, one database transaction, and preserved prior local files.
- `scripts/setup.ps1` — creates the Python environment, installs backend/frontend dependencies, prepares `.env`, and optionally installs the approved SF2 template.
- `scripts/update.ps1` — refuses a dirty source tree, fast-forwards from `origin/main`, and reruns the idempotent dependency setup.
- `scripts/start.ps1` — preflights the required ports, launches FastAPI and Vite in hidden processes, waits for both HTTP endpoints to become ready, cleans up failed startup processes, and writes output to `logs/`.
- `scripts/migrate-sqlite-to-mysql.ps1` — securely prompts for the restricted MySQL connection URL and runs the verified copy utility.
- `scripts/configure-eduscan-mysql.ps1` — securely provisions the restricted local MySQL account, creates an encrypted pre-migration backup, verifies the SQLite-to-MySQL copy, and updates the ignored backend environment file only after success.
- `scripts/apply-mysql-restore.ps1` — prompts for recovery confirmation, a fresh safety-backup passphrase, and MySQL administrator credentials before invoking the controlled offline restore.
- `scripts/test-disaster-recovery.ps1` — runs the isolated disaster-recovery verification procedure.
- `docs/DISASTER_RECOVERY.md` — operational backup, restore, validation, and incident-recovery runbook.
- `docs/INSTALLATION.md` — clean clone, dependency installation, MySQL selection, updates, offline preparation, and troubleshooting.
- `docs/MYSQL_MIGRATION.md` — MySQL account creation, verified copy, cutover, rollback, and post-migration backup procedure.
- `docs/ANDROID_SMS_GATEWAY.md` — physical Android Local Server setup, offline-network operation, connection tests, and troubleshooting.
- `docs/RAD_PROGRESS_REPORT.txt` — chronological capstone progress organized by RAD methodology phases.
- `docs/PROJECT_STRUCTURE.md` — this architecture and file-purpose guide.

## Runtime data not committed to Git

The following paths are created locally and should not be published:

- `backend/.env` — local secrets and deployment settings.
- `backend/.venv/` — installed Python environment.
- `backend/data/eduscan.db` and its WAL/SHM files — live SQLite records.
- `backend/data/.encryption_key` — key required to decrypt biometric samples and models.
- `backend/data/.app_secret` — generated per-installation token-signing secret when an environment secret is not supplied.
- `backend/data/biometrics/` — encrypted face samples.
- `backend/data/models/` — encrypted LBPH model versions.
- `backend/data/exports/` — generated temporary logs and SF2 workbooks.
- `backend/data/backups/` — encrypted backup packages.
- `backend/data/recovery_checks/` — private recovery evidence and protected recovery-test passphrases; excluded from Git.
- `logs/` — local API and frontend process output.
- `node_modules/` and `dist/` — installed frontend dependencies and generated build output.

The approved workbook at `backend/data/templates/School Form 2 (SF2) Daily Attendance Report of Learners.xlsx` is intentionally retained because the report generator requires its official structure.

## Scanner camera update

The current gate-station interface provides:

- a larger 16:9 camera workspace with a responsive minimum height;
- more horizontal space for recognizing several people in one frame;
- a whole-frame multi-face positioning guide instead of a single-face oval;
- a full-screen button inside the camera and an additional expand control below it;
- a browser-support warning if the Fullscreen API is unavailable; and
- a narrower recent-events panel so the camera remains the primary gate-station surface.

These presentation changes are located only in `src/pages/Scanner/Scanner.jsx` and `src/styles/index.css`. Recognition processing continues to use the existing local multi-face LBPH endpoint.
