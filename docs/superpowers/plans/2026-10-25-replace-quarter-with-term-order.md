# Replace quarter with term order Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove Quarter from grading-period administration and replace quarter-named persisted/API term identifiers with `term_order` without changing existing grade data or export behavior.

**Architecture:** Rename the four persisted integer fields in place through migration 0024, then update SQLAlchemy models, schemas, backend callers, and frontend term selection to use `term_order`. The admin UI shows the period name and dates only; the backend resolves order from numbered term names and preserves an existing order during edits.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, SQLite/PostgreSQL migrations, React/Vite, pytest, Node's built-in test runner.

**Spec:** `docs/superpowers/specs/2026-10-25-replace-quarter-with-term-order-design.md`

## Global Constraints

- Preserve period IDs, gradebook IDs, scores, audit history, and term export behavior.
- Do not change grading weights, grade calculations, term dates, or finalization rules.
- Keep historical audit JSON snapshots and legacy `class_key` strings intact.
- Do not display a replacement numeric term field in Administration.

## Review Focus

- Existing period rows may contain any valid order 1–4; migration must preserve the values in all four tables.
- New period names without an unambiguous term number must fail validation without creating a row.
- Editing a legacy period with a custom name must preserve its existing `term_order`.
- Duplicate order within one school year must be rejected by the existing uniqueness constraint.
- Single-term, Terms 1–2, and all-three-term exports must keep their current sheet and data scope.

---

### Task 1: Migrate persisted term identifiers

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/models_grading.py`
- Modify: `backend/app/migrations.py`
- Create: `backend/tests/test_grading_term_order_migration.py`

**Interfaces:**
- Models expose `term_order` for GradingPeriod, Gradebook, GradebookState, and GradeChangeAudit.
- Migration version: `0024_replace_quarter_with_term_order`.

- [x] **Step 1: Write the migration regression test** named `test_renames_term_columns_and_preserves_values_idempotently`; create a legacy SQLite schema with all four `quarter` columns, seed distinct values, mark migrations through 0023 applied, and assert migration 0024 renames the columns, preserves each value, and is idempotent.
- [x] **Step 2: Run the test and confirm it fails** because migration 0024 and the `term_order` model attributes do not exist.
- [x] **Step 3: Add migration 0024** to rename `quarter` to `term_order` only when the old column exists and the new column does not; update model mappings and the grading-period uniqueness constraint to use `term_order`.
- [x] **Step 4: Run the migration test and confirm it passes** with SQLite; run the existing migration tests to confirm older versions still work.

### Task 2: Update backend period API and grading/export logic

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/schemas_grading.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/academic.py`
- Modify: `backend/app/services/grading.py`
- Modify: `backend/app/services/adaptive_class_record.py`
- Modify: `backend/app/services/class_record_export.py`
- Modify: relevant grading and academic API tests under `backend/tests/`

**Interfaces:**
- Academic structure returns `term_order` for every grading period.
- Grading-period create/update accepts a name and derives its order from a numbered term name; updates preserve the stored order when the existing name is custom.
- Gradebook APIs and audit records use `term_order` in place of `quarter`.

- [x] **Step 1: Add tests** for numbered-name order derivation, custom-name edit preservation, invalid-name validation, duplicate-order rejection, and academic-structure responses exposing `term_order` with no `quarter` property.
- [ ] **Step 2: Run those tests and confirm they fail** on the current quarter-based API.
- [x] **Step 3: Rename backend term references** in validation, persistence, lookup, audit, export paths, and startup defaults; implement the smallest name-to-order parsing needed by the approved design while retaining existing range and uniqueness validation. New default periods are named Term 1 through Term 4, preserving the existing period count and dates.
- [x] **Step 4: Run the focused API, grading, migration, and export tests** and confirm period selection plus term export scopes remain unchanged.

### Task 3: Remove Quarter from Administration and grading UI

**Files:**
- Modify: `src/pages/Administration/Administration.jsx`
- Modify: `src/pages/Grading/Grading.jsx`
- Modify: `src/components/Grading/GradingSheet.jsx`
- Modify: `src/components/Grading/GradebookActions.jsx`

**Interfaces:**
- The Grading Period form and table show no Quarter or term-order numeric field.
- The grading page orders and selects periods by API `term_order`; labels continue to show the period's name.

- [x] **Step 1: Remove the Quarter control and table column**; set the initial period name to Term 1 and rename active frontend field references to `term_order` without changing the visible term labels or export button behavior.
- [x] **Step 2: Run `npm run lint` and `npm run build`** and confirm the UI consumes the renamed API shape.
- [ ] **Step 3: Verify the Grading Period form/table in the running app** and confirm Quarter is absent and term options remain ordered correctly.

### Task 4: Verify the complete grading lifecycle

**Files:**
- Modify: remaining test fixtures and assertions in `backend/tests/` and `src/` that reference active quarter fields.

- [x] **Step 1: Update active fixtures and API assertions** to use `term_order`; leave historical JSON snapshots and legacy class keys unchanged.
- [x] **Step 2: Run focused backend tests** for academic structure, gradebook save/finalize, MAPEH, and single/combined XLSX exports.
- [ ] **Step 3: Run the full backend test suite and frontend lint/build**; report any pre-existing unrelated failures separately.
- [ ] **Step 4: Inspect migration metadata and the rendered Administration view** to confirm all four active database fields and the UI field/table label have been removed from the quarter naming.
