# EduScan CMD Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a Command Prompt script that starts or safely restarts the full EduScan API and website.

**Architecture:** Add a small `.cmd` entry point that delegates to a PowerShell helper. The helper prompts before any remote database startup, safely stops only processes belonging to this checkout for `restart`, and reuses the existing `scripts/start.ps1` for service startup and health checks.

**Tech Stack:** Windows CMD, Windows PowerShell, existing FastAPI/Vite startup scripts.

**Spec:** `docs/superpowers/specs/2026-10-27-eduscan-cmd-launcher-design.md`

## Global Constraints

- Support `start` (default) and `restart` from Command Prompt.
- Before remote database startup, explain that API startup applies migrations and seeds users/reference data; require explicit confirmation.
- On a declined restart prompt, leave running services untouched.
- Stop only listeners on ports 8000 and 5175 proven to belong to this checkout; refuse unknown processes.
- Never print the connection string or password; do not alter `.env`, migration, or seed behavior.
- Reuse `scripts/start.ps1` for API/web readiness checks and logs.

## Review Focus

- SQLite, PostgreSQL, MySQL, and an unfamiliar `DATABASE_URL` scheme select the appropriate prompt behavior.
- Declining confirmation causes no process stop or startup.
- A port occupied by another application is reported and left running.
- Missing process metadata fails safely instead of killing by port alone.
- Startup failure is surfaced with the existing log locations and does not leave half-started services.

---

### Task 1: Add the CMD entry point and lifecycle helper

**Files:**
- Create: `scripts/eduscan.cmd`
- Create: `scripts/manage-eduscan.ps1`

**Interfaces:**
- `eduscan.cmd [start|restart]` forwards the requested action and preserves the helper's exit code.
- `manage-eduscan.ps1 -Action start|restart` implements confirmation, safe process handling, and delegates startup to `scripts/start.ps1`.

- [x] Create the CMD wrapper with a default `start`, explicit `restart`, and usage/error handling for unsupported actions.
- [x] Implement remote-database detection without echoing `.env` values; treat any non-SQLite URL as remote and require a Y/N confirmation before starting.
- [x] Implement restart by collecting owners for ports 8000 and 5175, verifying every owner against this checkout's Python executable or Vite command line, stopping only verified owners, and waiting for both ports to become free.
- [x] Call the existing `start.ps1`, return its result, and point failures to `logs\api.stderr.log` or `logs\web.stderr.log`.
- [x] Parse the PowerShell helper with the PowerShell AST parser and invoke the CMD wrapper with an invalid action to inspect its safe usage/error path; do not start the API or connect to Supabase during implementation verification.