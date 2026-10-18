# Enrollment and employment statuses

Students: Regular, Transferred In, Transferred Out, Dropped Out, Withdrawn,
Graduated, Other. Staff: Appointed, Transferred In, Transferred Out, Resigned,
Retired, Contract Ended, Other. Existing staff records using Regular remain valid.

Use the last enrolled / duty date as the final eligible attendance day. The
following day uses the selected departure reason instead of treating every
departure as a transfer. Appointments and transfers in require a start date;
departures require a last-day date. Other requires an explanation. Active/Inactive
remains independent. Changing status does not remove scores, attendance, face
enrollment, or the person's identity. Missed scans never change lifecycle status.

The shared backend validation also handles roster import. Gate scans and assisted
attendance cannot create attendance outside the person's period. Daily close
does not mark departed people absent. A manual correction must also respect the
period; clear an erroneous scan or correct the school-record dates first.

Historical attendance and SF2 include inactive departures. SF2 retains learners
whose enrolled dates overlap the selected month, puts the actual departure reason
and last-day date in remarks, and excludes days outside the period from absence
and presence counts. Staff never enter the learner SF2 roster. Legacy records
with an end date but no departure reason show Enrollment Ended / Service Ended,
rather than inventing a transfer. Legacy departures missing dates are preserved;
staff must supply a date when updating them.

Migration 0019 adds one nullable notes column without rewriting existing rows.
Before/after counts matched across nine live record tables after reload.

Validation: 86 isolated backend tests passed across lifecycle/SF2 (8), attendance
(24), smoke/migration (10), atomic enrollment/disposal (16), gate (12), and audit
rollback (16). Frontend lint/build passed with pre-existing memoization and bundle
size warnings. Tests used synthetic identities, temporary databases and reports.

Authenticated browser checks: student/staff identifiers and phones, role-specific
status options, required last-day dates, required Other reason, expandable terms,
existing teacher edit values and Cancel, plus lifecycle fields and camera-free
registration in Enroll Person. Only unsaved selections were made; no real person,
attendance, SMS, face samples or disposal was submitted. The camera stayed off.

Not checked: fresh camera hardware behavior or deployment load.
