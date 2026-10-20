# Administrator schedules and teacher report access — review

What this change does: Administrators manage teaching schedules and generate attendance reports. Teachers can read their own schedules and saved official SF2 reports for their assigned classes, without generating, downloading, reviewing, or printing attendance reports in EduScan.

## Scope and findings resolved

- Enforced permissions on the server, including the old attendance log, printable attendance, both class-record print routes, SF2 export, report download, and report review routes. Class-record XLSX export remains available to teachers as before.
- Replaced teacher schedule editing with a shared read-only schedule table, also shown in Reports. Administrator scheduling selects an existing teacher account and existing academic setup. New schedules retain the teacher account ID; old name-linked schedules are shown only when the teacher name is unambiguous. No old schedules were rewritten.
- Teacher reports use a role recorded at report-generation time and class/period authorization. Rejected and superseded reports are excluded. The saved SF2 file is checked against its stored hash, then displayed as read-only data. This does not generate another workbook or change attendance. Saved tardiness shading is represented as L in the on-screen view.
- The daily report now starts with one attendance date. Date-range reporting remains available to the administrator. Daily attendance and enrollment/employment status are separate columns in the preview, printable daily report, and XLSX detail sheet.
- SF2 preview and generation share the selected-month roster, including dated departures. School years come from academic setup; invalid year/month combinations are rejected. Past instructional days with unresolved No scan entries must be reviewed or closed before official generation. The report screen never invents absences.
- Added field-specific placeholders to editable text, number, password, and multiline fields across the existing forms. Native date/time/month/file inputs retain their native controls and have selection hints. Existing labels, validation, and handlers remain.

## Verification

- Frontend lint and production build passed. Existing Scanner memoization and bundle-size warnings remain.
- 123 relevant backend tests passed: administrator reporting permissions (9), reporting reliability (8), attendance synchronization (24), smoke checks (10), grading regressions (64), and enrollment statuses (8).
- New tests exercise real routes with temporary SQLite and synthetic learners. They cover forbidden teacher actions, account-linked schedules, class-scoped report access, report integrity, actual SF2 snapshot preview and tardiness marks, selected-month departed learners, pending-day export blocking without attendance writes, school-year validation, and escaped daily report content.
- The live API was restarted and migration 0020 added two nullable fields. Counts of persons, face samples, attendance events/corrections, grade scores, student scores, gradebooks, SMS, users, schedules, and registered reports were identical before and after restart.
- Authenticated administrator browser checks verified Reports, monthly selection, actual academic dropdowns, and the schedule form without saving real schedules or generating reports. The available browser viewport was narrow; the forms stack correctly there.
- Authenticated teacher browser checks completed as Juan dela Cruz: Reports shows only his schedules and the official-SF2 empty state; Schedules has no create/edit/remove controls. The Class workspace shortcut opens the same read-only SF2 view. Two misleading old labels were corrected to View official SF2 and Official SF2 reports. No live schedule/report/attendance writes were made. Server-side teacher checks passed with isolated authenticated accounts.

## Operating notes and limits

- Old reports have no recorded generator-role snapshot. They are preserved in administrator history. An administrator must generate an official SF2 under the updated flow before it appears in teacher Reports. Existing files were not relabeled or regenerated automatically.
- Viewing data cannot prevent operating-system printing or screenshots. EduScan's teacher attendance report generation/download/print actions are blocked.
- Expected use is one school server and normal classroom/monthly rosters. Month validation uses the existing batched daily attendance reader; this review did not load-test a district-scale deployment.
- No live camera, SMS delivery, real schedule save, official report generation, or grade finalization was performed during browser checks. Isolated tests cover the changed write paths.

Verdict: Ship. No remaining blocking findings in the changed permission and reporting flows. Live populated preview was subsequently verified on 2026-10-18: the administrator generated October 2026 Official SF2 for Grade 7–Jose, school year 2026–2027. Signed in as Jeffrey Cruel, Reports showed that report and View SF2 displayed the saved learner row, school details, marks and totals with no editing, generation, download, print or review controls. Aggregate student, attendance, correction, grade, SMS and schedule counts stayed unchanged; the registered report count increased from 7 to 8 only. No attendance was closed or corrected. The October period is ongoing, so future dates remain blank.
