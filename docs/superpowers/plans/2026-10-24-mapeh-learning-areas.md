# MAPEH Learning Areas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide one MAPEH workspace with independent Music and Arts and PE and Health gradebooks for Terms1–3, preserving old combined records and matching the supplied workbook.

**Architecture:** Keep the parent MAPEH subject/assignment. Add explicit area metadata and a legacy read-only flag to gradebooks; expand uniqueness to include area. Reuse the existing grading engine, workflow, template writer and assignment authorization. Live activation is a separate reviewed operation, never an automatic startup migration.

**Tech Stack:** Existing SQLAlchemy, PostgreSQL/Supabase, SQLite fixtures, FastAPI, React, openpyxl read-only inspection and ZIP/XML template writer. No new dependencies.

**Spec:** ../specs/2026-10-24-mapeh-learning-areas-design.md

## Global Constraints
- WW20%, PT60%, Exams20%; ST1/ST2/TE30/30/40 in both new areas.
- Keep old IDs, scores, items, policies, workflow statuses and audits unchanged; only the approved legacy marker may be added at activation.
- New area records start empty; never duplicate or split old scores.
- Preserve existing role permissions and unrelated subjects.
- Do not finalize real gradebooks or run live schema/activation changes before showing impact and obtaining approval.
- No commits of unrelated work or live data; user approval required before commit/push.

## Review Focus
- Simultaneous area initialization must not create duplicate contexts (Task1/2).
- Direct old API/class-key mutations must not bypass legacy protection (Task2).
- Switching area with pending edits must not save into the other area (Task3).
- One completed area or partial-term export must never produce a combined/annual grade (Task4).
- Reassigned teachers and duplicate historical records must not mix in exports (Task2/4).

### Task 1: Area-aware schema and isolated migration
**Files:** `backend/app/models_grading.py`, `backend/app/schemas_grading.py`, `backend/app/migrations.py`; create `backend/tests/test_mapeh_learning_areas.py`.
**Interfaces:** Gradebook fields `learning_area` (non-null string: empty for ordinary/old combined, `music_arts`, `pe_health` for new MAPEH) and `is_legacy_readonly` (boolean, default false). GradebookCreate accepts validated `learning_area`; summaries/full payloads expose both fields.
- [ ] Add failing isolated schema tests: ordinary context unchanged; two MAPEH areas coexist; same area duplicate rejected; null/unknown areas rejected; no old score/item/status changes after upgrade.
- [ ] Update context uniqueness to `(school_year_id,grading_period_id,grade_level_id,section_id,subject_id,learning_area)` and area suffixes on class_key. Handle PostgreSQL constraint replacement and SQLite fixture schema; inventory old constraints before changing them.
- [ ] Implement a separately invokable schema-upgrade step. Do not add a startup path that executes live DDL before approval. Audit existing startup run_migrations behavior and gate this upgrade until approved.
- [ ] Run `.venv/Scripts/python.exe -m unittest tests.test_mapeh_learning_areas -v` against isolated data; verify repeat upgrade is idempotent and rollback restores old uniqueness only when no area records exist.

### Task 2: Area initialization, immutable legacy records and authorization
**Files:** `backend/app/services/grading.py`, `backend/app/main.py`; create `backend/app/services/mapeh_learning_areas.py`; extend Task1 tests.
**Interfaces:** `ensure_mapeh_area_gradebook(db, context, area, user)` delegates to area-aware create_or_get_gradebook; `assert_gradebook_writable(book)` rejects legacy writes with HTTP409 and a plain-language explanation. `preview_mapeh_activation(db)` returns proposed legacy record IDs/context/status, existing grades, preserved score/item counts, and planned empty area contexts; `apply_mapeh_activation(db, expected_preview_hash, actor)` validates the reviewed preview and applies only approved markers/empty records transactionally.
- [ ] Write failing tests for assigned-teacher access to both areas, wrong section/year/teacher denial, ordinary subjects rejecting area values, blank score initialization, repeated/concurrent initialization and preserved parent assignment.
- [ ] Reuse existing template-backed MAPEH policy setup and snapshot20/60/20 plus named ST1/ST2/TE. Never update a shared policy used by old books. Require template transmutation parity; preserve all existing score validation.
- [ ] Enforce legacy protection in every write: save scores, assessment edits, submit/finalize/lock/reopen, score/criteria requests and approvals, deletes, and legacy class-key compatibility routes. Trace every caller of `_gradebook_for_update` and direct ORM updates. Read-only legacy exports retain existing permissions and cannot participate in new area combinations.
- [ ] Test legacy rejection through both service and API paths, including existing pending adjustment approvals; fingerprint legacy scores, items, policy and status before/after every attempt.
- [ ] Build preview/apply with a stale-preview guard, audit trail and rollback-on-error. Test dry-run does no writes, apply is idempotent, a changed preview blocks apply, and no grade changes occur. Do not execute apply on live data.

### Task 3: Single MAPEH workspace and area navigation
**Files:** `src/pages/Grading/Grading.jsx`, `src/components/Grading/GradingSheet.jsx`, `src/components/Grading/GradebookActions.jsx`, `src/api/client.js` only if required by current API wrappers; create `src/services/mapehLearningAreas.js` and `.test.js`; modify `src/styles/index.css` for area controls.
**Interfaces:** MAPEH selection carries parent subject ID plus `learning_area`; ordinary subject selection carries empty area. Area context is included in request identity, stale-response handling and dirty-edit checks.
- [ ] Add failing Node tests for two distinct context keys, area switch dirty handling, out-of-order responses and legacy read-only selection.
- [ ] Add Music and Arts / PE and Health controls inside MAPEH and a separate Legacy MAPEH history view. Preserve continuous male/female roster, component tabs and current role restrictions. Hide/disable all mutation controls for legacy records while preserving server enforcement.
- [ ] Use existing unsaved-change safeguard before changing area. Do not save pending edits or reload another area silently. Area-policy display is locked to the saved approved policy.
- [ ] Verify fresh empty area initialization and existing legacy view in an isolated browser fixture; no real score saves or finalizations. Run `node --test src/services/*.test.js` and `npm run verify`.

### Task 4: Exact supplied template and combined grades
**Files:** `backend/app/services/class_record_export.py`, `backend/app/services/reports.py`, `backend/app/services/adaptive_class_record.py` only where area routing shares logic; create `backend/tests/test_mapeh_area_exports.py`; extend export-term-scope tests.
**Interfaces:** Explicit `music_arts` maps to `TERM n M and A`; `pe_health` maps to `TERM n PE and H`. Select siblings by parent subject/context/area, never subject-name inference. Legacy exports remain isolated from new exports.
- [ ] Write failing tests for both areas in each term, two-term and all-three exports, wrong teacher/context exclusion, duplicate record rejection and missing/incomplete area blocking.
- [ ] Require both complete finalized/locked area records for every requested term. Preserve per-term/combined role checks and button placement. Fill two/four/six term sheets according to scope and leave excluded terms blank.
- [ ] Preserve original workbook styles, merges, page setup, margins and school metadata. Reuse ST1/ST2/TE formulas and template conversion rules for each area. Cache area, combined term and annual formula results only after independent comparison with gradebook calculations.
- [ ] Compute combined term as ROUND(AVERAGE(two area term grades),0), blank if either missing; annual is rounded mean of all three combined terms, blank if any missing/excluded. Ensure FINAL GRADES guards match in website, formulas and cached values.
- [ ] Test Grade7/8/9/10, varied maxima, zeros, perfect scores, cutoff rounding, incomplete pairs and all five export scopes. Compare every student's raw inputs, initial/term/combined/final grades and retained formulas. Assert source-copy data unchanged after export.

### Task 5: Verification, impact report and live approval boundary
**Files:** Create `backend/work/verify_mapeh_area_exports.py` using the existing isolated-copy verification pattern; output an impact report under `backend/work/mapeh-area-preview/`. Do not include secrets or face data.
- [ ] Read live data with a read-only transaction into an in-memory database. Fingerprint protected live tables before/after. Apply schema/activation only to the isolated copy; synthetic scores remain memory-only and clearly labeled.
- [ ] Run `.venv/Scripts/python.exe -m unittest tests.test_mapeh_learning_areas tests.test_mapeh_area_exports tests.test_export_term_scope tests.test_legacy_jhs_export tests.test_jhs_template_routing -v`, plus existing JHS parity tests. Run frontend Node checks, `npm run verify` and `git diff --check`; inspect every result before reporting success.
- [ ] Verify authorized browser roles and area-switch unsaved edits when browser access is available. Report desktop Excel recalculation separately; cached values and formulas alone do not prove native recalculation.
- [ ] Present exact affected legacy records, preserved grades/counts and planned empty area records, with test evidence. Stop before live schema/activation until user approves this concrete impact report. No real finalization.

## Self-review
All approved design requirements map to schema, authorization, UI, exports or impact verification tasks. Explicit metadata eliminates name-based area ambiguity. The expanded uniqueness constraint and startup migration gate are essential: do not activate UI against an unupgraded live schema. Legacy scores remain independent of the new area records. No product code or live changes are part of writing this plan.
