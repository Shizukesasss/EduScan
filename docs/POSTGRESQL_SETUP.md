# EduScan — Centralized PostgreSQL Setup Guide

This guide explains how to run EduScan with a **shared, centralized PostgreSQL
database** so that all developers and deployed instances work on the same data.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                   EduScan Deployment Modes                  │
├─────────────────┬───────────────────────────────────────────┤
│ Mode            │ When to use                               │
├─────────────────┼───────────────────────────────────────────┤
│ SQLite (local)  │ • Individual developer working offline    │
│                 │ • Quick demo on a single laptop           │
│                 │ • No network required                     │
├─────────────────┼───────────────────────────────────────────┤
│ PostgreSQL      │ • Team of developers sharing one DB       │
│ (centralized)   │ • School production deployment            │
│                 │ • Multiple browser clients on same LAN    │
│                 │ • Admin + Teacher + Scanner all connected  │
└─────────────────┴───────────────────────────────────────────┘
```

### What happens to a developer's local data?

When someone clones the repo and runs `scripts\setup.ps1`:

- If `backend\.env` has `DATABASE_URL=sqlite:///./data/eduscan.db` (the default),
  `setup.ps1` creates a **local-only** `backend\data\eduscan.db` via the seed
  script. This file is **gitignored** — it never appears in `git status`, never
  causes merge conflicts, and is invisible to other developers.

- If `backend\.env` has a PostgreSQL `DATABASE_URL`, the seed step is skipped.
  Start PostgreSQL deployments after running the maintenance migration. The API
  verifies the migration ledger and seeds reference data using its runtime login.

---

## Part 1 — Setting up the Central PostgreSQL Server

### Option A — Local school server (Windows)

1. Download and install **PostgreSQL 16** from https://www.postgresql.org/download/windows/

2. Connect as the database administrator with psql and run:

```sql
CREATE ROLE eduscan_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE eduscan_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
\password eduscan_owner
\password eduscan_app
CREATE DATABASE eduscan OWNER eduscan_owner;
\c eduscan
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO eduscan_owner;
GRANT CONNECT ON DATABASE eduscan TO eduscan_app;
```

3. Note the server IP address (e.g. `192.168.1.10`).

4. Edit `postgresql.conf` to listen on the LAN:
   ```
   listen_addresses = 'localhost,192.168.1.10'
   ```

5. Edit `pg_hba.conf` to allow LAN clients:
   ```
   # Allow EduScan app from the school LAN (adjust subnet as needed)
   host    eduscan    eduscan_app    192.168.1.0/24    scram-sha-256
   # Allow the separate maintenance login only from the administration host.
   host    eduscan    eduscan_owner  192.168.1.10/32   scram-sha-256
   ```

6. Restart the PostgreSQL service.

---

### Option B — Cloud/hosted PostgreSQL (Supabase, Railway, Neon, etc.)

Most hosted providers give you a connection string in the format:
```
postgresql+psycopg2://user:password@host:5432/dbname
```

For an existing database, use the role that owns the EduScan relations as the
maintenance login. Create a separate `eduscan_app` login with the restricted role
attributes shown above. Use its connection string as `DATABASE_URL` in
`backend\.env`. Use the same host, port and database in both URLs. For Supabase's
session pooler, the runtime username is `eduscan_app.<project-ref>`.

### Supabase Data API

EduScan's browser calls FastAPI. For a dedicated Supabase project, open
**Integrations > Data API** and turn off **Enable Data API** and **Automatically
expose new tables**. For a shared project that needs the Data API, keep EduScan's
`public` schema out of its exposed schemas and expose a separate schema for the
other application's API. Review existing views and functions in exposed schemas
for access to EduScan. [Supabase Data API controls](https://supabase.com/docs/guides/api/securing-your-api)

Run the following from the project root to audit effective grants and the runtime
role. The audit reads PostgreSQL catalogs. Review the Data API integration
settings in the dashboard to verify the HTTP exposure separately.

```powershell
& "backend\.venv\Scripts\python.exe" backend\tools\postgres_access.py audit
```

Before switching an existing owner connection to the runtime login, the owner
can remove existing direct Data API grants on EduScan tables and their sequences.

```powershell
& "backend\.venv\Scripts\python.exe" backend\tools\postgres_access.py revoke-data-api --confirm "REVOKE EDUSCAN DATA API GRANTS"
```

The command checks effective privileges, including column-level grants. It rolls
back when inherited Data API grants remain. Keep the former owner password in
the operator's secrets store before replacing the URL in `backend\.env`.

---

## Part 2 — Configuring EduScan to use PostgreSQL

On **every machine** (developer laptop or deployment server) that should use
the central database:

1. Open `backend\.env` (create from `.env.example` if missing):

```ini
# Change this line:
DATABASE_URL=sqlite:///./data/eduscan.db

# To this (use your real server IP and password):
DATABASE_URL=postgresql+psycopg2://eduscan_app:CHANGE_THIS_PASSWORD@192.168.1.10:5432/eduscan
```

2. Also set a shared `EDUSCAN_SECRET_KEY` so JWT tokens work across restarts:

```ini
EDUSCAN_SECRET_KEY=generate-a-long-random-string-here-at-least-48-chars
```

   Generate one with:
   ```powershell
   & "backend\.venv\Scripts\python.exe" -c "import secrets; print(secrets.token_urlsafe(64))"
   ```

3. If biometrics are enabled, set a shared `EDUSCAN_ENCRYPTION_KEY`:

```ini
EDUSCAN_ENCRYPTION_KEY=your-fernet-key-here
```

   Generate one with:
   ```powershell
   & "backend\.venv\Scripts\python.exe" -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

4. Set `ALLOWED_ORIGINS` to the origin used by the browser. The local launcher uses:

```ini
ALLOWED_ORIGINS=http://127.0.0.1:5175,http://localhost:5175
```

5. Run the maintenance migration before starting the app or after updating to a
   version with schema changes. The command prompts for the maintenance URL
   with hidden input, or reads `EDUSCAN_MIGRATION_DATABASE_URL` from the maintenance
   process environment. Keep that credential out of the app service and its
   `.env`.

   ```powershell
   & "backend\.venv\Scripts\python.exe" backend\tools\postgres_access.py migrate
   & "backend\.venv\Scripts\python.exe" backend\tools\postgres_access.py audit
   & ".\scripts\start.ps1"
   ```

   The migration runs with the owner login. It grants the runtime login
   application table reads and writes, sequence access for inserts and backups,
   and read access to the migration ledger. It rejects a runtime login that
   owns app objects, has elevated roles, or can create permanent objects in the
   database or `public` schema.

   On a fresh server database, create a named administrator from the EduScan server console. Run the following from the `backend` directory and enter a unique temporary password at the prompt.

   ```powershell
   & ".venv\Scripts\python.exe" tools\create_admin.py --username school.admin --full-name "School Administrator"
   ```

   Server databases default to disabling interactive API docs and demo-account seeding. For a shared SQLite deployment also set `EDUSCAN_SEED_DEMO_ACCOUNTS=false` and `EDUSCAN_ENABLE_API_DOCS=false`. Review previously created demo accounts before opening access. For institutional Google sign-in, reserve the named administrator's verified DepEd address using the [Google login setup](DEPED_GOOGLE_LOGIN.md).

The supplied launcher binds the website and API to `127.0.0.1`. The origin list above is for a local browser; adding a LAN origin alone does not expose the servers on the network. Deploy a shared site and API over HTTPS with an appropriate network and camera-permission configuration if other devices must access them. A shared PostgreSQL database contains enrollment metadata, but the encrypted face samples, trained model, and matching key also need an authorized encrypted backup/restore or new consent-based enrollment. Never place the connection string or biometric artifacts in Git.

---

## Part 3 — Migrating existing SQLite data to PostgreSQL

If you already have data in `backend\data\eduscan.db` and want to move it to
the new central PostgreSQL server:

```powershell
# From the project root:
& "backend\.venv\Scripts\python.exe" backend\tools\migrate_sqlite_to_postgresql.py `
    --confirm "MIGRATE TO POSTGRESQL"
```

The migration tool:
- Prompts for the PostgreSQL maintenance URL with hidden input
- **Never modifies** the SQLite source
- Aborts if the PostgreSQL target already has data (add `--force-wipe` to override)
- Verifies row counts table-by-table after copying
- Resets PostgreSQL sequences so new records don't conflict

After copying, set the runtime `DATABASE_URL` in `backend\.env` and run
`postgres_access.py migrate` to apply the runtime grants before starting the API.

---

## Part 4 — Developer Workflow (SQLite locally, PostgreSQL centrally)

```
Developer A (SQLite, offline dev)          Central PostgreSQL Server
─────────────────────────────────          ──────────────────────────
git clone ...                              (always running)
scripts\setup.ps1                          
  → seed_demo.py creates local DB          
  → backend\data\eduscan.db (gitignored)   
                                           
[code changes to src/ or backend/]         
git add, git commit, git push              
                                           
                                           Developer B (PostgreSQL, live)
                                           ──────────────────────────────
                                           git pull (gets code changes)
                                           scripts\start.ps1
                                             → connects to central DB
                                             → verifies the migration ledger
                                             → all users see changes
```

### Key rule: **only source code is committed, never the database file.**

| Committed to git            | NOT committed to git               |
|-----------------------------|------------------------------------|
| `backend/app/*.py`          | `backend/data/eduscan.db`          |
| `backend/seed_demo.py`      | `backend/data/biometrics/`         |
| `backend/.env.example`      | `backend/.env`                     |
| `backend/templates/*.xlsx`  | `backend/data/exports/`            |
| `src/**/*.jsx`              | `backend/data/.app_secret`         |
| `scripts/*.ps1`             | `backend/data/.encryption_key`     |

---

## Part 5 — Required Python package for PostgreSQL

The default `requirements.txt` includes `psycopg2-binary` which is the
PostgreSQL driver. No extra installation is needed — `setup.ps1` installs it.

To verify:
```powershell
& "backend\.venv\Scripts\python.exe" -c "import psycopg2; print('psycopg2 OK')"
```

---

## Quick Reference

| Task                                | Command / File                                  |
|-------------------------------------|-------------------------------------------------|
| Use SQLite (local dev)              | Keep default `DATABASE_URL` in `backend\.env`   |
| Use PostgreSQL (shared)             | Set `DATABASE_URL=postgresql+psycopg2://...`    |
| Seed fresh local demo DB            | `backend\.venv\Scripts\python.exe backend\seed_demo.py` |
| Migrate SQLite → PostgreSQL         | `python backend\tools\migrate_sqlite_to_postgresql.py --confirm "MIGRATE TO POSTGRESQL"` |
| Reset & reseed local DB             | Delete `backend\data\eduscan.db`, run `seed_demo.py` |
| Check current DB backend            | Look at `DATABASE_URL` in `backend\.env`        |
