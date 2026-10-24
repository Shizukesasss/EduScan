# Ten-record Pagination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show ten records per page without losing selections, pending edits, totals or export data.

**Architecture:** Share pagination calculation and accessible controls. Give each list independent page state; retain complete collections in existing owners and slice only for rendering.

**Tech Stack:** Existing React 18, JavaScript, CSS and Node built-in tests; no new dependencies.

**Spec:** ../specs/2026-10-24-pagination-design.md

## Global Constraints
- Exactly 10 records per page.
- Preserve records, permissions, grading calculations and full export scope.
- Preserve section selections and unsaved scores across pages.
- No live score changes, real finalizations or database migrations during verification.
- Do not commit unrelated work; obtain user authorization before committing.

## Review Focus
- Search must find off-page records (Task 1/2).
- Removing the last row on a page must clamp the page (Task 1/2).
- Select all must include eligible off-page sections (Task 2).
- Scores must survive page switches and keyboard navigation (Task 3).
- API response caps must not masquerade as complete totals (Task 2).

### Task 1: Shared pagination calculation and controls
**Files:** Create `src/services/pagination.js`, `src/services/pagination.test.js`, `src/hooks/usePagination.js`, `src/components/Common/Pagination.jsx`; modify `src/styles/index.css`.

**Interfaces:** `paginate(items, page, pageSize = 10)` returns `{items,page,pageCount,total,start,end}`. `usePagination(items, resetKey)` adds `setPage`. `Pagination({page,pageCount,total,start,end,onPageChange,label})` shows controls only above ten records.

- [ ] Write failing Node tests for 0/10/11/21 records, page bounds and immutable input. Page 3 of 21 must contain only record 21.
- [ ] Run `node --test src/services/pagination.test.js`; confirm failure before implementation.
- [ ] Implement slicing, stable context reset/clamping and accessible Previous/Next plus bounded numbered pages. Include current-page indication and “1–10 of 83 records”. Avoid automatic whole-page scrolling.
- [ ] Rerun tests; verify responsive controls and keyboard focus.

### Task 2: Growing record lists and section selection
**Files:** Modify growing lists in `src/pages/Administration/Administration.jsx`, `src/pages/Oversight/Oversight.jsx`, `src/pages/Attendance/Attendance.jsx`, `src/pages/Reports/Reports.jsx`, `src/pages/Setup/SystemSetup.jsx`, `src/pages/Dashboard/Dashboard.jsx`, `src/pages/Teacher/MyAdvisory.jsx`, `src/pages/Teacher/MySchedules.jsx`, `src/pages/Teacher/TruancyInterventions.jsx`, `src/components/Teacher/SectionAttendance.jsx`, `src/components/Teacher/ReleasedSF2Reports.jsx`, `src/components/Setup/ClassScheduleManager.jsx`, `src/components/Setup/PersonnelScheduleManager.jsx`, `src/components/Setup/BiometricEnrollmentManager.jsx`, `src/components/Setup/DemoTeacherSetup.jsx`, `src/components/Grading/AuditHistory.jsx`, `src/components/Grading/GlobalAdjustmentsTab.jsx`, `src/components/Grading/AdjustmentRequestsModal.jsx`, and gradebook record lists in `src/pages/Grading/Grading.jsx`.

**Consumes:** Task 1 hook and controls. **Produces:** Independent paged rendering, leaving source collections intact.

- [ ] Inventory every dynamic list in these files, its filters and API source. Exclude static reference/calculation tables. Record API caps; use existing backend paging if available or label counts as loaded records when incomplete. Do not invent total counts.
- [ ] Add assertions to `pagination.test.js`: filtering/sorting precedes slicing; last-row removal clamps; separate page states do not interfere; selected IDs survive paging and Select all covers the entire eligible collection.
- [ ] Wire hooks in stable component order, outside conditional renders. Reset keys use stable school-year/section/date/search/filter values, not object identity. Keep forms and selected IDs outside page slices.
- [ ] Page SectionAssignmentPicker cards while preserving total selected count and existing Select all/Clear behavior.
- [ ] Verify row actions, edits and searches with isolated fixtures; confirm no off-page records disappear from source state.

### Task 3: Gradebook learner paging
**Files:** Modify `src/components/Grading/GradingSheet.jsx`; create `src/services/gradebookPagination.test.js` if extracted domain logic is necessary.

**Consumes:** Task 1 pagination. **Produces:** Ten visible learners with full-roster calculations and score state.

- [ ] Inspect groupedStudents, displayNum, navIdx, score-state ownership and dirty tracking. Add failing checks for filtering then paging, global numbering, male/female boundary and cross-page pending updates.
- [ ] Slice the filtered ordered learner collection before rebuilding visible groups. Keep all score state, saves, totals, validation and exports bound to the complete roster.
- [ ] Keep score keyboard navigation within visible inputs. Component-tab switches preserve learner page; gradebook context changes reset it.
- [ ] Verify teacher editable and administrator/principal/records-officer read-only variants without saving real scores.

### Task 4: Verification and delivery
- [ ] Run `node --test src/services/*.test.js` and `npm run verify`; fix relevant regressions.
- [ ] In the authenticated built-in browser, verify recognition reviews, administration lists, section picker, attendance, reports and class records using more than ten fixture rows. Check empty results, page boundaries, filters, narrow viewport and keyboard focus. Do not resolve real reviews or save real records.
- [ ] Using isolated backend fixtures, prove exports include off-page learners and score updates include edits from multiple pages. Confirm pagination itself sends no mutation requests.
- [ ] Run `git diff --check` and inspect every slice to ensure it cannot restrict exports, saves or validation. Report covered screens and exclusions.

## Self-review
All approved behaviors map to tasks. Stable reset keys, API caps, score navigation and cross-page state are explicit checks. Product implementation has not started.
