# EduScan interface polish design

## Intent

Polish the existing EduScan desktop interface across its routes, role variants, dialogs, forms, and shared components. Make school staff workflows calmer, easier to scan, and less crowded while preserving the existing product identity and operational detail.

## Why

The current app supports several staff roles and high-stakes attendance, grading, reporting, and records workflows. The audit found duplicated status presentation, uneven page hierarchy, long dense workspaces, inconsistent dialog/accessibility behavior, and a layered stylesheet that makes refinements inconsistent.

## Goals

- Give every route a clear heading, primary action, and predictable hierarchy.
- Apply a consistent spacing, type, form, table, surface, and dialog system using existing styles and components.
- Reduce visual competition in dense screens while retaining distinct information and all existing workflows.
- Make empty, loading, error, success, disabled, hover, and keyboard-focus states predictable where applicable.
- Improve keyboard navigation and dialog semantics, including a skip-to-content path.
- Use desktop layouts at common widths of 1280, 1440, and 1920 pixels.

## Non-goals

- No route, permission, feature, business-rule, data, or API changes.
- No new dark theme; the repository currently defines only a light theme.
- No mobile/tablet layouts, breakpoints, or touch-specific behavior. Existing breakpoints are not expanded as part of this work.
- No replacement of the school logo, brand palette, fonts, or school terminology.
- No dependency additions unless implementation proves an existing capability cannot meet the requirement; that would require a revised design decision first.

## Anti-goals

- Do not hide school-critical data behind extra clicks solely to make screens appear sparse.
- Do not remove a functional action or unique status/data point. If implementation uncovers a candidate functional removal, stop and ask first.
- Do not alter report wording, records, confirmation requirements, action order with business meaning, or role-specific access.
- Do not redesign the product from scratch or introduce a second visual language.

## Constraints and current state

- React 18, React Router, Vite, Lucide, and plain CSS are already used. `src/main.jsx` imports `src/styles/index.css`; `src/App.css` and `src/index.css` are unused Vite starter styles.
- Existing product tokens use school navy, blue actions, neutral surfaces, and bundled Manrope/Inter fonts. Preserve them. The generic UI/UX search suggested a cyan palette and different typefaces, which conflict with the product brief and are not adopted.
- `src/App.jsx` defines public login/security/scanner routes, administrator workspace routes, teacher workspace routes, role gates, and shared attendance/grading/report pages.
- There are administrator, teacher, scanner, records-officer, privacy-officer, ICT, and school-head variants. Component-level review must preserve role-specific navigation and actions.
- The audit was source-based for protected routes because no test credentials were provided. The login page was visually inspected in the local browser.
- `impeccable context` could not run: its engine cache is absent and requires write access outside the workspace. PRODUCT.md and the maintained source/style files were read directly. No DESIGN.md exists.

## Approaches

1. **Shared system, then every screen (selected by the user).** Normalize the existing tokens, shell, controls, tables, and dialogs, then apply them across all routes. This resolves common inconsistencies at their source and fits the request for small, reusable edits.
2. Screen-by-screen refinements with little shared-style work. Rejected because repeated patterns would remain inconsistent across roles.
3. Highest-severity screens only. Rejected because the user asked to polish the entire interface.

## Scope by surface

### Shared shell and components

- Admin/teacher/public shells: spacing, content width, active-route clarity, page landmarks, keyboard navigation, and focus treatment.
- Forms and controls: consistent labels, helper/error treatment, disabled/saving feedback, button hierarchy, and removal of redundant placeholders where the label already explains the field.
- Tables and pagination: scan order, row action grouping, readable density, consistent empty/loading/error states, and keyboard access.
- Dialogs: consistent sizing and footer hierarchy, semantic roles/names, keyboard handling, and focus behavior. Preserve dialog-specific confirmation text and every action.
- Toasts, status badges, notices, and empty states: consistent tone and visual priority without losing distinct statuses.

### Routes and role variants

- `/login`: role-neutral credential copy and reduced repeated school identity.
- `/account/security`: password requirement hierarchy, form spacing, and primary/secondary actions.
- `/scanner`: preserve camera as the focal point; group operational state and controls; reduce the prominence of duplicated full-screen affordances without removing actions.
- `/dashboard`: retain all health values while consolidating overlapping indicators; establish one primary task and quieter support links.
- `/dashboard/attendance` and `/teacher/attendance`: organize filters, summaries, table actions, and audit disclosures while retaining role-scoped options and corrections.
- `/dashboard/grading` and `/teacher/grading`: clarify class selection, tabs, saved/unsaved state, validation, and score-sheet hierarchy without changing the grading workflow or sheet content.
- `/dashboard/reports` and `/teacher/reports`: distinguish current report generation from historical review, clarify daily/date-range mode, and improve wide-table actions.
- `/dashboard/setup`: retain the existing task tabs; group operations and SMS settings into clearer sections and differentiate saving, connection checks, and real test SMS.
- `/dashboard/administration`: retain current tabs and role-specific operation views; separate routine management from destructive actions visually while preserving all actions.
- Embedded operations views: health, biometric/liveness, review queue, audit, SMS reconciliation, retention/legal holds, backup/recovery. Improve hierarchy within each role-filtered view without adding routes or changing access.
- `/teacher/roster`, `/teacher/schedules`, `/teacher/truancy`: add clear page context, make roster profile access unambiguous, provide explicit request states, and reduce repetitive intervention-card height while keeping learner history accessible.
- Nested enrollment, student profile, attendance correction/assist/reset, intervention, grading configuration/adjustment/audit/validation, and administration dialogs are included.

## Add / Remove / Change

### Add

- Missing loading, error, empty, saving, and success states, using existing toast conventions where appropriate.
- A skip-to-main-content link in app shells.
- Consistent accessible dialog names, focus entry/return, keyboard dismissal where safe, and focus containment for modal dialogs.
- Clear page headings and concise contextual helper text where audit findings show users lack orientation.
- Visible saving/disabled feedback for actions that currently lack it.

### Remove

- Redundant explanatory copy and placeholder text when labels already provide the same instruction.
- Overlapping presentation of the same status, consolidating the display while retaining all distinct status values and information.
- Unnecessary decorative borders, shadows, and repeated icon treatments where spacing can group content.
- No functional control, route, workflow, permission, or unique data point is approved for removal.

### Change

- Establish a coherent 4/8px-based spacing scale, 2–3 type sizes per section, and reusable page/section heading patterns.
- Keep the current brand variables, bundled fonts, light theme, and existing icon family.
- Set sensible desktop content widths: broad enough for operational tables and grade sheets, narrower for forms and explanatory text.
- Make one primary action visually dominant per view and secondary/destructive actions quieter.
- Use whitespace and task grouping before adding borders, boxes, tabs, or nested disclosures.
- Consolidate duplicate health presentation without losing unique indicators.
- Reduce visual density in rosters, intervention history, setup, admin, reports, grading controls, and operations views while preserving underlying rows and access.

## Implementation choices left to the builder

- Exact spacing and type token values, CSS consolidation order, and whether a small shared component should be extracted where it reduces duplication.
- Exact content max-width per page family, based on its operational data shape.
- Which existing repeated content can be collapsed into disclosures, provided its state and full content remain available and the default view remains clear.
- The specific missing states per request and an auditable desktop visual QA matrix.

## Verification expectations

- Build and lint the frontend and run the existing frontend test suite.
- Inspect representative and role-specific routes, dialogs, empty/error/loading states, and dense tables at desktop widths 1280, 1440, and 1920 pixels.
- Confirm focus visibility, keyboard access, dialog focus handling, labels, and text contrast against the retained light palette.
- Confirm no new responsive breakpoints or mobile/tablet layouts were introduced; no dark theme exists to verify.
- Report inaccessible protected screens or operational states that could not be exercised without user-supplied test accounts or available devices/services.
