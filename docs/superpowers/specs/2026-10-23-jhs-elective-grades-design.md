# JHS elective allowed grades

## Intent
Administrators assign each JHS elective to one or more grades from 7 through 10. For example, Research 1 can be limited to Grade 7, while Robotics can allow Grades 7 and 8.

## Approaches
The user selected allowed grades per elective rather than relying only on assignments to individual sections. A central subject restriction prevents accidental assignment to the wrong grade and can be reused by schedules and gradebooks.

## Proposed behavior
- Only administrators edit allowed grades, alongside the existing elective subject settings.
- A JHS elective requires at least one allowed grade. Only Grades 7–10 are valid.
- Eligible sections must satisfy both the allowed-grade selection and the existing STE program restriction.
- Subject selectors, teaching assignments, schedules, and new gradebook creation enforce the restriction. Backend validation also rejects invalid new assignments independently of the browser.
- Teachers see only electives eligible for the selected grade and their existing teaching assignments.
- Existing JHS electives initially allow all Grades 7–10, preserving current availability until the administrator narrows them. This is the proposed compatibility default, not an existing user decision.
- Narrowing allowed grades does not delete, reassign, or recalculate saved records. Existing gradebooks remain available through their saved context; creating new out-of-scope assignments is blocked. Existing incompatible assignments are retained and identified for administrator review rather than silently changed.
- Core JHS subjects, SHS rules, grading formulas, scores, and Excel template mappings retain their existing behavior.

## Scope and verification
Extend subject persistence, schema validation, academic-structure responses, shared eligibility helpers, administration forms, and assignment/schedule/gradebook callers. Use isolated tests for single and multiple allowed grades, invalid grades, missing selections, STE eligibility, access roles, and preservation of existing gradebooks. Check frontend lint/build and authenticated forms when a session is available.

## Non-goals
No automatic subject-to-grade guesses from names, changes to student enrollment, removal of historical records, or grading-policy changes.

## Status
Approach selected. Short design awaiting user approval before implementation planning.
