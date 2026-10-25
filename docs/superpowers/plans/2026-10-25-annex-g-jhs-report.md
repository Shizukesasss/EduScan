# Annex G JHS electronic report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare, review, and release an Annex G learner report for Grades 7–10 using verified year-specific enrollment, finalized term grades, reconciled attendance, and administrator-verified DOBs.

**Architecture:** Add separate school-year learner placements and report comments; do not mutate `Person.grade/section` or gradebook scores. Build report calculations from the existing grading service with an optional historical learner roster, reuse attendance status helpers and `GeneratedReport` audit/history, and render an immutable print-ready HTML report because the backend has no PDF engine installed.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite/PostgreSQL migrations, openpyxl, existing React/Vite API and print helpers, unittest/pytest.

**Spec:** `docs/superpowers/specs/2026-10-25-annex-g-jhs-report-design.md`

## Global Constraints

- Grades 7–10 only; keep Grades 11–12 and SHS behavior unchanged.
- Preserve all existing grade scores, gradebook finalization states, and attendance events.
- Only finalized/locked gradebooks may supply term grades.
- DOB is sensitive; only administrators can import or view raw DOB. Teachers and Records Officers receive calculated age only.
- Match uploaded DOBs to existing learners by exact LRN; fill blank DOBs only; never guess or overwrite.
- Match enrollment placement imports to existing learners by exact LRN; retain source hash, approval reference, and importing administrator.
- Age reference is the first Friday in June of the selected school year; keep this date visible in the report and retain the open local-policy confirmation.
- JHS elective subjects assigned to the section appear as dynamic learning-area rows and are included once in General Average.
- No new runtime dependency. Store a versioned HTML snapshot for browser print/download; report files must be immutable after release.

## Review Focus

- A learner transferred to another current section still gets grades from the year-specific report roster and never disappears from their historical report.
- A missing DOB, term gradebook/grade, or unresolved instructional-day attendance blocks release and names the learner/source.
- MAPEH shows Music and Arts and PE and Health as subrows and counts its combined Term/Final Grade once in General Average.
- Advisers can edit only comments for their assigned section and school year; only Records Officers release reports.
- Repeated release keeps the prior snapshot available and does not mutate source grades or attendance.

---

### Task 1: Verified historical enrollment and DOB intake

**Files:** `backend/app/models.py`, `backend/app/migrations.py`, `backend/app/services/annex_g.py`, `backend/app/main.py`, `backend/tests/test_annex_g.py`

**Interfaces:** `import_annex_g_enrollments(db, data, filename, approved_reference, actor, dry_run) -> dict`; `backfill_annex_g_dobs(...) -> dict`; `LearnerEnrollment` stores one effective-dated section placement, verified import reference, and source hash.

- [x] Write tests for exact-LRN placement import, year/section validation, audit metadata, DOB blank-only update, and rejection of weak/name-only matches.
- [x] Run the failing test first; the initial failure was the expected missing service module.
- [x] Add the enrollment and DOB-import audit schema in migration `0026_annex_g_enrollment_and_comments`; do not backfill historical placement from mutable person fields.
- [x] Implement the two admin-only preview/apply XLSX imports; enrollment import requires school year, LRN, grade, section, start date, and optional end date; DOB import requires LRN and DOB.
- [x] Re-run focused tests and verify imported data changes only the intended columns/rows.

### Task 2: Annex G data assembly and report rendering

**Files:** `backend/app/services/grading.py`, `backend/app/services/annex_g.py`, `backend/tests/test_annex_g.py`

**Interfaces:** `build_annex_g_section(db, school_year_id, grade, section, term_order) -> dict`; `render_annex_g_html(report) -> str`. `get_gradebook_full(..., roster_person_ids=None)` uses the supplied roster only when requested; all existing callers keep current behavior.

- [ ] Add tests for first-Friday-of-June age, direct/adjusted reporting modes, missing and unfinalized subject books, year-specific roster, MAPEH once in General Average, electives, term 1/2 blanks, and year-end Final Grade/General Average.
- [ ] Run the focused tests and confirm they fail for the report behavior, not fixture/setup errors.
- [ ] Reuse `get_gradebook_full` and `round_value`; read only finalized/locked books and include historical report learners by explicit person IDs.
- [ ] Reuse attendance day classification; derive monthly days/presence/absence only from saved attendance and enrollment dates. Surface unresolved past instructional days as blockers.
- [ ] Render Annex G labels, grade descriptors/remarks, monthly attendance, term comments, signature spaces, and transfer fields into print-oriented HTML; leave future terms/annual values blank until available.
- [ ] Re-run focused tests and inspect a synthetic HTML snapshot.

### Task 3: Adviser draft and Records Officer release workflow

**Files:** `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/main.py`, `backend/app/services/annex_g.py`, `backend/tests/test_annex_g.py`

**Interfaces:** `GET /api/annex-g/options`; `GET /api/annex-g/section`; `PUT /api/annex-g/comments`; `GET /api/annex-g/preview/{enrollment_id}`; `POST /api/annex-g/release/{enrollment_id}`. Comments are stored by learner, school year, and term; released files are registered with `GeneratedReport` and a checksum.

- [ ] Test role restrictions, adviser/year/section matching, release blockers, immutable release history, and unchanged grade/attendance counts.
- [ ] Run targeted tests and confirm expected failures before implementation.
- [ ] Add per-learner term comments and API checks; teachers may save only their assigned adviser section, while Records Officers alone can release.
- [ ] Generate and register an immutable print-ready HTML report only when all release checks pass; audit the release.
- [ ] Run focused API tests, including unauthorized teacher, unrelated section, and records-officer release.

### Task 4: Reports workspace UI

**Files:** `src/components/Reports/AnnexGWorkspace.jsx`, `src/pages/Reports/Reports.jsx`, `src/components/Reports/AnnexGWorkspace.test.jsx` (if the existing frontend test runner supports it).

**Interfaces:** Uses `/api/annex-g/options`, `/api/annex-g/section`, `/api/annex-g/comments`, and `/api/annex-g/release`; uses existing `api.printHtml` for released reports.

- [ ] Implement an Annex G workspace showing year, grade/section, term, per-learner completion/blockers, calculated age, adviser comments, and Records Officer release status/actions.
- [ ] Add admin-only source-import forms with preview/apply confirmation for enrollment and DOB workbooks.
- [ ] Keep existing attendance/SF2 report controls and history intact.
- [ ] Run `npm run lint` and `npm run build`; correct failures caused by the change.

### Task 5: Isolated verification and self-review

**Files:** no additional production files.

- [ ] Run targeted Annex G tests, migration tests, and frontend lint/build.
- [ ] Run the full backend suite and record unrelated baseline failures without changing them.
- [ ] Start a separate temporary API/UI instance backed by an isolated database; use synthetic people/scores/attendance only.
- [ ] In the live built-in browser, confirm adviser draft/comment flow, blocker display, Records Officer release, print view, and history; compare the rendered grade values to the gradebook calculation.
- [ ] Confirm no real learner grades or attendance changed; inspect the final diff and document remaining policy/output risks.
