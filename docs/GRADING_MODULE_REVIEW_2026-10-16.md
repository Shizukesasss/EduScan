# Grading module review — 16 October 2026

What this repo does: EduScan lets assigned teachers enter scores, calculate term grades, finalize class records, and request corrections that an administrator reviews. This review covers the grading module, its modern and legacy API routes, calculation engines, permissions, Excel export, and relevant tests. Assumed load: several teachers using one school API and Supabase PostgreSQL, including a teacher opening the same record in two tabs.

## Implemented: incomplete records cannot be finalized

The previous calculation removed a configured assessment when every learner's entry in its column was blank. A teacher could enter one assessment per component, leave other configured columns blank, and still get a complete calculated grade. Both the browser preview and server calculation used that rule.

Every assessment listed in Assessment Setup now counts toward completeness. Blank, Missing, Absent, Excused, Incomplete, and Not Applicable entries leave the learner's initial and term grades blank. Teachers can save partial drafts, but Finalize stops with a warning naming affected learners. A genuine entered zero is a valid score; a completed failing grade may still be finalized.

The server independently rejects incomplete finalization. Its validation endpoint reports incomplete learners and empty setup as errors. The older grading route also rejects empty records and an unentered manual overall score. Official XLSX download now requires the selected record to be Finalized or Locked and its current learners to have complete scores. Print remains available for draft work.

No formulas, weights, transmutation rules, role permissions, database columns, or saved score values were changed. No existing record was automatically reopened, finalized, or deleted. Existing Submitted records retain their status and can still be finalized when complete. Teachers can adjust unused blank activities through the existing Assessment Setup controls; no activities were removed automatically.

## Checks and review of this change

- 52 isolated backend grading regression tests passed, including the four follow-up fixes below.
- 6 isolated grading API integration tests passed, including admin read-only access, teacher assignment restrictions, locked scores, adjustment permissions, blank-column rejection, and export rejection.
- 10 isolated legacy smoke tests passed.
- 16 JavaScript calculation, workflow, and class-record-selection tests passed.
- Frontend lint and production build passed. The existing approximately 507 kB JavaScript bundle warning remains.
- Fixed older API test assertions that assumed the first unread notification belonged to the latest test, assumed reading another teacher's notification would return 403 instead of safely ignoring it, and expected 403 rather than the existing 422 assignment rejection. No permission behavior was changed to make these tests pass.
- All writes made by automated checks used temporary SQLite databases, not the school's Supabase database.
- Restarted the API and verified healthy PostgreSQL connectivity and a working frontend.
- In the current teacher page, unfinished assessment columns now leave the grade cells blank. Clicking Finalize showed the incomplete-score warning before opening a confirmation or saving/finalizing a live record.

What this change does: It removes the inference that an entirely blank assessment column is optional and applies the same completion requirement in the browser and server. It also prevents direct official-download calls from bypassing the selected record's finalization requirement. Review found no additional blocking issue introduced by this change in the checked paths.

Verdict: The incomplete-score constraint and all four follow-up fixes are implemented. Grade formulas and admin read-only gradebook access are unchanged; no school data was deleted.

## Follow-up fixes

### 1. Approved adjustments keep finalized grades complete

Source: `backend/app/services/grading.py`, `create_adjustment_request` and `review_adjustment_request` (around lines 971–1109).

- **What this is:** The teacher proposes a score or status correction; an administrator approves or rejects it.
- **Fix:** The request form and server require Scored with a valid numeric value. Approval also checks legacy or crafted pending requests, so a non-scored adjustment stays pending for an administrator to reject. Grade status and audit history are retained.
- **Check:** Regression test covers both request rejection and a legacy pending request that cannot be approved into an incomplete finalized record.

### 2. Draft sibling terms stay out of official workbooks

Source: `backend/app/services/reports.py:453` and the term-writing loop around line 523; MAPEH uses the sibling collection around line 430.

- **What this is:** Exporting one term also loads other terms for the same class and subject into the three-term workbook.
- **Fix:** Regular subjects and MAPEH areas contribute only when each sibling record is Finalized or Locked and all active learners have complete scores.
- **Check:** Workbook regression confirms a Draft sibling term's assessment cells remain blank while finalized terms are exported.

### 3. The Validation checklist warns about pending edits

Source: `src/pages/Grading/Grading.jsx:742` and `src/components/Grading/ValidationChecklist.jsx:19`.

- **What this is:** The checklist shows whether learners have complete computed scores.
- **Fix:** When scores or statuses have unsaved edits, the completion item switches to a warning and tells the teacher to save before relying on the saved-data check. Finalize still validates the live edits.

### 4. Gradebook mutations serialize on the record row

Source: `backend/app/services/grading.py:781`, `update_gradebook_components`, and `finalize_gradebook` around line 906.

- **What this is:** A save checks the record's status before writing; finalization reads scores before changing the status.
- **Fix:** Score saves, component changes, workflow status changes, adjustment requests, and adjustment reviews lock and refresh the parent Gradebook row before validating or writing. This makes PostgreSQL serialize those paths and recheck the current status after waiting.
- **Check:** The lock query is asserted to compile as PostgreSQL `FOR UPDATE`, and the grading regression, API, legacy smoke, and frontend calculation suites pass.
- **Limit:** An actual concurrent two-connection PostgreSQL race was not run; the test database is isolated SQLite and does not enforce PostgreSQL row locks.

## Ponytail reference

Full mode is active. It means the smallest complete change, a focused check for important logic, and an explicit statement of skipped work and risks.

| Level | Trigger | Behavior |
|---|---|---|
| Lite | `/ponytail lite` | Build the requested change and name the smaller option. |
| Full | `/ponytail` | Complete the smallest fix and its necessary checks. |
| Ultra | `/ponytail ultra` | Also question work that the need does not justify. |

| Skill | Purpose |
|---|---|
| ponytail | Smallest complete implementation. |
| ponytail-review | Review a change and the connected code. |
| ponytail-audit | Inspect the named module or repository and rank problems. |
| ponytail-debt | List recorded shortcuts. |
| ponytail-gain | Show measured benchmark savings. |
| ponytail-help | Show the command reference. |

Say “stop ponytail”, “normal mode”, or `/ponytail off` to deactivate it. No mode files or system settings were changed for this request.

Verdict: All four follow-up findings are fixed and regression-tested. The exact PostgreSQL race still needs validation against a disposable PostgreSQL instance before claiming live concurrent-load coverage.

Not checked: a full repository audit outside grading; live Supabase grade writes; PostgreSQL concurrency under load; Excel recalculation inside the installed desktop Excel application; every teacher account individually. Shared teacher components and role restrictions were covered without finalizing real school records.
