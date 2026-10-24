# Clear Gradebook Finalization Errors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** On Finalize, show teachers each learner with the exact missing score activities, including ST1, ST2, and TE, across all gradebooks.

**Architecture:** Keep the current scoring rules and required-activity detection. Collect structured missing learner/activity details in the shared browser validation, render them in a persistent dialog, and use matching server-side details as a fallback if the data changes before the finalize request.

**Tech Stack:** React, JavaScript `node:test`, FastAPI, Python `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-24-grading-finalization-errors-design.md`

## Global Constraints

- Preserve all current score validation, required-activity, status, grading, and MAPEH partner rules.
- Do not change or save scores during validation; finalization remains blocked until validation passes.
- Show all affected learner/activity pairs in a dismissible, persistent message.
- Identify the MAPEH learning area and term where applicable.

## Review Focus

- Genuine zero scores remain valid; test in Task 1.
- Missing ST1, ST2, and TE identify each exact exam item; test in Task 1.
- A used activity missing for one learner identifies that learner and activity; test in Task 1.
- An unused non-exam activity remains excluded under current rules; retain and run the existing test in Task 1.
- Server rejection after a stale page still names the affected learners and activities; test in Task 3.

---

### Task 1: Collect specific missing-score details

**Files:**
- Modify: `src/services/gradingWorkflow.js`
- Test: `src/services/gradingWorkflow.test.js`

**Interfaces:**
- Produce `collectGradebookFinalizationIssues(students, components, scoreEdits = {}, statusEdits = {})`, returning `{ learners: [{ personId, learnerName, activities: [{ label, status }] }], componentsWithoutScores: [{ componentName, activityLabels }] }`.
- `validateGradebookForFinalization(...)` keeps its boolean/throw contract and attaches this data as `error.finalizationIssues` when scores are incomplete.

- [x] Write tests asserting the learner/activity grouping for a missing used activity and for missing ST1, ST2, and TE; include multiple learners and an explicit zero score.
- [x] Run `node --test src/services/gradingWorkflow.test.js`; confirm the new assertions fail because the collector is missing.
- [x] Implement the collector using the existing active-item, edit-buffer, and score-status rules; keep existing setup/weight errors unchanged.
- [x] Re-run the focused test and confirm the specific details and existing unused-activity behavior pass.

### Task 2: Show a persistent finalize validation dialog

**Files:**
- Create: `src/components/Grading/FinalizeValidationDialog.jsx`
- Modify: `src/components/Grading/GradebookActions.jsx`
- Modify: `src/pages/Grading/Grading.jsx`

**Interfaces:**
- `FinalizeValidationDialog({ issue, onClose })` renders grouped learner/activity rows or a detailed server message and stays open until dismissed.
- `onValidateFinalize()` returns `true` on success, `false` when a short non-score error has already been shown, or `{ learners, componentsWithoutScores, message, context }` for the persistent dialog.

- [x] Add the missing-score result path to `handleValidateFinalize`; preserve ordinary setup errors and include MAPEH area/term context when available.
- [x] Update `GradebookActions` to display the dialog when preflight returns details and when the finalize API returns a detailed missing-score rejection; do not open the finalize confirmation for invalid records.
- [x] Keep server errors from producing duplicate toasts; closing the validation dialog returns the user to the gradebook.
- [x] Move keyboard focus into the dialog, keep Tab navigation inside it, support Escape dismissal, and restore focus to Finalize when it closes.
- [x] Run the focused frontend service tests and `npm run verify`; confirm build succeeds and no scoring behavior changes.

### Task 3: Return specific details from server finalization

**Files:**
- Modify: `backend/app/services/grading.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_grading_regressions.py`
- Test: `backend/tests/test_grading_api.py`

**Interfaces:**
- Add `incomplete_gradebook_message(full: dict) -> str` in `backend/app/services/grading.py`; format every affected learner and each required missing assessment label from the gradebook payload.
- Use the same detailed message in the current gradebook finalize and validation endpoints, preserving existing HTTP status codes and rejection behavior.

- [x] Add service/API tests asserting specific learner names and missing item labels, including ST1, ST2, and TE.
- [x] Run the new tests first and confirm they fail against the current generic count-only error.
- [x] Implement the formatter and use it when an otherwise incomplete gradebook is rejected; retain the existing finalization guard and grading calculation.
- [x] Run focused grading backend tests and the full frontend test suite; attempt the broader backend suite with workspace-local temp storage and report any timeout or environment limitation.

### Final verification

- [x] Run all frontend tests (`node --test`): 49 passed.
- [x] Run `npm run verify`: lint/build passed with the existing scanner memoization and >500 kB chunk warnings.
- [x] Run focused backend finalization regressions: 4 passed. Full `test_grading_regressions.py`: 72 tests, with only the same four pre-existing XLSX export failures recorded at baseline.
- [x] Run `git diff --check` on the changed files; no whitespace errors (only line-ending normalization warnings for the two pre-existing frontend service files).
