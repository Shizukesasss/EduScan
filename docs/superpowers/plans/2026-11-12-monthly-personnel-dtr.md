# Monthly personnel DTR implementation plan

**Goal** Add admin Form 48 downloads and recurring duty hours per employee.

**Architecture** Keep DTR rules, schedule storage, and routes separate from attendance processing. Use the supplied Excel template, generate PDF from the same report data, and register files in report history. Route personnel selections in the admin Reports page to the DTR controls.

**Spec** [Monthly personnel DTR design](../specs/2026-11-12-monthly-personnel-dtr-design.md)

## Implementation

- Add failing API tests for roster search by employee ID, admin permissions, saved weekday duty hours, four punches, incomplete days, noon, and exports.
- Add the versioned DTR schedule table and admin routes under `/api/dtr`. Read existing attendance, resets, and corrections with the same visibility rules as daily attendance. Expect punches only for elapsed duty periods and flag unknown schedules separately.
- Render both copies of Form 48 for the selected employee and month, preserve blank punches, and use existing report history with admin access for DTR files.
- Add the employee search, month, recurring hours, preview, and export controls under Monthly DTR. Route Faculty and Non-teaching Personnel downloads there while preserving the daily preview and the original controls for school-wide and learner reports.
- Run backend and frontend suites, lint, build, and inspect actual PDF and workbook output from the new route.
