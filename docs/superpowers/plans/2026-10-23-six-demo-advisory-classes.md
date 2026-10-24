# Six Demo Advisory Classes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. Native execution is the user's preserved preference; obtain their plan review before implementation.

**Goal:** Add a dedicated, confirmed setup of six demo teacher accounts and six separate Grade 7–BEP advisory sections for an active school year.

**Architecture:** Extend the existing demo setup service and batch JSON with a dedicated setup kind. Reuse its name generation, digest, password handling, atomic apply and annual adviser helper. A second preview endpoint feeds a dedicated option in the existing Administration component; no new database table or dependency is needed.

**Tech Stack:** React, FastAPI, Pydantic, SQLAlchemy, unittest; existing password hashing and audit helpers.

**Spec:** `docs/superpowers/specs/2026-10-23-six-demo-advisory-classes-design.md`

## Global Constraints
- Exactly six subjects: Filipino, Science, Values Education, TLE, MAPEH and Araling Panlipunan, using existing active subject records.
- Six realistic names, separate Demo indicators, unique usernames, one subject and one separate Grade 7–BEP advisory section per teacher in the selected school year.
- Preserve Jose, Manuel, Oslo, current advisers, teaching assignments and all existing people, grades, attendance, biometrics, schedules and reports.
- Preview and separate explicit confirmation; atomic creation, stale protection and repeat protection.
- Plaintext temporary passwords are returned once, never stored in preview/result JSON, audit or logs. Force password change on first sign-in.
- No students, scores, attendance, schedules or reports generated.
- No automatic live account creation during verification. No unrelated changes or broad refactoring.

## File Responsibilities
- Modify `backend/app/services/demo_teacher_setup.py`: dedicated preview, reusable name allocation and dedicated apply branch inside the current transaction.
- Modify `backend/app/schemas.py`: year-only request for the dedicated preview.
- Modify `backend/app/main.py`: administrator-only dedicated preview endpoint; retain shared apply endpoint.
- Modify `src/components/Setup/DemoTeacherSetup.jsx`: explicit setup choice and preview display; retain current missing-assignment mode.
- Modify `src/styles/index.css` only if existing controls need narrowly scoped layout adjustments.
- Create `backend/tests/test_demo_advisory_setup.py`: synthetic service, API authorization, rollback, idempotency and preservation cases.
- Keep `backend/tests/test_demo_teacher_setup.py` and `backend/tests/test_section_advisers.py` passing.

## Review Focus
- Two distinct administrator previews confirmed concurrently for one year must not create twelve accounts.
- A pre-existing or archived section with a colliding name must never be reused, restored or reassigned silently.
- Deleted, ambiguous or wrong-category subject/grade records must not be guessed.
- Switching setup type or year must invalidate the displayed confirmation; refreshing accounts must not discard the one-time credential result.
- A failure after section creation must roll back sections, accounts and assignments together.

## Implementation Decisions
- Use `kind='six_advisory'` in dedicated stored proposals; old proposals without kind retain existing behavior.
- Add `DedicatedDemoAdvisoryPayload(school_year_id: int > 0)` and POST `/api/admin/demo-teacher-setup/advisory-preview`.
- Service interface: `preview_demo_advisory_setup(db, school_year_id: int, actor) -> dict`. Shared `apply_demo_teacher_setup(db, batch_id: str, actor) -> dict` remains unchanged externally.
- Dedicated proposal teacher entries retain current display fields and add `new_section_name`; `section_ids=[]` until apply. Include `kind`, `grade_level_id`, `program='BEP'`, and the existing school year/display fields. New names must not masquerade as persisted section IDs.
- Section names include the year because section uniqueness is grade/name, not year: `Demo Filipino 2026-2027`, etc. Use the six subject labels above. Reject any collision, including archived sections.
- Resolve exactly one active, undeleted Grade 7 using the shared grade normalization. Resolve each subject by a small explicit alias set (case/space normalized), including VE/Values Education and TLE/Technology and Livelihood Education. Require JHS, non-elective and Grade 7 eligibility. Fail with the specific missing/ambiguous learning area; never create a replacement subject.
- Under the existing school-year lock, inspect applied batches for `kind='six_advisory'` before writing. Existing setup returns `already_applied=True`, stored created IDs and empty credentials. A second preview/apply cannot add another six accounts. Do not reuse generic demo batches.
- Result adds `created_section_ids` to existing created user/count fields. Preserve existing credentials behavior.

### Task 1: Dedicated preview and exact subject coverage
**Files:** service, schema, new test file.
**Consumes:** `_state(db, year_id)`, existing eligible-subject and name rules.
**Produces:** dedicated stored proposal returned by `preview_demo_advisory_setup`.

- [x] Write `test_preview_proposes_six_grade7_bep_classes_without_creating_accounts_or_sections`: assert exact six subject IDs, six unique realistic names/usernames, six distinct year-qualified section names, selected year, BEP, and unchanged User/SchoolSection counts.
- [x] Write `test_preview_rejects_missing_ambiguous_or_ineligible_context`: inactive year, absent/duplicate normalized Grade 7, absent/archived subject, ambiguous aliases, SHS subject and colliding archived section each fail without a batch or school record write.
- [x] Run `.venv\Scripts\python.exe -W ignore -m unittest tests.test_demo_advisory_setup -v` from backend; observe failures before implementation.
- [x] Implement the dedicated preview using existing batch persistence and digest. Extract only the shared name allocation needed by both modes; preserve generic proposal results.
- [x] Run the new suite plus `tests.test_demo_teacher_setup`; expected zero failures. Record results and commit only task-related changes when the task's workspace diff can be staged without unrelated work.

### Task 2: Atomic creation and authenticated routes
**Files:** service, main.py, new test file.
**Consumes:** dedicated proposal from Task 1.
**Produces:** six accounts/sections/teaching links/annual adviser links and one-time credentials through the existing apply endpoint.

- [x] Write `test_apply_creates_exactly_six_owned_classes_and_preserves_protected_rows`: assert six is_demo teachers, hashed distinct passwords, must_change_password, one subject and one Grade 7–BEP section each, annual adviser year correct, empty rosters and identical snapshots of existing protected rows.
- [x] Write `test_second_batch_cannot_duplicate_setup_for_same_year`: preview twice, apply both; second does not create more users/sections or reveal credentials. Compile the locking path for PostgreSQL and assert the SchoolYear row is locked before checking applied sibling batches.
- [x] Write `test_failure_after_creating_section_rolls_back_everything`, `test_stale_preview_rejected`, and `test_existing_year_setup_never_resets_credentials_or_reassigns_sections`.
- [x] Write route tests for administrator access and teacher/records-officer denial, invalid year payload, safe conflict responses and unchanged generic preview/apply behavior.
- [x] Run tests and observe failures, then extend shared apply inside its current transaction. Create each new section before the teaching/adviser links; reuse `assign_section_adviser`. Audit IDs and non-secret metadata only.
- [x] Add year-only schema and admin-only route. Run new and existing demo/adviser suites; expected zero failures. Record and make a scoped commit as above.

### Task 3: Dedicated administrator option and verification
**Files:** DemoTeacherSetup.jsx; scoped CSS if needed; plan verification record.
**Consumes:** Task 1 dedicated preview endpoint and Task 2 shared apply result.
**Produces:** administrator can select either existing missing-assignment setup or “Create six demo advisory classes”.

- [x] Add a clearly labeled setup choice, retaining the shared year selector. Dedicated mode hides the existing-section checkboxes, lists the six subjects and states Grade 7–BEP and initially empty rosters.
- [x] Reset preview/confirmation on mode or year changes. Render proposed new section names in the existing preview table; keep preview and confirm distinct. Show existing setup state without an actionable duplicate-create button.
- [x] Keep the one-time credential result visible after structure reload. Do not persist credentials in browser storage or ordinary logs. Explain sign-in requires changing the temporary password.
- [x] Run `npm run verify` and `git diff --check`; expected exit 0. Run focused backend suites, attendance/report permissions, and grading assignment permission regressions in separate processes to avoid their fixture environment collisions. Report unrelated existing XLSX failures accurately.
- [x] Restart only the backend if needed after fresh tests. In authenticated admin UI, verify the dedicated live preview has exactly six subjects/sections and no changes to existing advisers. Do not confirm live account creation as a test. Check keyboard and desktop layout; report mobile verification unavailable if browser capabilities still cannot resize.
- [x] Obtain one final whole-change review using the preserved Native workflow, fix blocking findings with regression tests, then document results and hand off the preview for administrator confirmation. Do not push or commit unrelated existing changes.

## Self-review
Spec coverage: scope/subjects and naming in Task 1; atomicity, security, repeat protection and preservation in Task 2; visible workflow/credentials in Task 3. All five Review Focus cases have explicit checks above. Interfaces keep the current apply endpoint and generic proposal compatibility. No new table, schema migration, student seeding or dependency is required. Year-qualified names are an implementation choice to satisfy the existing grade/name uniqueness constraint.

## Execution status
Implemented after user approval using Native execution. No live account creation was performed during verification.


## Verification record - 2026-10-23
- 34 focused tests passed: dedicated preview/apply, old setup, annual advisers and elective rules. Credential verification and advisory route checks use isolated accounts.
- 33 attendance/report permission tests and 54 non-workbook grading/assignment regressions passed in separate isolated runs.
- Frontend lint/build and git diff --check passed. Existing Scanner memoization and bundle size warnings remain.
- One final independent review found no blocking defect. Two real concurrent PostgreSQL transactions were not exercised; PostgreSQL lock-order inspection and sequential distinct-batch duplicate tests cover the serialization design.
- Live authenticated administrator preview shows exactly six new Grade 7-BEP sections/teachers for the requested subjects. Switching setup clears the preview and confirmation. Confirmation was left unchecked; Confirm creation was not clicked.
- Live fingerprints matched for nine protected tables before/after preview: persons 24, attendance events 470, student scores 270, gradebooks 62, policies 10, sections 10, teaching assignments 35, users 34, annual advisers 3.
- Existing 24 demo teachers from the earlier setup were already present before this extension's preview check. This operation proposes six new accounts; it does not repurpose those accounts.
- Desktop preview checked; mobile viewport resizing unavailable. Actual live teacher login was not exercised because live account creation is left for administrator confirmation; isolated password verification and advisory lookup passed.
- Ruling: Continue in the existing working checkout because this extension depends on uncommitted earlier demo-setup files; preserve unrelated work. No commit/push was made and no broad staging was attempted.
- Ruling: Include school year in each new section name, since the existing database requires section names to be unique within a grade across years.
- Remaining limitations: no real PostgreSQL contention run, no mobile visual check, and existing unrelated XLSX mismatch failures were not rerun or changed.
