# Six demo advisory classes — design

## Intent
Let the administrator create six demonstration teacher accounts that can sign in and each advise a separate Grade 7–BEP section in a selected active school year.

## Agreed scope
- Add a dedicated “Create six demo advisory classes” option alongside the existing missing-assignment setup.
- Subjects: Filipino, Science, Values Education, TLE, MAPEH and Araling Panlipunan. Resolve the existing active subject records; report a missing or ambiguous subject instead of guessing or creating subjects.
- Create six realistic teacher names with separate Demo account indicators and unique usernames. Each teacher teaches one of the six subjects and advises their own separate Grade 7–BEP section for the selected school year.
- Keep Jose, Manuel and Oslo, their advisers and all existing teaching assignments unchanged.
- Use an administrator preview and separate confirmation. Show proposed teacher, subject, section, program and school year before saving.
- Create accounts, sections, teaching assignments and annual adviser assignments atomically. Reject stale previews and prevent repeated confirmation from creating duplicates.
- Show individual temporary sign-in credentials only once; require a password change at first login. Do not store plaintext passwords in previews or audit logs.

## Builder choices proposed
- Clearly mark section names as demonstration sections: “Demo Filipino”, “Demo Science”, “Demo Values Education”, “Demo TLE”, “Demo MAPEH” and “Demo Araling Panlipunan”. Keep teacher display names realistic.
- If a matching dedicated demo setup already exists for the year, show that it exists instead of creating another six accounts or reassigning its owners.
- No students, scores, attendance, schedules or reports are created. The sections initially have empty rosters; student enrollment is a separate action.
- Each teacher initially teaches only their own demo section. Existing teaching-assignment controls can later add eligible sections in the same grade.

## Approaches
1. Dedicated setup option: selected by the user. Reuses the current preview, confirmation, credentials and annual-adviser rules while limiting this operation to exactly six subject-specific classes.
2. Manual account and section creation: rejected as unnecessarily repetitive and easier to misconfigure.

## Constraints and verification
Preserve all existing people, grades, attendance, biometrics, report files and academic history. Reuse existing React, FastAPI, SQLAlchemy and password handling; add no dependency. Test exact six-subject coverage, Grade 7–BEP eligibility, unique identities, one adviser per year, missing/ambiguous subjects, stale and repeated submissions, rollback and protected-record preservation. Verify the authenticated administrator preview without creating live accounts during checks.

## Status
Design approved and implemented on 2026-10-23. Dedicated live preview verified; administrator confirmation creates the six accounts and sections. See the plan verification record for checks and limits.
