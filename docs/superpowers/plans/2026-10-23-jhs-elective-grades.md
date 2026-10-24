# JHS Elective Allowed Grades Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development to implement this plan task-by-task. Track steps using checkboxes.

**Goal:** Administrators restrict JHS electives to one or more Grades 7–10 without changing existing scores or gradebooks.

**Architecture:** Store allowed grades on the existing subject record. Reuse matching rules in browser selectors and enforce them on the backend for new assignments, schedules, and gradebooks. Historical records stay readable and exportable.

**Tech Stack:** Existing FastAPI, SQLAlchemy migrations, Pydantic schemas, React, JavaScript tests, Python unittest; no new dependencies.

**Spec:** ../specs/2026-10-23-jhs-elective-grades-design.md

## Global Constraints
- Administrators select one or more of Grades 7–10 for each JHS elective.
- Retain the existing STE restriction; leave core JHS subjects and SHS rules unchanged.
- Existing electives initially allow Grades 7–10 until explicitly narrowed.
- Never delete, reassign, or recalculate saved records to enforce a narrowed selection.
- Preserve grading policies, scores, and Excel template mappings.

## Review Focus
- Existing null subject settings must retain previous access, not hide every elective.
- Reject Grade 11/12, empty selections and unauthorized edits for JHS electives.
- A renamed or prefixed grade must match its normalized number.
- Narrowing eligibility must not make historical gradebooks unreadable or unexportable.
- A new out-of-scope assignment must fail even if a caller bypasses the browser.

### Task 1: Subject storage and eligibility rules
**Files:** backend/app/models.py, migrations.py, schemas.py, services/academic_context.py; backend/tests/test_jhs_elective_grades.py (new).

**Interfaces:** Subject.allowed_grades_json stores a JSON list; SubjectPayload.allowed_grades is list[int] | None. Academic-structure output exposes allowed_grades. New helper subject_matches_grade(subject, grade_name: str) -> bool normalizes grade labels and enforces only elective restrictions in addition to existing JHS/SHS rules.

- [ ] Write failing tests for [7], [7,8], normalized 'Grade 8', rejection of 11, empty elective selections, and legacy null settings allowing 7–10.
- [ ] Run `.venv/Scripts/python -m unittest tests.test_jhs_elective_grades -v` from backend; confirm missing behavior fails.
- [ ] Add an additive, idempotent migration. Existing subjects receive compatible defaults; never rewrite scores or class records. Validate allowed_grades on subject save, canonicalizing unique grades in ascending order. Non-JHS-electives retain their current eligibility.
- [ ] Run the same tests and confirm success, including migration rerun and unchanged student-score snapshots.

### Task 2: Backend enforcement and historical access
**Files:** backend/app/main.py, services/grading.py; backend/tests/test_jhs_elective_grades.py.

**Interfaces:** Consume subject_matches_grade from Task 1. Subject list responses include allowed_grades and existing incompatible section assignments can be identified from their grade levels.

- [ ] Add failing tests: administrator-only updates; reject new teaching assignments, schedules and gradebooks outside allowed grades or outside STE; accept multiple permitted grades. Tests must submit requests directly, not depend on UI filtering.
- [ ] Add tests proving existing gradebooks remain readable/exportable after narrowing; existing incompatible assignments remain stored and are visible for review. Enforce new-gradebook eligibility after finding an existing saved record, preserving historical access.
- [ ] Apply the helper in subject-teaching assignment validation, schedule validation, and new gradebook creation. Subject saves must not cascade mutations to existing assignments.
- [ ] Run targeted tests plus `tests.test_grading_regressions` and `tests.test_grading_api`; distinguish failures caused by this change from known export failures rather than weakening assertions.

### Task 3: Administrator form and browser filtering
**Files:** src/pages/Administration/Administration.jsx, src/services/academicContext.js, src/pages/Grading/Grading.jsx, src/components/Setup/ClassScheduleManager.jsx; src/services/gradingCalculations.test.js. Inspect other schedule and teacher selectors using the academic-structure response before editing.

**Interfaces:** subjectMatchesGrade(subject, gradeName) consumes subject.allowed_grades. Pass the actual selected grade, replacing Grading.jsx's current representative '7'/'11' call so Grade 8 restrictions are evaluated correctly.

- [ ] Add failing JavaScript assertions for electives allowed in Grade 7 only, Grades 7 and 8, prefixed grade labels, legacy defaults, core JHS and SHS eligibility.
- [ ] Add Grade 7/8/9/10 checkboxes to JHS elective creation/editing, require one selection, preserve selections on edit, and show allowed grades in the subject list.
- [ ] Filter eligible teaching-assignment sections, schedule subjects, and new-gradebook selectors through shared rules. Display retained incompatible assignments as needing review; never silently reassign them.
- [ ] Run `node src/services/gradingCalculations.test.js` and `npm run verify` from EduScan; require successful exit and report unrelated existing warnings.

### Task 4: End-to-end verification and delivery
**Files:** tests and form files above; update the design status after verification.

- [ ] Run the new backend tests, JavaScript tests, lint/build and `git diff --check` fresh; record complete outputs and failures.
- [ ] In an authenticated administrator session, check single-grade and multi-grade selections and invalid empty selection. Use isolated records for save tests; do not narrow real subjects as a demonstration.
- [ ] Verify teacher subject selection for eligible and ineligible grade contexts, historical-gradebook access, unchanged saved-score snapshots, and existing core/elective export mappings.
- [ ] Report exactly which live checks were possible, any remaining blockers, and migration activation requirements. Do not push or change real subject assignments without a request.

## Self-review
Tasks cover persistence, defaults, validation, all known eligibility callers, administrator controls, historical compatibility, and verification. Exact test-case assertions are specified above; implementation reuses the existing layers. Inspect discovered additional consumers during Task 3 without expanding feature scope.
