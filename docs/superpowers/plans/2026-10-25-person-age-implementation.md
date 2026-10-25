# Person Date of Birth and Calculated Age Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture a person's date of birth in the Administration and scanner enrollment forms and display age as a read-only calculation.

**Architecture:** Store one nullable `date_of_birth` value on `Person`; calculate age in the shared React enrollment fields and do not persist age separately. Keep the raw birth date in administrator-scoped responses, and let roster imports optionally supply it. This builds the data foundation for Annex G; the Annex G report workflow and release preflight remain a separate implementation.

**Tech Stack:** React, JavaScript built-in `node:test`, FastAPI, Pydantic, SQLAlchemy, versioned SQL migrations, Python `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-25-person-age-design.md`

## Global Constraints

- Require date of birth for new student records; keep it optional for faculty and non-teaching personnel.
- Keep existing rows with null date of birth valid and unchanged until an administrator verifies the value.
- Reject dates after the current Asia/Manila school date.
- Age is read-only and derived from date of birth; do not persist a separate age.
- Keep date of birth out of teacher-facing roster responses and general attendance exports.
- Keep existing records valid with a null date of birth; do not backfill or fabricate birth dates.
- Do not alter grading, attendance, face capture, or enrollment rules.
- Do not implement Grades 11–12 reporting as part of this change.

## Review Focus

- Legacy person rows with no birth date remain readable and editable without fabricated values: migration and CRUD tests in Task 1.
- New student records require birth date, staff records may omit it, and future dates are rejected: API tests in Task 1.
- Teacher-facing person responses do not expose birth dates: API serialization test in Task 1.
- Blank/missing import cells do not accidentally erase an existing birth date: import test in Task 2.
- Age changes on the birthday, handles leap-day births consistently, and returns blank without a date: age utility tests in Task 3.

---

### Task 1: Store and protect date of birth

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/migrations.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_person_date_of_birth.py`
- Create: `backend/tests/test_person_date_of_birth_migration.py`
- Update: student-creation API test fixtures to include the required date of birth.

**Interfaces:**
- `Person.date_of_birth: date | None` maps to nullable SQL `DATE`.
- `PersonCreate.date_of_birth: date | None = None` accepts an omitted value for update compatibility and staff; `_new_person_record` requires it for new students and rejects dates after the current Asia/Manila school date.
- `person_json(person, db, include_private=True, include_sensitive=False)` includes `date_of_birth` only when `include_sensitive` is true; only administrator endpoints set it true.

- [x] **Step 1: Write failing schema, API privacy, and migration tests.** Cover student create with/without date, staff create without date, future date rejection, admin read/write, teacher list omission, legacy null rows, and migration idempotence.
- [x] **Step 2: Run the focused tests and confirm the new assertions fail.** Run from `EduScan/backend`: `python -m unittest discover -s tests -p "test_person_date_of_birth*.py" -v`.
- [x] **Step 3: Add the nullable model/schema field and future-date validation.** Keep the date value in ISO form through create and update payloads; require it in `_new_person_record` only when creating a student.
- [x] **Step 4: Add migration `0025_person_date_of_birth`.** Use `_add_column_if_missing` with `DATE NULL`; leave old rows unchanged.
- [x] **Step 5: Update person serialization call sites.** Keep `include_sensitive=False` by default; enable it only on admin-only create, update, `/api/admin/persons`, and admin status-change routes. Verify teacher list and attendance callers remain redacted.
- [x] **Step 6: Rerun the focused tests and confirm they pass.**

### Task 2: Support date of birth in roster imports

**Files:**
- Modify: `backend/app/services/roster.py`
- Modify: `backend/tests/test_person_date_of_birth.py`
- Update: existing roster workbook fixtures with verified synthetic dates.

**Interfaces:**
- `parse_roster(data)` recognizes `date of birth`, `date_of_birth`, and `dob` headers and returns `date_of_birth` as a `date | None`.

- [x] **Step 1: Add failing workbook tests.** Cover Excel date cells and ISO date strings, staff without DOB, new student import without DOB, invalid date, and an existing record receiving a blank DOB cell.
- [x] **Step 2: Run the focused roster tests and confirm they fail.** Run the Task 1 unittest command.
- [x] **Step 3: Reuse `_date_value` for the DOB column.** Reject new student imports without DOB; allow staff imports without it. Treat an omitted or blank DOB on an update as “leave existing DOB unchanged.”
- [x] **Step 4: Rerun focused roster tests and confirm they pass.**

### Task 3: Show calculated age in both enrollment forms

**Files:**
- Create: `src/services/personAge.js`
- Create: `src/services/personAge.test.js`
- Modify: `src/components/Scanner/EnrollmentFields.jsx`
- Modify: `src/pages/Administration/Administration.jsx`
- Modify: `src/components/Scanner/StudentRegistrationModal.jsx`

**Interfaces:**
- `calculateAge(dateOfBirth, asOfDate)` accepts ISO date strings and returns a non-negative integer or `null` when no valid birth date is available.
- The shared enrollment fields bind to `form.date_of_birth` and display the returned age as read-only text.

- [x] **Step 1: Write failing age utility tests.** Cover missing/invalid date, before and on the birthday, and a leap-day birth (age increases on March 1 in non-leap years).
- [x] **Step 2: Run `node --test src/services/personAge.test.js` from `EduScan` and confirm it fails.**
- [x] **Step 3: Implement `calculateAge(dateOfBirth, asOfDate = new Date())` using calendar date parts.** Avoid parsing an ISO date through UTC so local time zones cannot shift the displayed birthday.
- [x] **Step 4: Add the date input and read-only age display to `EnrollmentFields`.** Show it for student and personnel roles; require it for new student forms, but allow legacy student edits with a blank date and keep it optional for staff.
- [x] **Step 5: Add `date_of_birth: ''` to the Administration and scanner form defaults.** Preserve the value when editing an administrator-visible record and include it in both create payloads, including camera-free registration.
- [x] **Step 6: Rerun the age tests.** Run `npm run lint` and `npm run build` from `EduScan` to verify both form integrations.

### Task 4: Focused end-to-end verification

**Files:** No additional files.

- [x] **Step 1: Run backend date-of-birth and roster tests** from `EduScan/backend`: `python -m unittest discover -s tests -p "test_person_date_of_birth*.py" -v`.
- [x] **Step 2: Run frontend age tests, lint, and production build** from `EduScan`: `node --test src/services/personAge.test.js`, `npm run lint`, and `npm run build`.
- [x] **Step 3: Inspect the final diff** to confirm the DOB-specific changes contain no gradebook or saved-score edits. Other unrelated pre-existing worktree edits remain outside this implementation.
