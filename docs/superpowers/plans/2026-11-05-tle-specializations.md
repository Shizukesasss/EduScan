# TLE Specializations Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Support multiple typed TLE specializations through the existing teacher, gradebook, and Excel workflows.

**Architecture:** Store each specialization as a normal subject named `TLE - <specialization>` with an automatically generated unique code. Share recognition helpers within each application layer; keep existing TLE policies and workbook routing.

**Tech Stack:** React, JavaScript, FastAPI, SQLAlchemy, Python unittest, Node test runner.

**Spec:** `docs/superpowers/specs/2026-11-05-tle-specializations-design.md`

## Global Constraints

- No new dependencies or specialization dropdown.
- Keep existing subject identities, permissions, teacher eligibility, grading policies, and Excel templates.
- Preserve unrelated local changes; implement in the existing feature branch as requested.

## Review Focus

- Case and whitespace differences must not create duplicate specializations.
- Long or non-ASCII specialization names must still get unique bounded codes.
- Editing must retain existing subject IDs, assignments, and gradebooks.
- Switching subjects or categories must not leave a hidden specialization attached.
- Single-period and all-period workbooks must retain specialization labels and separate scores.

### Task 1: Subject creation and workbook recognition

**Files:** `backend/app/services/tle_subjects.py`, `backend/app/main.py`, `backend/app/services/class_record_export.py`, `backend/tests/test_tle_specializations.py`.

**Interfaces:** `tle_specialization(name: str) -> str | None` returns an empty string for plain TLE and None for other subjects. Specialized names use `TLE - <typed text>`.

- [x] Add failing tests for creating multiple specializations, duplicate normalization, code limits/collisions, and editing identity preservation.
- [x] Run `backend/.venv/Scripts/python.exe -m unittest tests.test_tle_specializations` from backend and confirm missing support failures.
- [x] Implement canonical names and generated unique codes in subject saving. Route recognized specialized names to the existing TLE workbook.
- [x] Add integration coverage for independent teacher assignments, gradebook permissions/policy, and actual exports in both scopes; run until passing.

### Task 2: Typed specialization form

**Files:** `src/services/tleSubjects.js`, `src/services/tleSubjects.test.js`, `src/pages/Administration/Administration.jsx`.

**Interfaces:** `tleSpecialization(subject)` returns typed text, empty string for plain TLE, or null for non-TLE subjects. `withTleSpecialization(subject, value)` updates the canonical name while retaining identity.

- [x] Write and run failing helper tests for edit recognition, typing, clearing, and category/elective isolation.
- [x] Implement helpers; integrate catalog recognition, repeatable TLE selection, free-text field, and automatic codes for new selections.
- [x] Run Node tests, lint, and the production build.

### Task 3: Verification and review

- [x] Run relevant existing backend suites and all discoverable project tests; report any environment blockers or failures explicitly.
- [x] Review only task changes against the approved design, including snapshots in generated Excel files.
- [x] Document results. Leave changes uncommitted alongside the user's existing local work.

## Execution Notes

The user approved the design and explicitly requested implementation now; proceed inline without another approval gate. Existing work is uncommitted on `codex/eduscan-interface-consistency`, so avoid moving it to a separate checkout or committing unrelated changes. Plain TLE currently uses the core workbook policy; specializations must match that behavior rather than changing the existing grading weights.

## Verification Results

- Task 1 complete: nine new backend tests pass. Coverage includes real saved scores and generated XLSX files in both export scopes, separate teacher access, editing identity, converting plain TLE, normalized duplicates, unique bounded codes, and restoration of a deleted Unicode specialization.
- Task 2 complete: four new JavaScript tests pass. `npm run verify` passes (lint and production build); existing warnings concern `tmp/ui-review/cdp.mjs` and bundle size.
- Final focused run: `python -m unittest tests.test_tle_specializations tests.test_jhs_template_routing -v` passes all 14 tests.
- Independent reviewer found spaces-only input and Unicode case duplicates. Both were reproduced with failing tests and fixed. Deleted-item restoration uses the original code to retain identity despite capitalization differences.
- Broad frontend run: 99 of 100 tests pass. `tests/attendance-route.test.js`, “attendance reads the administrator role after login, not at app startup,” also fails when rerun alone: it expects “Recognition review queue” but renders “Loading operational records…”. This task does not modify the attendance page or its test.
- Broad backend run collects 607 tests. Initial collection was blocked by sandbox temporary-directory permissions. Redirecting temporary files to the workspace resolves collection, but the first academic-deletion test stalls in Windows asyncio socket-pair creation inside Starlette TestClient. A 45-second bounded run captures the stack and exits; the full backend suite is not verified green. Diagnostic: `tmp/tle-full-backend-bounded.log`. The larger selected suites that encounter TestClient were interrupted rather than left running.
- Python syntax checks and `git diff --check` pass for the changed production files. No database migration or dependency installation is required.

## Rulings

- Implement inline in the current feature branch and leave changes uncommitted, preserving the user's preexisting work. No merge or publish operation is part of this request.
- Preserve plain TLE's existing 20/50/30 core policy and workbook. Changing all TLE grading weights would exceed the approved scope.
