# DO 15, s. 2026 Gradebook Policies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all applicable existing and future Grade 7-12 gradebooks use the official assessment policy assigned to their class offering, with matching browser and XLSX grades and preserved raw scores.

**Architecture:** Reuse `SubjectTeachingAssignment` for class-offering classification and immutable `GradingPolicy` rows for saved policy versions. Resolve official profiles centrally; enforce them in gradebook writes and calculate through explicit examination and reporting modes. Align existing records through a reviewed, encrypted, audited transaction rather than a startup migration.

**Tech Stack:** Existing Python/FastAPI, SQLAlchemy, Pydantic, unittest, openpyxl, cryptography; React 18, existing form styles, native Node tests, Vite. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-19-do2026-grading-policy.md` (read in full before execution).

## Global Constraints

- The latest instruction supersedes the earlier new-gradebooks-only choice: include existing and future Grade 7-12 gradebooks, including Finalized and Locked records, for school years to which the order applies.
- Preserve every existing `StudentScore` row, including IDs, assessment-item IDs, numeric values, statuses, notes/reasons, actor fields, and timestamps; preserve every existing assessment maximum and student record.
- Never delete components or items during alignment.
- No real record is finalized by this operation.
- Gradebook -> XLSX is the direction of authority.
- No new dependencies.
- Admin and School Head retain read-only grade access. Existing Records Officer export, reopen, and adjustment approval permissions remain unchanged.
- The present request creates the spec and implementation plan; it does not apply an alignment.
- Preserve unrelated uncommitted work and stage only this feature's changes during execution.

## Review Focus

1. A new SHS elective or missing offering must require explicit classification instead of silently inheriting a generic policy (Tasks 2-3).
2. TE-only and no-exam groups must calculate/finalize without nonexistent STs or a hidden examination requirement; zero scores must count (Tasks 1, 3-4).
3. Grade 12 transition, year changes, and conversion boundaries must use explicit reporting modes in browser/backend/Excel, including groups without exams (Tasks 1, 4).
4. A saved Attendance component, ambiguous GMRC domain, or pending old criteria request must remain preserved without distorting official grades (Tasks 3, 5).
5. A stale migration manifest or mid-transaction failure must leave every raw score, maximum, policy, audit, and workflow row unchanged (Task 5).

---

## File map and execution preparation

Paths below are relative to the `EduScan` project root. Line anchors describe the inspected tree and may move; locate the named function before editing. This is one coupled grading subsystem, so keep a single plan with independently testable vertical tasks.

| Files | Responsibility |
|---|---|
| New `backend/app/services/do2026_policies.py` | Official catalog, policy resolution and managed-policy validation |
| Existing `backend/app/models.py`, `models_grading.py`, `migrations.py`, `schemas.py`, `schemas_grading.py` | Offering classification, explicit reporting mode and retained-assessment metadata |
| Existing `backend/app/main.py`, `services/grading.py`, `services/academic_context.py`, `services/template_policies.py` | Narrow authorization endpoints, authoritative gradebook creation/configuration/adjustments; remove managed-policy reliance on name/fallback inference |
| Existing `backend/app/services/grading_engine.py`, `src/services/gradingCalculations.js` | Examination and conversion modes with matched arithmetic |
| Existing `backend/app/services/reports.py`, `class_record_export.py`, `adaptive_class_record.py` | Policy-compatible templates, adaptive formulas/caches and three-term consistency |
| New `src/components/Grading/OfferingPolicyEditor.jsx`; existing `src/api/client.js`, `pages/Administration/Administration.jsx`, `pages/Grading/Grading.jsx`, `components/Grading/AssessmentConfig.jsx`, `AdjustmentRequestsModal.jsx`, `GradingSheet.jsx` | Restricted group selection, visible policy/read-only weights and retained-data disclosure |
| New `backend/app/services/do2026_alignment.py`, `backend/tools/align_do2026_policies.py` | Pure dry-run planning and transactional application/recovery |
| New `backend/tests/test_do2026_policies.py`, `test_do2026_offerings.py`, `test_do2026_alignment.py`; existing grading/API/export/browser-calculation tests | Isolated catalog, permissions, calculation, retention, migration and export evidence |
| New `docs/DO2026_GRADING_ROLLOUT.md` | Classification, dry-run/recovery and operator checklist |

Before Task 1: invoke the execution skill chosen by the user and `using-git-worktrees` if execution needs isolation. Inspect `git status` and the current diff: many grading/export/UI files already contain unrelated uncommitted work. Establish isolated regression baselines; do not move, overwrite, or commit that work. Run tests in separate processes because existing modules set database environment variables at import time. Backend commands use `backend/.venv/Scripts/python.exe`; do not start the real application as a test fixture.

### Task 1: Official policy catalog and calculation modes

**Files:**
- Create: `backend/app/services/do2026_policies.py`, `backend/tests/test_do2026_policies.py`
- Modify: `backend/app/services/grading_engine.py:103-180,354-432`, `src/services/gradingCalculations.js:41-83,169-end`
- Test: `backend/tests/test_grading_engine.py`, `src/services/gradingCalculations.test.js`

**Interfaces:**
- Produces: `resolve_assessment_profile(school_year_start: int, grade: int, curriculum_profile: str, assessment_group: str) -> dict`. Return keys: `assessment_group`, `curriculum_profile`, `version`, `component_definitions`, `reporting_method`, `transmutation_table`, `passing_grade`, `rounding_decimal_places`, `rounding_final_decimal_places`, `rounding_method`. Definitions contain stable `key`, `name`, `component_type`, `weight`, `max_items`, and optional `exam_weights`.
- Produces: `is_managed_policy(policy: GradingPolicy | None) -> bool` by the managed version prefix; use `DO015-2026-v1` initially.
- Extends: `calculate_component_percentage(scores, items, component_type="", exam_weights: dict[str, float] | None = None) -> dict`; JS `calculateComponentPercentage(scores, items, componentType = '', examWeights = null)`.
- Extends: `calculate_student_grade(..., reporting_method: str = "legacy") -> dict`; JS `calculateStudentGrade({...existingOptions, reportingMethod = 'legacy', roundingFinalDecimalPlaces = 0})`. Components carry `exam_weights`; legacy default callers retain current behavior.

- [ ] **Step 1: Add failing catalog/calculation tests.** Assert all 13 exact group IDs/weights in the spec, all 41 adjusted-table bands, and all legal grade/curriculum/year combinations. Reject Grade 11 `legacy_shs`, Grade 12 legacy after SY 2026-2027, a JHS group in Grade 11, and unknown group/year inputs. Mirror these representative expectations in JS without importing the implementation's policy values as the expected results:

```python
# Each test uses independent score/item fixtures and the official values in the spec.
assert exam_percentage((15, 18, 35), (20, 20, 40), {'ST1': 30, 'ST2': 30, 'TE': 40}) == 84.5
assert exam_percentage((35,), (40,), {'TE': 100}) == 87.5
assert reported(69.99, 'adjusted_2026') == 74
assert reported(70, 'adjusted_2026') == 75
assert reported(71.175, 'adjusted_2026') == 75
assert reported(71.18, 'adjusted_2026') == 76
assert reported(80, 'adjusted_2026') == 83
assert reported(74.49, 'direct') == 74
assert reported(74.5, 'direct') == 75
```

`exam_percentage` and `reported` above are fixture helpers within the test modules that call the published engine interfaces; define them in the same failing-test step. Include no-exam WW/PT (80% and 90% at 40/60 -> IG 86 -> TG 88 in SY 2026-2027), TE-only zero, unequal maxima, blank inputs, and direct-mode `None` table not triggering legacy fallback. Keep the existing normalized draft preview expectation.

- [ ] **Step 2: Run the focused tests and confirm the new assertions fail.** Run `backend/.venv/Scripts/python.exe -m unittest discover -s backend/tests -p test_do2026_policies.py -v` and `node --test src/services/gradingCalculations.test.js`. Expected: newly introduced profile/mode cases fail before implementation; record existing failures separately.
- [ ] **Step 3: Implement the catalog and the exact engine/JS signatures above.** Transcribe Annex D Table 4 from the official pages listed in the spec, preserve the published bounds, and implement lower-bound lookup for adjusted mode independent of component type. Standard exam weights are `{ST1:30,ST2:30,TE:40}`, field-experience weights `{TE:100}`, and no-exam profiles omit the exam component. Direct mode rounds the raw IG using final-grade rounding and never calls legacy conversion. Retain current class-wide completeness and draft saving rules.
- [ ] **Step 4: Run both focused commands plus `backend/.venv/Scripts/python.exe -m unittest discover -s backend/tests -p test_grading_engine.py -v`.** Expected: PASS, including existing legacy behavior and all boundary/mode cases.
- [ ] **Step 5: Commit only Task 1 changes.** Suggested message: `feat: define official DO 2026 grading profiles and calculation modes`.

### Task 2: Assign a policy group to each class offering

**Files:**
- Modify: `backend/app/models.py:161-183`, `models_grading.py:17-57`, `migrations.py`, `schemas.py:568-573`, `main.py:1524-1585,1708-1785`, `src/api/client.js`, `src/pages/Administration/Administration.jsx:440-485,710-730`, `src/pages/Grading/Grading.jsx`
- Create: `src/components/Grading/OfferingPolicyEditor.jsx`, `backend/tests/test_do2026_offerings.py`

**Interfaces:**
- Consumes: Task 1 `resolve_assessment_profile(...)`.
- Produces: nullable `SubjectTeachingAssignment.curriculum_profile: String(30)` / `assessment_group: String(80)`; `GradingPolicy.reporting_method: String(30)` with non-null `legacy` default and existing-row backfill.
- Produces: Pydantic `OfferingAssessmentPolicyPayload(curriculum_profile: str, assessment_group: str, reason: str)` with reason length 8-2000; `GET /api/grading/assessment-groups?school_year_id=int&grade_level_id=int&curriculum_profile=str`; `PUT /api/class-offerings/{assignment_id}/assessment-policy` (Admin/Records Officer only). Return `{offering_id, curriculum_profile, assessment_group, policy_version, requires_alignment}`. GET returns `{groups: [{id,label,weights,exam_weights}], reporting_method}` after validating context.
- Extends: `SubjectTeachingAssignmentPayload` with nullable curriculum/group for the existing Admin-only assignment creation; include both and `policy_version` in existing `academic_structure` assignment output. Existing unclassified rows remain NULL.
- Produces: `OfferingPolicyEditor({offering, groups, onSave, disabled})` used by Admin in teaching assignments and Records Officer within Grading. Client methods: `getAssessmentGroups(params)` and `saveOfferingAssessmentPolicy(assignmentId, payload)`.

- [ ] **Step 1: Write failing role/schema/migration tests.** In an isolated DB, upgrade a legacy row with nullable defaults; existing assignment identities/teacher IDs survive. Admin and Records Officer can assign valid groups; Teacher, School Head, scanner and unauthenticated calls fail. Test invalid grade/group and conflicting school-year dates. Confirm two offerings of the same named subject can use different valid SHS groups. An existing populated offering returns `requires_alignment=True` while its book's saved policy/score rows stay unchanged.
- [ ] **Step 2: Run `backend/.venv/Scripts/python.exe -m unittest discover -s backend/tests -p test_do2026_offerings.py -v`.** Expected: failures for missing fields/endpoints/permissions.
- [ ] **Step 3: Implement schema upgrade, endpoints and shared selector.** Reuse `SubjectTeachingAssignment`, existing `add_audit`, reference checks and form controls. Keep teacher re-assignment Admin-only; Records Officer receives only assessment-policy authority. Use `SchoolYear.starts_on` to determine policy year and reject inconsistent labels. Offer known-subject suggestions without saving them automatically. The list must state the WW/PT/EX percentages and TE-only/no-exam behavior in plain language; teacher receives read-only policy details from the gradebook response.
- [ ] **Step 4: Run the focused test and `npm run verify`.** Expected: PASS. Check selector by keyboard, mobile width, and role visibility using isolated UI fixtures or authorized live read-only sessions; save no real offering assignment during verification.
- [ ] **Step 5: Commit only Task 2 changes.** Suggested message: `feat: classify class offerings with authorized DO assessment groups`.

### Task 3: Enforce the saved policy on every gradebook write path

**Files:**
- Modify: `backend/app/models_grading.py`, `migrations.py`, `schemas_grading.py`, `services/do2026_policies.py`, `services/grading.py:90-110,285-410,493-680,683-810,1070-1185`, `services/template_policies.py`, `main.py:2530-2665,2770-2810,2890-2950`, `src/pages/Grading/Grading.jsx`, `src/components/Grading/AssessmentConfig.jsx`, `AdjustmentRequestsModal.jsx`, `GradingSheet.jsx`
- Test: `backend/tests/test_do2026_offerings.py`, `backend/tests/test_grading_regressions.py`, `backend/tests/test_grading_api.py`

**Interfaces:**
- Consumes: Task 1 profile and Task 2 offering classification.
- Produces: `ensure_do_policy(db: Session, school_year: SchoolYear, profile: dict, actor: User) -> GradingPolicy` (flushes, never commits); immutable managed policy rows identified by `(school_year, version, subject_category)` under the existing year-row lock.
- Produces: component `assessment_key: String(40) | None`, component/item `included_in_grading: Boolean` with non-null server/default `True`; criteria request `policy_id_at_request: int | None` as a nullable `grading_policies.id` foreign key. Additive migrations retain every old row and legacy defaults.
- Produces: `validate_managed_components(book: Gradebook, components: list[dict]) -> None`, raising `ValueError` for mismatched official keys/weights/exam roles; `gradebook_policy_compliance(book: Gradebook) -> dict` returning `{compliant: bool, issues: list[str]}`.
- Extends: `get_gradebook_full` policy object with `assessment_group`, `curriculum_profile`, `version`, `reporting_method`, `compliance`; active component objects with `assessment_key` / `exam_weights`, and top-level `retained_assessments: list[dict]` for excluded components/items plus their existing authorized score data.

- [ ] **Step 1: Write failing creation/enforcement tests.** A new Mathematics Grade 7 book resolves `20/50/30`; TLE resolves `20/60/20`; a missing offering/group blocks creation with a helpful message. Reject an injected `grading_policy_id`, arbitrary 100%-total weights, extra Attendance contribution, renamed exam roles, direct policy edits and stale criteria approval. Preserve score adjustments, variable WW/PT activity counts/maxima and draft saves. Test no-exam finalization needs only WW/PT, TE-only needs only TE, and zero remains a scored entry. Test excluded rows remain readable but never affect totals, completeness, validation or export input.
- [ ] **Step 2: Run the focused offering test and isolated `test_grading_regressions.py` / `test_grading_api.py` processes.** Expected: the new assertions fail on existing fallback/configuration paths. Record existing failures before edits.
- [ ] **Step 3: Implement the interfaces and all callers.** Grep every caller of `create_or_get_gradebook`, `update_gradebook_components`, `policy_transmutation_table`, criteria request/review, legacy component write/finalize endpoints, and `calculate_student_grade`. Managed books must always resolve the offering policy, with no `General` fallback or teacher-supplied override. Reject legacy endpoint writes that could bypass managed-book rules. Freeze managed policy rows once referenced. Add the compliance check to finalize and official export preconditions; allow draft score saving while a populated book awaits alignment. Capture policy identity in criteria requests and refuse stale approvals without deleting requests. Pass explicit mode and portions to backend and JS callers.
- [ ] **Step 4: Restrict the existing UI controls.** Keep activity maxima and eligible activity slots editable in open books, show policy version/group and read-only weights/examination roles, preserve score adjustment actions, and explain that a wrong assessment group is corrected by Admin/Records Officer. Provide a collapsed read-only retained-assessments view. Preserve existing historical pre-2026 custom-policy behavior.
- [ ] **Step 5: Run the focused backend tests separately, `node --test src/services/gradingCalculations.test.js`, and `npm run verify`.** Expected: PASS with unchanged auth/score-edit restrictions and no deleted retained data.
- [ ] **Step 6: Commit only Task 3 changes.** Suggested message: `fix: enforce offering policies across gradebook configuration and adjustments`.

### Task 4: Match every XLSX export to the applied gradebook policy

**Files:**
- Modify: `backend/app/services/reports.py:374-400`, `class_record_export.py:18-42,65-105`, `adaptive_class_record.py:32-205,260-end`
- Test: `backend/tests/test_adaptive_class_record.py`, `backend/tests/test_grading_regressions.py`, `backend/tests/test_do2026_offerings.py`

**Interfaces:**
- Consumes: Task 3 full-gradebook response and Task 1 explicit exam/reporting modes.
- Preserves: `generate_gradebook_report_xlsx(..., all_terms: bool = False) -> Path` and existing per-term/three-term routes and role restrictions.
- Produces: policy metadata cells in adaptive XLSX and compatibility checks for fixed templates; no new export-selection API.

- [ ] **Step 1: Write failing export parity tests using synthetic complete books.** Cover every assessment group, Grades 7-12 and SY 2026-2027/2027-2028. Independently compute expected WS/IG/TG for unequal maxima, zero, TE-only, no-exam, GMRC domain weights and the 70/71.18 conversion boundaries; compare every learner against `get_gradebook_full`, raw worksheet formulas, and `data_only=True` results. Include one official sample: WW 74/85, PT 86/100, EX 15/20,18/20,35/40 -> raw IG approximately 85.7617647059 -> displayed IG 85.76 -> TG 88. Retain the sample's published 85.8/88 as rounded presentation evidence rather than changing the application's existing display precision.
- [ ] **Step 2: Add three-term and permissions assertions.** Export three complete matching-policy terms with different activity maxima, and still export each separately. A missing/incomplete term or different group/reporting mode is rejected; Admin cannot acquire Records Officer export rights. Source-score fingerprints remain identical before/after export. Verify all existing school metadata and combined Music/Arts + PE/Health output.
- [ ] **Step 3: Run export tests in separate processes and confirm the new cases fail.** Commands: `backend/.venv/Scripts/python.exe -m unittest discover -s backend/tests -p test_adaptive_class_record.py -v` and the existing regression module. Expected: missing TE-only/direct-mode/formula metadata support fails before edits.
- [ ] **Step 4: Implement policy-compatible template routing and adaptive formulas/caches.** Remove the managed TLE/core filename assumption; choose based on the saved profile. A template may render a record only if exact weights, examination portions, conversion and rounding match; otherwise call the existing adaptive exporter. Direct mode must write direct-grade formulas, TE-only must use TE 100%, no-exam must require no exam cells, and adjusted lookup must work without a `Term Examinations` component. Reuse school-head and school-detail handling. Check all-term offering/group/mode consistency before writing any report file.
- [ ] **Step 5: Run focused tests and independently recalculate representative XLSX files with installed Excel or LibreOffice.** Include one standard, one TE-only, one no-exam, one GMRC, one legacy Grade 12, one direct-mode and one three-term workbook. Reopen the recalculated files and compare every learner's WS/IG/TG to the independent oracle and gradebook. If no external calculator is installed, report that limitation and keep production rollout pending rather than claiming formula execution was verified.
- [ ] **Step 6: Commit only Task 4 changes.** Suggested message: `fix: export saved DO assessment and conversion rules consistently`.

### Task 5: Audited alignment of existing open and finalized records

**Files:**
- Create: `backend/app/services/do2026_alignment.py`, `backend/tools/align_do2026_policies.py`, `backend/tests/test_do2026_alignment.py`, `docs/DO2026_GRADING_ROLLOUT.md`
- Reuse/modify only as necessary: `backend/tools/align_template_policies.py` fingerprint/encrypted-snapshot pattern, `services/grading.py` audit/reopen helper, Task 3 retained-assessment flags

**Interfaces:**
- Consumes: Tasks 1-4 policy resolution, saved policy, retained flags, calculation and export parity.
- Produces: `build_alignment_plan(db: Session, school_year_ids: list[int], mappings: dict) -> dict`, a no-write manifest with `version`, `source_fingerprint`, `school_year_ids`, `books`, `blockers`, and `coverage`. Each book reports IDs, old/new policy, component/item mapping, old/new learner grades/completeness and workflow change.
- Produces: `apply_alignment_plan(db: Session, plan: dict, actor: User, reason: str) -> dict`; only an active Records Officer can apply, using existing audited workflow authority; caller owns the single transaction commit.
- Produces: CLI default dry-run `--school-year-id <id>` (repeatable), `--mappings <local.json>` (optional), `--output <local-plan.json>`; apply requires `--apply --plan <local-plan.json> --actor-user-id <id> --reason <text>`. Recovery is `--restore <encrypted-backup> --actor-user-id <id> --reason <text>` with post-alignment fingerprint checks.

- [ ] **Step 1: Write failing dry-run/mapping tests.** Fixture books span Grades 7-12, all statuses, a historical school year, missing/unclassified offerings, extra Attendance component, ambiguous GMRC domains, a single legacy QA item, TE-only and no-exam profiles. Assert dry-run commits no row, exposes every unresolved case, maps existing QA ID to TE, creates no invented score, retains previous noncontributing components/items and maxima, and predicts Draft reopening only for closed records that become incomplete.
- [ ] **Step 2: Write failing transaction/integrity/recovery tests.** Snapshot all columns of StudentScore, all existing activity maxima and person/student rows. Assert exact equality after successful alignment; one audit per changed book; correct old/new grades and statuses; an identical second run does nothing. A changed score after dry-run, concurrent offering change, pending stale criteria, ambiguous mapping or injected exception rolls back all touched rows/audits. Recovery preserves score rows and refuses to overwrite subsequent edits. Test encrypted backup round trip using a temporary test key, never the live key.
- [ ] **Step 3: Run `backend/.venv/Scripts/python.exe -m unittest discover -s backend/tests -p test_do2026_alignment.py -v`.** Expected: new interfaces absent or new mapping/transaction assertions fail.
- [ ] **Step 4: Implement the plan/apply/restore interfaces.** Reuse the existing encrypted backup and fingerprint approach without importing a command-line script into application services. Lock offerings/gradebooks and coordinate with existing score-update locks; recheck the manifest fingerprint inside the transaction. Apply only resolved ID mappings, manage retained flags and immutable policy references, add required blank exam slots, and calculate all learner deltas. Preserve closed state only when the resulting record remains complete; otherwise use the existing reopen semantics with the recorded Records Officer reason and old-state audit. Audit before/after metadata and policy/version. Never finalize a real book, change raw scores/maxima, or clear pending requests.
- [ ] **Step 5: Run alignment tests plus separate offering/regression/export tests.** Expected: PASS, exact score/maxima equality and complete rollback proof. Document commands, mapping fields, blockers, encryption/recovery location, affected-grade review and the fact that pre-2026 records retain applicable historical policies. No live `--apply` is run as part of this task.
- [ ] **Step 6: Commit only Task 5 changes.** Suggested message: `feat: add reversible audited DO policy alignment for existing gradebooks`.

### Task 6: Integrated verification and concrete rollout report

**Files:**
- Modify: `docs/DO2026_GRADING_ROLLOUT.md` with actual verification results and limitations
- Local ignored output only: `work/do2026-policy/` (dry-run evidence and synthetic workbooks; never commit personal scores, database snapshots or keys)

**Interfaces:**
- Consumes: all previous tasks; no new production interface.
- Produces: a reviewable dry-run impact report and an explicit list of compliant/unclassified/blocked gradebooks before real application.

- [ ] **Step 1: Run each new backend module, the grading engine/API/regression/adaptive-export modules, `test_admin_reporting_permissions.py`, `test_reporting_reliability.py`, and `test_smoke.py` in its own process.** Compare to recorded baseline; include relevant full-suite failures rather than hiding them. Run `node --test src/services/gradingCalculations.test.js` and `npm run verify`. Expected: no new failures; smoke coverage confirms attendance, enrollment, SF2, school-head visibility and existing permission boundaries.
- [ ] **Step 2: Check authenticated UI roles using isolated fixtures or the user's authorized accounts without saving real changes.** Admin/Records Officer see assessment-group controls; Teacher sees correct read-only policy and retains score entry, Assessment Setup maxima and score requests; School Head remains read-only. Inspect desktop/mobile, labels, keyboard focus, unknown-group explanation, retained-data disclosure and conversion/group details. Do not edit real scores, generate attendance/SMS or finalize records.
- [ ] **Step 3: Generate only a read-only populated alignment plan for the real applicable school year(s).** Store sensitive output locally under ignored work/data paths; summarize counts and blockers to the user, not raw student scores in Git. If SJNHS curriculum/group classifications are unavailable, list each offering needing the Admin/Records Officer decision and do not guess. All targeted records must be compliant or explicitly blocked, with no silent skips.
- [ ] **Step 4: Self-review the entire diff against the spec and run the chosen execution workflow's final independent review.** Pay particular attention to the five Review Focus cases, DB/PostgreSQL row-lock behavior, template constants, decimal boundaries and encrypted restoration. Stage only reviewed feature changes. Suggested final message: `docs: record DO 2026 grading verification and rollout impact`.
- [ ] **Step 5: Present the exact impact report and apply command for review before a real alignment.** Explain counts of changed grades and records reopening as incomplete. Keep rollout pending if classifications, external spreadsheet recalculation or recovery verification are unresolved. Applying the database change is a separately reviewed final operational step; no permission is inferred from elapsed time or a successful isolated test.

## Plan self-review record

- Coverage: official matrices/GMRC domains and year rules -> Task 1; offering authority -> Task 2; every write path, retained data and stale criteria -> Task 3; all export paths -> Task 4; all existing statuses, preservation and recovery -> Task 5; live/role/regression/rollout evidence -> Task 6.
- Interface consistency: `assessment_group`, `curriculum_profile`, `reporting_method`, `exam_weights`, `assessment_key`, `included_in_grading` and `policy_id_at_request` are named consistently across tasks. Policy definitions use the existing JSON structure; no parallel generic grading framework is introduced.
- Five Review Focus cases each have explicit failing tests in their owning tasks. No implementation, real migration, real finalization or database write was performed while writing this plan.
- Remaining operational input: SJNHS's confirmed SHS curriculum/group classifications for each offering. The software can be implemented and tested without guessing those choices; real alignment cannot report full compliance until they are supplied.
