# Demo Teacher Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development to implement this plan task-by-task. Track steps with checkboxes.

**Goal:** Let administrators preview and confirm realistic demo teachers to fill missing JHS teaching and adviser assignments safely.

**Architecture:** A single backend setup service generates proposals from existing academic structure and commits a confirmed batch atomically. Existing teacher access, subject eligibility, password security and assignment invariants remain authoritative. An Administration panel displays preview results and unresolved sections before confirmation.

**Tech Stack:** Existing React, FastAPI, SQLAlchemy migrations, Pydantic and unittest; no new dependencies.

**Spec:** ../specs/2026-10-23-demo-teacher-setup-design.md

## Global Constraints
- Demonstration accounts only, realistic names with separate Demo metadata.
- One subject per teacher per school year; one grade level; multiple eligible sections; at most one adviser section per teacher.
- Preserve existing accounts, advisers, teaching assignments and all grades, attendance, reports and biometrics.
- Respect JHS elective allowed grades and STE restrictions; no SHS coverage in this version.
- Administrator reviews the exact proposal before any account is created.
- No shared default password or plaintext credentials in persistent previews, logs or audit details.

## Review Focus
- Repeated confirmation must not generate duplicate users or assignments.
- Existing account names/usernames must never be mistaken for reusable demo accounts.
- Too few missing teaching slots for advisers must produce unresolved sections, not overwritten assignments.
- A concurrent assignment change must invalidate the preview before any write.
- Adviser links must be keyed by school year and section, with one adviser section per teacher in each year; changing years must not overwrite prior assignments.

### Task 1: Preview generator and provenance
**Files:** Create backend/app/services/demo_teacher_setup.py and backend/tests/test_demo_teacher_setup.py; modify backend/app/models.py, migrations.py and schemas.py.

**Interfaces:** `preview_demo_teacher_setup(db, school_year_id: int, section_ids: list[int], actor) -> dict` returns batch_id, proposed teachers (stable proposal keys, realistic display names, unique demo usernames, subject_id, grade_level_id, section_ids, adviser_section_id), preserved assignments and unresolved sections. Persist batch provenance and non-secret proposal JSON in a DemoTeacherSetupBatch record; User.is_demo defaults to false.

- [x] Write failing isolated tests: existing coverage unchanged; eligible gaps grouped by subject/grade; multiple sections supported; disallowed electives and inactive/deleted subjects excluded; names/usernames unique; no preview-created accounts.
- [x] Run `.venv/Scripts/python -m unittest tests.test_demo_teacher_setup -v` from backend and observe failure.
- [x] Add year-specific adviser assignment storage and migrate legacy links only into SY 2026–2027 (confirmed by the user), preserving the original links for traceability. Resolve the actual school-year record by name; stop with a clear explanation if absent, duplicated or conflicting rather than guessing an ID. Add unique constraints for (school_year_id, section_id) and (school_year_id, teacher_user_id). Update adviser setup, authorization, advisory rosters, attendance and report consumers to resolve the relevant year; never borrow an adviser from a different year. Test that the same section and teacher may have different assignments across years while conflicts within one year are rejected.
- [x] Implement deterministic planning and a small realistic-name pool with collision-safe expansion. Propose advisers only among teachers covering each section in the selected year; split missing coverage when needed and flag sections with no available slot. Preserve every assignment outside the selected year.
- [x] Add an additive idempotent migration for demo provenance. Run tests including migration rerun, existing non-demo defaults and existing adviser commitments.

### Task 2: Authorized, atomic confirmation
**Files:** backend/app/services/demo_teacher_setup.py, main.py, schemas.py; backend/tests/test_demo_teacher_setup.py.

**Interfaces:** `apply_demo_teacher_setup(db, batch_id: str, actor) -> dict` consumes the stored proposal, returns created account/assignment IDs and one-time temporary credentials. Admin-only POST endpoints `/api/admin/demo-teacher-setup/preview` and `/api/admin/demo-teacher-setup/{batch_id}/apply` wrap these services.

- [x] Write failing tests for non-admin access, unknown batch, duplicate confirmation, stale academic structure, conflicting advisers, missing eligible subjects and rollback after a simulated final assignment failure.
- [x] Store a digest of relevant academic structure and assignments with the preview. On apply, lock the batch, school year and target sections consistently, re-read relevant assignments and reject a stale digest. Existing assignment writers must participate in the same school-year locking convention so race protection is real.
- [x] Reuse password hashing, strong-password generation and forced password-change requirements from existing account provisioning. Use transaction-safe service logic rather than calling endpoints that commit individually. Create accounts, assignments, adviser links, demo provenance and audit entries in one transaction.
- [x] Mark the batch applied atomically. Repeated apply returns the existing result without recreating accounts, resetting passwords or redisclosing plaintext credentials. Never store plaintext temporary credentials in the batch or logs.
- [x] Run all new tests and existing assignment/account permission regressions; compare protected grade/attendance/person record snapshots before and after.

### Task 3: Administrator preview and verification
**Files:** Create src/components/Setup/DemoTeacherSetup.jsx; modify src/pages/Administration/Administration.jsx and scoped rules in src/styles/index.css; add appropriate component/service tests using the project's existing test approach.

**Interfaces:** Consume Task 2 endpoints. Administrator selects an active JHS school year and sections, then requests a preview. Applying requires a separate explicit confirmation of that exact batch.

- [x] Build selection, loading, preview, unresolved, stale, failure and completed states. Show each teacher's Demo marker, subject, grade, handled sections and optional adviser section. State that existing assignments stay untouched and schedules are not generated.
- [x] Keep Generate preview and Confirm creation distinct. Show unresolved adviser shortages without claiming complete coverage. If apply fails, retain the preview and display the server explanation; never claim partial success after rollback.
- [x] Show one-time credentials through the existing secure account handoff convention; do not copy them into ordinary page logs or exports. Explain how Admin can reset a lost temporary password through the existing flow.
- [x] Run `npm run verify`, backend tests and `git diff --check` fresh; record exit codes, failures and existing warnings.
- [ ] Check mobile rendering (browser viewport resizing is unavailable). Desktop preview and native keyboard controls were checked. In an authenticated administrator browser, verify preview without applying to real sections; test apply with isolated synthetic academic data and inspect all resulting assignments.
- [x] Obtain a fresh code review, fix findings, rerun affected checks, then report results and unverified live cases. Do not create accounts in the user's live database merely to demonstrate that the feature works.

## Self-review
The amended requirement expands the work to year-specific adviser persistence and all authorization/report consumers. Implementation must first inspect every use of SchoolSection.adviser_user_id and adviser_name and map it to a year-aware lookup. Legacy mapping to SY 2026–2027 is confirmed. Native execution remains the previously selected session preference; no software implementation or account creation has occurred for this feature yet.


## Verification record � 2026-10-23
- Implemented preview/apply, demo provenance, one-time credentials, annual advisers, school-year-aware permissions and admin controls.
- Fresh final review identified legacy gradebook authorization using the current year; regression reproduced the problem and the fix now uses the saved year.
- Focused setup, migration, annual authorization and elective tests: 24 passed.
- Attendance and report API tests: 33 passed in isolated temporary databases.
- Non-workbook grading/assignment regressions: 54 passed.
- Frontend lint/build passed. Existing Scanner memoization and bundle-size warnings remain.
- Broader grading API has 4 XLSX policy-mismatch assertion failures; broad workbook regressions also fail fixed-template/custom-policy exports. These were not changed under this assignment task and are not claimed passing.
- Live PostgreSQL migration 0022 applied. Fingerprints match for persons (24), attendance events (470), scores (270), gradebooks (62), policies (10), sections (10), teaching assignments (7).
- Live admin preview for Jose, Manuel and Oslo proposes 24 demo teachers, preserving 6 teaching assignments and 3 advisers; Confirm creation was not clicked. No live demo accounts created.
- User subsequently authorized removing only unused archived subjects. 13 were permanently removed after checking foreign keys, legacy gradebooks, schedules and reports. All 7 archived sections and 2 archived subjects with linked grades remain. Protected records again fingerprint-identical.
- Ruling: Only current active, undeleted sections/grade levels migrate to annual assignments. Archived links remain unchanged in original fields, never become current access. This preserves the strict one-adviser/year rule and all archived records; restored sections require an explicit annual adviser assignment.
- Ruling: No live demo accounts are created by implementation verification; the administrator reviews and confirms the exact proposal.
- Remaining: mobile viewport visual check; unrelated XLSX mismatches. No source commit or push requested for this task.
