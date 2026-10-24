# Decimal-Safe Grade Calculation Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make browser previews, saved backend grades, and XLSX calculations agree exactly at grading and transmutation boundaries.

**Architecture:** Keep `grading_engine.py` authoritative for saved grades and make the browser calculation mirror it. Add boundary regressions to the existing export-path tests; change exporter formulas only if those tests show a mismatch remains after the shared calculations are corrected.

**Tech Stack:** Python `Decimal`, JavaScript built-in numeric types, existing unittest and Node test suites, openpyxl and supplied XLSX templates. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-25-grade-calculation-decimal-parity-design.md`

**Workspace note:** Preserve all existing modified and untracked files; implementation is limited to the paths listed in each task.

## Global Constraints

- Keep the current component weights and the ST1/ST2/TE 30/30/40 split unchanged.
- Keep existing scores, saved policies, rounding settings, and transmutation tables unchanged.
- Use decimal-safe arithmetic consistently in browser previews, backend calculation, fixed-template XLSX exports, and adaptive XLSX exports.
- Preserve incomplete-draft display behavior and existing unrounded-threshold behavior: 71.175 remains below 71.18.

## Review Focus

- Exact 71.18 boundary: returns 76 in the browser, backend, and exported workbooks.
- Just-below 71.18 (71.175): remains 75 even when the displayed initial grade rounds to 71.18.
- Partial ST1/ST2/TE drafts: retain current scored-portion normalization and incomplete status.
- Fractional legacy weights: continue normalizing to percentage weights without changing stored policies.
- Custom transmutation boundaries and configured rounding methods: preserve current threshold and display behavior.

---

### Task 1: Make backend grade calculation decimal-safe

**Files:**
- Modify: `backend/app/services/grading_engine.py`
- Test: `backend/tests/test_grading_engine.py`

**Interfaces:**
- Preserve `calculate_component_percentage`, `calculate_weighted_grade`, `apply_transmutation`, and `calculate_student_grade` signatures and response types.
- Keep API-facing numeric results as floats/integers; use `Decimal` internally for score ratios, 30/30/40 exam weighting, weighted grade, and transmutation comparisons.

- [x] **Step 1: Add a failing regression**

Add a complete calculation with WW/PT/exam weights 20/50/30. Give WW and PT one 14.236/20 score each and ST1, ST2, and TE each 14.236/20; use a custom lower-bound table with 75 below 71.18 and 76 from 71.18. Assert the displayed initial grade is `71.18` and reported grade is `76`. Repeat with 14.235/20 throughout and assert the displayed initial grade rounds to `71.18` but the unrounded comparison reports `75`.

- [x] **Step 2: Run the focused test and confirm it fails on the current precision path**

Run: `.\.venv\Scripts\python -m unittest tests.test_grading_engine.TestFullStudentCalculation.test_decimal_safe_transmutation_boundary -v`

Expected: the exact-boundary case reports `75` instead of `76` before the fix.

- [x] **Step 3: Use `Decimal(str(value))` through calculation and threshold selection**

Convert inputs at the calculation boundary, retain current incomplete/weight normalization behavior, and convert to the existing public numeric types only when constructing result objects. Do not round before transmutation.

- [x] **Step 4: Run backend calculation regressions**

Run: `.\.venv\Scripts\python -m unittest tests.test_grading_engine tests.test_grading_regressions -v`

Expected: existing calculation and saved-grade behavior passes; the two new boundary cases pass.

### Task 2: Mirror decimal-safe arithmetic in the browser

**Files:**
- Modify: `src/services/gradingCalculations.js`
- Test: `src/services/gradingCalculations.test.js`

**Interfaces:**
- Preserve all exported function signatures and the result object fields consumed by `GradingSheet.jsx`.
- Keep score inputs and UI outputs numeric; use exact decimal-value arithmetic internally without adding a package.

- [x] **Step 1: Add matching browser boundary tests**

Mirror Task 1’s complete WW/PT/exam case: 14.236/20 throughout produces displayed initial grade 71.18 and reported grade 76; 14.235/20 displays 71.18 but reports 75. Keep the existing partial-exam normalization test passing.

- [x] **Step 2: Run the Node test and confirm the exact-boundary test fails**

Run: `node --test src/services/gradingCalculations.test.js`

- [x] **Step 3: Apply the backend’s decimal semantics in the browser calculation path**

Use the smallest built-in arithmetic approach that preserves decimal input values and existing return types; avoid changing score rounding, draft handling, or grading policy.

- [x] **Step 4: Run browser calculation tests and production checks**

Run: `node --test src/services/gradingCalculations.test.js` and `npm run verify`.

Expected: all browser calculations pass and the app builds cleanly.

### Task 3: Verify XLSX formula and cache parity at the same boundary

**Files:**
- Test: `backend/tests/test_jhs_export_parity.py`
- Test: `backend/tests/test_mapeh_area_exports.py`
- Test: `backend/tests/test_adaptive_class_record.py`
- Test: `backend/tests/test_grading_regressions.py`
- Conditional modify: `backend/app/services/class_record_export.py`, `backend/app/services/adaptive_class_record.py`

**Interfaces:**
- Keep export endpoints, template selection, workbook layouts, and cached-cell format unchanged.
- Fixed-template exports retain their supplied calculation formulas, with a 12-decimal normalization before transmutation; adaptive exports use `_term_sheet` and `_write_class_record_workbook`.

- [x] **Step 1: Add isolated export regressions for the 71.18 boundary**

In the existing temporary/in-memory fixtures, assert both 71.18→76 and 71.175→75 in saved grades and exported caches for one ordinary JHS subject, MAPEH learning-area exports, and one adaptive workbook. Inspect fixed-template formulas to ensure they compare unrounded values. Assert saved score snapshots remain unchanged and update the template-preservation test to allow only the intended initial/final-grade formula overrides.

- [x] **Step 2: Run the focused export tests and identify any remaining formula mismatch**

Run: `.\.venv\Scripts\python -m unittest tests.test_jhs_export_parity.JHSExportParityTests tests.test_mapeh_area_exports.MapehAreaExportTests.test_grades_7_to_10_and_all_export_scopes tests.test_adaptive_class_record.AdaptiveClassRecordTests.test_variable_maxima_components_and_formula_caches_match_engine tests.test_adaptive_class_record.AdaptiveClassRecordTests.test_exam_conversion_uses_unrounded_percentages_at_grade_boundaries -v`

- [x] **Step 3: Correct only an exporter formula that still disagrees**

If an export regression fails after Tasks 1–2, update only the corresponding formula-generation path to preserve the exact unrounded comparison. Keep supplied templates, grades, saved scores, policies, and formula caches intact. If tests pass without exporter changes, leave both production exporter files untouched.

- [x] **Step 4: Run all focused parity checks**

Run the backend calculation and export commands from Tasks 1 and 3, then run `node --test src/services/gradingCalculations.test.js` and `npm run verify`.

Expected: exact 71.18 is grade 76, 71.175 remains 75, each tested XLSX formula/cache matches the backend result, and all isolated saved-score snapshots are unchanged. Report any pre-existing unrelated export-suite failures separately.
