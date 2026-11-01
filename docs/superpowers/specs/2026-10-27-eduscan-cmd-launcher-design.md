# EduScan CMD Start/Restart Launcher Design

Date: 2026-10-27

## Intent

Give the user a Command Prompt entry point to start or restart the full EduScan website and API.

## Goals

- Add `scripts\eduscan.cmd` with `start` and `restart` actions; default to `start` when no action is given.
- Reuse `scripts\start.ps1` for API/Vite startup, health checks, and existing logs.
- On a remote PostgreSQL/MySQL configuration, show that API startup applies recorded schema migrations and seeds users/reference data; require explicit confirmation before starting.
- For `restart`, ask before stopping anything. If declined, leave the current services running.
- Stop only listeners on EduScan's ports whose process path/command line proves they belong to this checkout. Refuse to kill unrelated listeners.
- Preserve `backend\.env` and never print the connection string or password.

## Non-goals

- Change database migrations, seed logic, or website behavior.
- Add a frontend-only mode, deployment workflow, or a general process manager.
- Automatically connect to Supabase during script installation.

## Approaches

- **Chosen: CMD wrapper with a PowerShell helper.** The helper reuses the existing startup script and handles the remote-database prompt and safe restart process detection. This avoids duplicating service launch logic and avoids killing unrelated applications.
- Pure batch implementation. Rejected because the existing startup, health-check, and process-ownership logic is PowerShell-based; duplicating it in batch would be less reliable.
- Frontend-only wrapper. Rejected because the user chose the full stack and API-backed features require the backend.

## Interface and behavior

Run `scripts\eduscan.cmd start`, `scripts\eduscan.cmd restart`, or simply `scripts\eduscan.cmd` from Command Prompt. The helper prompts before launching the API whenever `backend\.env` points to a remote database. A declined prompt starts nothing; for restart, it also leaves running services untouched. A successful start uses the existing API health endpoint and web server checks, then reports the local URLs and log directory.

## Calls left to the implementer

Use a small `scripts\manage-eduscan.ps1` helper behind the CMD wrapper, detect process ownership using listener PID plus executable path/command line, and surface startup errors from the existing log files.