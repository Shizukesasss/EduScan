# Monthly personnel Daily Time Record

## Purpose

Give admins a monthly CSC Form 48 download for one faculty or non-teaching employee at a time. Use the supplied workbook as the layout reference and retain its two copies of the form.

## Approaches

- **Replace the personnel download in Reports.** This is the requested approach. Keep the daily attendance preview and direct Faculty and Non-teaching Personnel downloads to Monthly DTR. That workspace provides an employee and month selector, a punch preview, and PDF and Excel downloads. The DTR service generates the form and registers it in the existing report history.
- **Add a separate DTR workspace.** This would preserve the generic personnel export in the interface and provide both formats. It would also leave two ways for admins to export personnel attendance, where the requested workflow calls for the Form 48 replacement.

## Punch rules

- Use the school-local date and time recorded by EduScan. AM covers times before noon. PM starts at noon.
- An exact noon Time Out is shown as a PM departure. For morning duty scheduled to end at noon, that punch also satisfies the expected departure for review.
- For each day, use the first Time In and last Time Out within each period. AM scans populate AM fields and PM scans populate PM fields. A morning arrival and afternoon departure fill those two cells and leave the other two blank.
- Respect the existing reset, correction, service-date, and calendar rules. If a correction replaces or clears daily times, honor those corrected values. Flag any remaining ambiguity for review without changing the attendance record.
- Leave missing punches blank and flag incomplete elapsed workdays in the preview based on the expected duty periods. Leave future dates blank. Show recorded punches on weekends and holidays when present. Use the selected month's actual calendar, including leap days.

## Recurring duty hours

In Monthly DTR, admins select a faculty or non-teaching employee by name and Employee ID and can save recurring duty start and end times by weekday. Store the schedule against the personnel record ID. Use the employee's DTR schedule for that weekday when configured. Otherwise, use EduScan's existing applicable personnel schedule. If neither is configured for an elapsed workday, flag the schedule for review.

Expect punches for the periods covered by official duty hours. For example, Tuesday duty from 7:30 AM to 11:30 AM calls for AM arrival and departure. Blank PM fields are expected, and any actual PM scans still appear. The recurring employee schedule affects only Form 48 and its review flags. Keep attendance recording, late and absence processing, and SF2 on their existing rules.

## Form and export

Use the employee's name and the selected month on both copies. Populate the school, personnel, and schedule details where supported by EduScan. Leave unavailable values and signatures blank for completion. The workbook's Albay header, November 2026 dates, and sample office hours are layout examples. Keep undertime available for manual completion until the school provides a calculation rule. Leave its totals blank while there are no undertime entries.

Restrict generation to admins and validate the employee's personnel role on the server. Keep prior generated reports available through report history. Preserve the student and school-wide exports, SF2, and the existing attendance APIs, scanning, corrections, and scheduling workflows.

## Verification

Verify a four-punch day, an AM-in/PM-out day, a PM-only day, multiple scans in a period, noon, missing punches, corrected or reset records, and a short month. Verify recurring morning-only duty, separate schedules for employees with the same role, and fallback to the applicable personnel schedule. Verify that both exports show the same selected employee and times, access is admin-only, and SF2 and the existing attendance tests still pass.
