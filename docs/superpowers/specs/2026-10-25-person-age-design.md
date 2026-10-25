# Person date of birth and calculated age

## Intent

Capture date of birth in Administration's Add/Edit School Record form and the scanner's new-person registration form. Show age as a read-only calculation so Annex G and other approved reports can derive age for the correct reporting date without storing a second value that can become stale.

## Goals

- Require date of birth when creating a student record in either form; keep it optional for faculty and non-teaching personnel.
- Add the date-of-birth field to the shared enrollment fields used by both forms.
- Persist date of birth on the person record and carry it through create, update, and scanner registration APIs.
- Display calculated age beside the date field in the forms; reject future dates.
- Keep existing records valid with a null date of birth and allow legacy records to be edited without inventing a date. Flag missing learner age when an Annex G report is prepared for release.
- Keep date of birth out of teacher-facing roster responses; compute report age on the server for only the authorized report scope.
- Accept an optional date-of-birth column in roster imports.

## Non-goals

- Do not persist a separately editable age or alter grading, attendance, or enrollment rules.
- Do not change face capture, existing scores, or existing person records during migration.
- Do not add date of birth to teacher or general attendance exports.
- Do not implement Grades 11–12 reporting as part of this change.

## Approaches

1. **Store date of birth and calculate age (chosen).** Supports accurate age for the report's selected reference date and avoids stale duplicated age values. Requires protecting date of birth as sensitive personal data.
2. **Store age only.** Collects less sensitive data, but age becomes outdated and cannot reliably reproduce age for a past school year.

## Design

- Add nullable `date_of_birth` to `Person`, `PersonCreate`, and the person API mapping, with a versioned database migration. Existing rows remain null and unchanged.
- Require a date of birth for new student records through Administration, scanner registration, and roster import; keep the value optional for staff. Existing student records with no date remain editable without a fabricated value and must be completed before a future Annex G report can be released.
- Add a date input and calculated, read-only age display to the shared enrollment fields. Keep legacy and staff records without a date valid.
- Restrict date-of-birth reads to administrator workflows. Teacher-facing reports receive only the computed age for the learner and report date, within their authorized section scope.
- Extend roster import with a date-of-birth header alias and ISO/date-cell parsing; imports without that column remain valid.
- Use the report's selected school-year reference date when Annex G age is generated; preserve the generated PDF as the historical snapshot.

## Constraints and risks

- Date of birth is sensitive personal data, so API serialization must not expose it through broad person-list responses.
- New student records require a date, while existing null dates stay untouched until an administrator verifies and enters the correct value.
- Annex G release needs a defined school-year reference date; it must not recompute historic age using today's date.
- No learner birth dates will be fabricated or backfilled during migration.

## Scope

The main frontend touchpoint is `src/components/Scanner/EnrollmentFields.jsx`, shared by Administration and scanner registration. Backend touchpoints include `backend/app/models.py`, `schemas.py`, `main.py`, `migrations.py`, and `services/roster.py`.
