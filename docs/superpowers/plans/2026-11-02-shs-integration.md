# SHS Grading Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Combine upstream SHS grading changes with this checkout's current features without changing the shared database.

**Architecture:** Preserve the current tracked edits in an isolated branch, merge upstream's single commit, and resolve overlapping files at their behavior boundaries. Retain upstream's migrations and templates as a set. Validate against an isolated SQLite database and test API/UI workflows.

**Tech Stack:** React/Vite, FastAPI/SQLAlchemy, PostgreSQL production, SQLite test fixtures, XLSX templates.

**Spec:** `docs/superpowers/specs/2026-11-02-shs-integration.md`

## Global Constraints

- Do not copy `backend/.env`, biometric files, keys, logs, or generated reports into Git.
- Do not run startup migrations against shared Supabase during integration testing.
- Preserve locally changed attendance, scanner, SF2, Administration, and launcher behavior.

## Review Focus

- SHS track and elective cluster validation with legacy sections.
- Subject-name uniqueness migration with duplicate names.
- Grade 11/12 exports and official template structure.
- Administration permissions after upstream UI changes.
- Existing attendance, scanner, SF2, and launcher behavior after merge.

## Task 1: Preserve the local checkout

- [x] Copy its tracked diff and selected new source files into the isolated worktree.
- [x] Confirm no secrets or generated reports were copied.
- [x] Run baseline build and available tests; record any pre-existing failures.
- [x] Commit the preserved local source state on the integration branch.

## Task 2: Merge upstream SHS commit

- [x] Fetch `origin/main` and verify it contains commit `5dc93e29`.
- [x] Merge it into the integration branch; inspect and resolve every conflict, particularly `main.py`, `schemas.py`, `start.ps1`, Administration, and styles.
- [x] Add regression tests before any new conflict-resolution behavior. No production behavior was newly implemented in conflict resolution; the local launcher was preserved and the CSS grid rules were combined.
- [x] Check migration order and schema compatibility on a disposable database.

## Task 3: Verify end-to-end integration

- [x] Run SHS and existing backend grading/reporting/attendance tests.
- [x] Run frontend tests, lint, and build.
- [x] Generate/check SHS class-record exports and existing SF2 output using disposable data.
- [x] Review the complete diff and report any limits of verification.

## Verification record

- The original checkout's frontend baseline passed 57 tests and built; its backend suite already had failures before merging.
- After integration, `npm ci`, 66 Node tests, lint, and build passed. Lint retains the existing Annex G memoization warning.
- The four new SHS backend test files passed: 18 tests. The migration smoke test now checks all registered versions and new columns; the isolated smoke module passed 11 tests. The SF2 reliability module passed 9 tests alone.
- Disposable Grade 11 and Grade 12 records generated readable seven-sheet official SHS ECR workbooks. No shared data was written.
- The full backend suite is not green: 465 passed, 39 failed, 17 errors, and 1 skipped. The upstream commit alone reproduces all 14 failures in `test_grading_regressions.py`; the original checkout also has 7 failures in that file. Some cross-module errors arise from test process state. Do not use this branch for a live deployment until the failing workflows and tests are reconciled.
- Read-only shared database preflight found the SHS schema migrations already applied and no duplicate subject names. Three active SHS sections have no track and one has the old `ABM` track. An administrator must classify these before the new SHS export can serve them.
- The upstream `Run EduScan.bat` was excluded because it calls an unsupported `-OpenBrowser` switch in this checkout and duplicates `scripts/eduscan.cmd`. The dependency lockfile was repaired so `npm ci` works.
