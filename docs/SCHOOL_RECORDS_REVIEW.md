What this change does:
Students enter an LRN; staff enter an employee ID. Administration and camera
registration show guardian phone for students and phone number for staff, and
share expandable biometric enrollment terms. School records no longer show the
face-sample count. Full disposal requires an administrator, an explicit checkbox,
and the person's exact identifier; the audit still records the actor and time.

Existing identifiers are preserved when editing, including older student IDs.
New LRN-only records use the LRN as the existing internal external ID so no
database migration or relinking is needed. Contact numbers keep the existing
storage field so attendance and SMS integrations remain compatible.

Disposal removes biometric rows, encrypted samples, and obsolete recognition
models after the database operation commits, rebuilds the remaining model, and
clears the removed person's cached identity features. Relocated sample paths use
the same resolution as recognition. A failed transaction preserves files. File
permission failures are reported as pending cleanup rather than complete success.
Existing backups are not purged by this operation.

Review assumption: the current local single-server deployment and existing
PostgreSQL enrollment locking. No additional deployment load test was performed.
No remaining blocking findings in this change. Looks good. Ship.

Checked: 96 isolated backend tests (16 atomic enrollment/disposal, 16 audit and
rollback, 10 application smoke, 54 biometric regressions), frontend lint/build,
and rendered disposal controls for unchecked, incorrect-ID, busy, and valid
confirmation states. Existing bundle-size and memoization warnings remain.
No real school records or real face enrollments were deleted during validation.
Not checked: authenticated browser forms; the available browser opened at login.

Original lifecycle proposal (implemented in the subsequent enrollment-status change; see ENROLLMENT_STATUSES.md):

- Keep Active/Inactive separate from the reason a person arrived or left.
- Students: Regular, Transferred In, Transferred Out, Dropped Out, Withdrawn,
  Graduated, or Other; record the effective date and an optional staff note.
- Staff: Appointed/Transferred In, Transferred Out, Resigned, Retired,
  Contract Ended, or Other; record the effective date and receiving/previous
  institution only for transfers.
- Deactivate departures to stop automatic recognition, preserving attendance,
  grades, and history. Never infer resignation or dropout from missed scans.
- Returnees should reactivate their existing identity rather than create another
  record. Full disposal remains a separate, explicit permanent action.
- Before implementing these statuses, update attendance and SF2 together: they
  currently label an enrollment end date as Transferred Out. Adding dropdown
  choices alone would misclassify dropouts and staff departures.
