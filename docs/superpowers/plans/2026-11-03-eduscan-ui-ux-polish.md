# EduScan Interface Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every existing EduScan desktop route, role variant, dialog, form, and shared component calmer, clearer, and more consistent without changing product behavior.

**Architecture:** Refine the active global stylesheet and shared shell/components first, then apply the shared patterns to operational, grading/reporting, setup/administration, scanner, and teacher surfaces. Keep existing React routes, role gates, data, and actions intact; use CSS and presentational markup changes, adding only the missing accessibility and status feedback described by the spec.

**Tech Stack:** React 18, React Router, Vite, Lucide, plain CSS, Oxlint, Node.js built-in test runner.

**Spec:** `docs/superpowers/specs/2026-11-03-eduscan-ui-ux-polish-design.md`

## Global Constraints

- No route, permission, feature, business-rule, data, or API changes.
- No mobile/tablet layouts, breakpoints, or touch-specific behavior. Existing breakpoints are not expanded as part of this work.
- No new dark theme; the repository currently defines only a light theme.
- No replacement of the school logo, brand palette, fonts, or school terminology.
- No dependency additions unless implementation proves an existing capability cannot meet the requirement; that would require a revised design decision first.
- Do not hide school-critical data behind extra clicks solely to make screens appear sparse.
- Do not remove a functional action or unique status/data point. If implementation uncovers a candidate functional removal, stop and ask first.
- Do not alter report wording, records, confirmation requirements, action order with business meaning, or role-specific access.
- Do not redesign the product from scratch or introduce a second visual language.

## Review Focus

- 1280px layouts with full admin navigation and wide tables remain usable without clipping or unintended overlap; manually inspect header, attendance, reports, administration, and grading at 1280px.
- Role-specific links and actions remain as before for admin, teacher, scanner, records officer, privacy officer, ICT, and school head; compare rendered navigation and page controls for each available role.
- Loading/error/empty/saving states give accurate feedback and keep the relevant action usable; manually inspect each newly updated state.
- Dialog focus enters, stays within, and returns to the invoking control, and keyboard dismissal does not bypass required confirmation; manually exercise each dialog family with Tab, Shift+Tab, Escape, Enter, and close controls.
- Focus indicators, visible labels, reduced-motion behavior, and normal-text contrast remain accessible; manually review keyboard paths and calculate/inspect contrast for any changed token pair.

---

### Task 1: Shared visual tokens, shell, and page landmarks

**Files:**
- Modify: `src/styles/index.css`
- Modify: `src/layouts/AdminLayout.jsx`
- Modify: `src/layouts/TeacherLayout.jsx`
- Modify: `src/layouts/PublicLayout.jsx`

**Interfaces:**
- Consumes: Existing CSS variables, `app-container`, header, nav, and main styles.
- Produces: Consistent desktop spacing/type/surface/control tokens and a keyboard-accessible skip link targeting the main landmark in all layouts.

- [ ] **Step 1: Define focused shared tokens and override points** in the existing active stylesheet. Keep existing navy/blue/neutral colors, Manrope/Inter, light theme, Lucide sizing, visible focus ring, and reduced-motion support. Use a 4/8px spacing rhythm; do not rewrite unused Vite starter styles.
- [ ] **Step 2: Add a skip link and explicit main target** to all three shells. Ensure the link is visually hidden until focused and moves focus to the main landmark when activated.
- [ ] **Step 3: Run `npm run lint` and `npm run build`**; resolve only issues caused by this task.
- [ ] **Step 4: Commit the shared shell and token changes** with message `style: refine shared EduScan interface system`.

### Task 2: Shared forms, tables, and status states

**Files:**
- Modify: `src/styles/index.css`
- Modify: `src/components/Common/PaginatedBody.jsx`
- Modify: `src/components/Common/Pagination.jsx`
- Modify: `src/contexts/ToastContext.jsx`

**Interfaces:**
- Consumes: Task 1 visual tokens and shell landmarks.
- Produces: Consistent field, table, pagination, toast, empty/loading/error, and saving-state presentation. Existing component props and business callbacks remain unchanged.

- [ ] **Step 1: Normalize reusable field, table, pagination, and toast states** in the shared components and stylesheet. Remove only redundant placeholder instructions; retain labels, distinct statuses, and table content.
- [ ] **Step 2: Run `npm run lint`, `npm run build`, and `node --test`**; inspect one shared form, table, pagination control, and toast state in the browser.
- [ ] **Step 3: Commit shared component refinements** with message `style: standardize shared forms and tables`.

### Task 3: Accessible dialog behavior

**Files:**
- Create: `src/hooks/useDialogA11y.js`
- Modify: `src/styles/index.css`
- Modify dialog JSX in `src/pages/Attendance/Attendance.jsx`, `src/pages/Administration/Administration.jsx`, `src/pages/Teacher/TruancyInterventions.jsx`, `src/components/Grading/*.jsx`, `src/components/Reports/AnnexGWorkspace.jsx`, `src/components/Scanner/StudentRegistrationModal.jsx`, and `src/components/Teacher/StudentProfileModal.jsx`.

**Interfaces:**
- Consumes: Task 1 focus tokens and Task 2 shared control styles.
- Produces: `useDialogA11y(dialogRef, { onClose, closeOnEscape = true })` for consistent initial focus, focus containment/return, and Escape handling; existing form submission and confirmation behavior remain unchanged.

- [ ] **Step 1: Implement `useDialogA11y(dialogRef, options)`** in `src/hooks/useDialogA11y.js`; handle absent initial focus targets, focus restoration when the invoking element is still connected, and Escape only when `closeOnEscape` is true.
- [ ] **Step 2: Apply semantic dialog labels and the hook** to each named dialog family while preserving `alertdialog` semantics and confirmation behavior where already required.
- [ ] **Step 3: Run `npm run lint`, `npm run build`, and `node --test`**; exercise Tab/Shift+Tab, Escape, Enter, close buttons, focus return, and browser console state in representative dialogs.
- [ ] **Step 4: Commit dialog accessibility refinements** with message `feat: make EduScan dialogs keyboard accessible`.

### Task 4: Overview, attendance, and embedded operations

**Files:**
- Modify: `src/pages/Dashboard/Dashboard.jsx`
- Modify: `src/pages/Dashboard/Dashboard.css`
- Modify: `src/pages/Attendance/Attendance.jsx`
- Modify: `src/pages/Operations/OperationalControls.jsx`
- Modify: `src/styles/index.css`

**Interfaces:**
- Consumes: Tasks 1–3 shared system.
- Produces: Clearer overview, attendance review, correction, and role-filtered operations views. Do not change polling, data, APIs, access, or action results.

- [ ] **Step 1: Consolidate the overview’s overlapping health presentation** while retaining every distinct API, database, LBPH/model, gateway, and checked-time indicator; keep attendance/SMS totals and all report/gateway links.
- [ ] **Step 2: Reorganize overview hierarchy** to show one primary gate-station action, a compact health summary, daily attendance/SMS summary, recent events, then quieter shortcuts.
- [ ] **Step 3: Reorganize attendance filters, counts, row actions, and audit disclosures** so reporting scope and date lead, main attendance table stays central, and correction/assisted attendance and clean-slate actions retain all existing confirmation and audit copy.
- [ ] **Step 4: Clarify each `OperationalControls` view’s section grouping and action hierarchy** for health, biometric settings, reviews, activity, SMS, retention/legal holds, and backup/recovery. Preserve role visibility and all records.
- [ ] **Step 5: Run `npm run lint`, `npm run build`, and `node --test`**; inspect overview plus admin, teacher, records/privacy officer attendance and relevant operations views.
- [ ] **Step 6: Commit operations surface refinements** with message `style: clarify attendance and operations workspaces`.

### Task 5: Grading and reports

**Files:**
- Modify: `src/pages/Grading/Grading.jsx`
- Modify: `src/components/Grading/GradebookSummary.jsx`
- Modify: `src/components/Grading/GradebookActions.jsx`
- Modify: `src/components/Grading/GradingSheet.jsx`
- Modify: `src/components/Grading/AssessmentConfig.jsx`
- Modify: `src/components/Grading/CalculationBreakdown.jsx`
- Modify: `src/components/Grading/AuditHistory.jsx`
- Modify: `src/components/Grading/AdjustmentRequestsModal.jsx`
- Modify: `src/components/Grading/FinalizeValidationDialog.jsx`
- Modify: `src/components/Grading/GlobalAdjustmentsTab.jsx`
- Modify: `src/components/Grading/ValidationChecklist.jsx`
- Modify: `src/components/Grading/ValidationIssueGroups.jsx`
- Modify: `src/components/Grading/GradebookActions.css`
- Modify: `src/components/Grading/GradingSheet.css`
- Modify: `src/pages/Reports/Reports.jsx`
- Modify: `src/components/Reports/AnnexGWorkspace.jsx`
- Modify: `src/components/Reports/AnnexGWorkspace.css`
- Modify: `src/styles/index.css`

**Interfaces:**
- Consumes: Tasks 1–3 shared components/tokens; existing gradebook/report services and callbacks.
- Produces: More legible class selection, gradebook tools, score sheet, review state, report selection, generated history, and export actions with existing formulas, data, and workflow unchanged.

- [ ] **Step 1: Group class-record selectors and reviewer gradebook search** into a clear selection area; retain current selected context, historical option, result count, and all role-specific controls.
- [ ] **Step 2: Improve score-sheet and gradebook-tool hierarchy** for saved/unsaved state, assessment configuration, validation, metrics, audit, adjustments, and export; keep the sheet’s score/status inputs and all spreadsheet content intact.
- [ ] **Step 3: Clarify report mode and generation controls** for daily vs. date range, attendance/personnel scope, SF2, export, and print; preserve official terminology and output parameters.
- [ ] **Step 4: Improve generated-report history scanability** and review controls without removing parameters, hashes, statuses, notes, filenames, or actions.
- [ ] **Step 5: Run `npm run lint`, `npm run build`, and `node --test`**; inspect teacher/admin/school-head/records-officer grading and reports states, including empty, dirty, validation, and history views.
- [ ] **Step 6: Commit grading and reporting refinements** with message `style: simplify grading and report workspaces`.

### Task 6: Setup and administration

**Files:**
- Modify: `src/pages/Setup/SystemSetup.jsx`
- Modify: `src/components/Setup/BiometricEnrollmentManager.jsx`
- Modify: `src/components/Setup/ClassScheduleManager.jsx`
- Modify: `src/components/Setup/PersonnelScheduleManager.jsx`
- Modify: `src/pages/Administration/Administration.jsx`
- Modify: `src/components/Scanner/BiometricConsent.jsx`
- Modify: `src/components/Scanner/EnrollmentFields.jsx`
- Modify: `src/components/Scanner/PhoneNumberField.jsx`
- Modify: `src/styles/index.css`

**Interfaces:**
- Consumes: Tasks 1–3 shared shell, field, table, and dialog patterns.
- Produces: Clearer task grouping for system configuration, enrollment, person/account/academic structure management, role-specific data controls, and destructive actions. Existing API calls, tabs, access, and confirmation remain unchanged.

- [ ] **Step 1: Refine setup tab headings and section grouping** for attendance rules, personnel schedules, face enrollments, and Android SMS; preserve tabs and every setting.
- [ ] **Step 2: Refine SMS task hierarchy** so gateway credentials/configuration, template editing, save, non-sending connection check, and real test SMS are visually distinct. Keep the long installation guidance available with clearer grouping.
- [ ] **Step 3: Refine administration tabs and working areas** for accounts, people/records, academic structure, activity, data management, backup/recovery, and service health. Separate routine management visually from full disposal and restore confirmations.
- [ ] **Step 4: Normalize setup/admin enrollment, schedule, and data forms** using shared labels, widths, field groupings, and feedback; do not change schemas or validation rules.
- [ ] **Step 5: Run `npm run lint`, `npm run build`, and `node --test`**; inspect each setup tab and each administration/operations tab available to representative roles.
- [ ] **Step 6: Commit setup and administration refinements** with message `style: organize setup and administration tasks`.

### Task 7: Scanner and teacher workspaces

**Files:**
- Modify: `src/pages/Scanner/Scanner.jsx`
- Modify: `src/pages/Login/Login.jsx`
- Modify: `src/pages/Account/AccountSecurity.jsx`
- Modify: `src/pages/Teacher/MyAdvisory.jsx`
- Modify: `src/pages/Teacher/MySchedules.jsx`
- Modify: `src/pages/Teacher/TruancyInterventions.jsx`
- Modify: `src/components/Teacher/ReleasedSF2Reports.jsx`
- Modify: `src/components/Teacher/SF2ReportGenerator.jsx`
- Modify: `src/components/Teacher/StudentProfileModal.jsx`
- Modify: `src/components/Scanner/StudentRegistrationModal.jsx`
- Modify: `src/styles/index.css`

**Interfaces:**
- Consumes: Tasks 1–3 shared hierarchy, feedback, and dialog patterns.
- Produces: Focused camera station and teacher pages with clear page context and existing actions preserved.

- [ ] **Step 1: Group scanner camera, service status, recognition feedback, and recent events** around the camera task; reduce the prominence of duplicate full-screen controls but keep both actions available.
- [ ] **Step 2: Add a clear heading and group/search hierarchy to the teacher roster**; retain both current profile-opening affordances, make their shared outcome explicit, and ensure the row interaction is keyboard accessible.
- [ ] **Step 3: Add explicit loading/error/empty states to teacher schedules and improve table grouping** without changing assigned schedule data.
- [ ] **Step 4: Reduce repeated vertical chrome in intervention results** while keeping each student’s absence summary, guardian contact, full intervention history, and log action available.
- [ ] **Step 5: Refine login and account-security copy/hierarchy** so the login describes all account roles and the password requirement/form actions are easy to scan, without changing authentication.
- [ ] **Step 6: Refine scanner enrollment and teacher profile/SF2 surfaces** using shared forms, dialogs, and table conventions.
- [ ] **Step 7: Run `npm run lint`, `npm run build`, and `node --test`**; inspect login, account security, scanner preview (without camera permission), enrollment, roster, schedule, and intervention states.
- [ ] **Step 8: Commit scanner, account, and teacher refinements** with message `style: refine scanner and teacher workspaces`.

### Task 8: Desktop visual and accessibility verification

**Files:**
- Modify only defects found in: `src/styles/index.css`, the route/component files above.

**Interfaces:**
- Consumes: Completed Tasks 1–7.
- Produces: Verified desktop interface and final defect fixes; no behavior, route, breakpoint, or dependency changes.

- [ ] **Step 1: Run `npm run lint`, `npm run build`, and `node --test`** from the project root; record pass/fail output.
- [ ] **Step 2: Inspect all routes and role-available views at 1280px, 1440px, and 1920px**; check overflow, density, content width, form/table alignment, and primary-action hierarchy.
- [ ] **Step 3: Exercise keyboard flows across navigation, filters, tables, and every dialog family**; confirm focus visibility, logical order, dialog focus entry/containment/return, and existing destructive-action confirmation.
- [ ] **Step 4: Check representative form labels/helper/error states and compute contrast for any changed text/surface pair**; verify reduced motion remains respected.
- [ ] **Step 5: Fix verified defects and repeat the relevant build/lint/test and visual check**; do not make speculative polish changes after the checklist passes.
- [ ] **Step 6: Commit final verified fixes** with message `style: finish EduScan interface polish`.

## Plan self-review

- Coverage: shared shell, design tokens, all routed pages and role variants, nested dialogs/forms/components, state feedback, keyboard access, desktop widths, light-theme contrast, and required frontend verification have assigned tasks.
- Boundaries: each task groups surfaces that share component patterns and ends with a build/lint/test cycle; no task changes APIs, schemas, routes, or permissions.
- Review focus is tied to manual checks in Tasks 4–8 because the project has no existing browser UI-test framework and adding a dependency is outside the approved design. Task 3 first checks whether the existing toolchain can test the dialog hook without a new dependency.
- Protected routes require credentials and the scanner needs a real camera for full operation; final verification must report any unavailable role/device states rather than claim they were exercised.
- No new feature or content claims are introduced; UI feedback is limited to existing save/request outcomes and missing presentation states.
