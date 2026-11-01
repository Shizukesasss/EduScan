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

- [ ] Copy its tracked diff and selected new source files into the isolated worktree.
- [ ] Confirm no secrets or generated reports were copied.
- [ ] Run baseline build and available tests; record any pre-existing failures.
- [ ] Commit the preserved local source state on the integration branch.

## Task 2: Merge upstream SHS commit

- [ ] Fetch `origin/main` and verify it contains commit `5dc93e29`.
- [ ] Merge it into the integration branch; inspect and resolve every conflict, particularly `main.py`, `schemas.py`, `start.ps1`, Administration, and styles.
- [ ] Add regression tests before any new conflict-resolution behavior.
- [ ] Check migration order and schema compatibility on a disposable database.

## Task 3: Verify end-to-end integration

- [ ] Run SHS and existing backend grading/reporting/attendance tests.
- [ ] Run frontend tests, lint, and build.
- [ ] Generate/check SHS class-record exports and existing SF2 output using disposable data.
- [ ] Review the complete diff and report any limits of verification.
