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
  The app connects to the central server on start and applies any missing schema
  migrations automatically. All changes go directly to the shared database.

---

## Part 1 — Setting up the Central PostgreSQL Server

### Option A — Local school server (Windows)

1. Download and install **PostgreSQL 16** from https://www.postgresql.org/download/windows/

2. Open pgAdmin or psql and run:

```sql
-- Create the dedicated database and user
CREATE DATABASE eduscan;
CREATE USER eduscan_app WITH PASSWORD 'CHANGE_THIS_PASSWORD';
GRANT ALL PRIVILEGES ON DATABASE eduscan TO eduscan_app;

-- Required for SQLAlchemy schema creation
\c eduscan
GRANT ALL ON SCHEMA public TO eduscan_app;
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
   ```

6. Restart the PostgreSQL service.

---

### Option B — Cloud/hosted PostgreSQL (Supabase, Railway, Neon, etc.)

Most hosted providers give you a connection string in the format:
```
postgresql+psycopg2://user:password@host:5432/dbname
```

Copy that string and use it as `DATABASE_URL` in `backend\.env`.

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

4. Add the server IP to `ALLOWED_ORIGINS` so browser clients on the LAN work:

```ini
ALLOWED_ORIGINS=http://127.0.0.1:5173,http://127.0.0.1:5174,http://192.168.1.10:5174
```

5. Run `scripts\start.ps1`. EduScan will automatically create all tables in
   PostgreSQL on the first start (schema migrations run at startup).

---

## Part 3 — Migrating existing SQLite data to PostgreSQL

If you already have data in `backend\data\eduscan.db` and want to move it to
the new central PostgreSQL server:

```powershell
# From the project root:
& "backend\.venv\Scripts\python.exe" backend\tools\migrate_sqlite_to_postgresql.py `
    --pg-url "postgresql+psycopg2://eduscan_app:CHANGE_THIS_PASSWORD@192.168.1.10:5432/eduscan" `
    --confirm "MIGRATE TO POSTGRESQL"
```

The migration tool:
- **Never modifies** the SQLite source
- Aborts if the PostgreSQL target already has data (add `--force-wipe` to override)
- Verifies row counts table-by-table after copying
- Resets PostgreSQL sequences so new records don't conflict

After migration, update `backend\.env` with the PostgreSQL `DATABASE_URL`.

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
                                             → migrations apply automatically
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
| Migrate SQLite → PostgreSQL         | `python backend\tools\migrate_sqlite_to_postgresql.py --pg-url ... --confirm "MIGRATE TO POSTGRESQL"` |
| Reset & reseed local DB             | Delete `backend\data\eduscan.db`, run `seed_demo.py` |
| Check current DB backend            | Look at `DATABASE_URL` in `backend\.env`        |