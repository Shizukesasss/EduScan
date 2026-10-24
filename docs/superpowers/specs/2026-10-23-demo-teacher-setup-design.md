# Demonstration teacher and adviser setup

## Intent
Help the administrator populate demonstration teaching coverage in existing sections without replacing real or existing assignments.

## Agreed rules
- Adviser assignments belong to a section AND a specific school year. A section may have different advisers in different years; prior-year assignments remain available as history.
- Create demonstration teachers only, using realistic display names such as Lisa Manoban; do not put TEST or TEACHER TEST in their names.
- Mark demonstration records separately from their display names.
- Each teacher teaches one subject per school year, within one grade level, and can handle several eligible sections.
- Each teacher advises at most one section per school year, even when teaching several sections. A section has at most one active adviser in that school year.
- Fill missing assignments in existing sections. Preserve current teachers, advisers and subject assignments.
- For an unadvised section, propose an adviser who teaches that section.
- Administrator reviews the proposed teachers and assignments before saving.

## Approaches considered
1. Fill missing assignments in existing sections: selected by the user; preserves the current setup while making remaining coverage demonstrable.
2. Create separate demonstration sections: not selected; would add sections beyond the requested existing context.

## Proposed workflow
1. Administrator selects an active school year and the JHS grades/sections to include.
2. Read active subjects, allowed elective grades, programs, current subject-teacher assignments, advisers and existing teacher commitments.
3. Propose coverage for each missing eligible section/subject pair. Group new teachers by grade and subject so one teacher can cover multiple sections. Existing assignment gaps are filled with new demo teachers, without expanding or replacing existing teachers' commitments automatically.
4. Assign proposed advisers to unadvised sections. Prefer an existing uncommitted demo teacher proposed for that section. If there are too few distinct teachers, propose additional demo teachers and split the missing teaching coverage between them, ensuring each proposed adviser actually teaches their section. Never silently appoint the same teacher to two sections. If no eligible missing teaching slot remains, identify the section as unresolved for administrator review rather than replacing an existing assignment.
5. Show a preview of new names, demo status, subject, grade, handled sections, adviser section, preserved assignments and unresolved gaps. Summarize why any pairing cannot be generated.
6. After the administrator confirms, revalidate against current records and save atomically through the existing account and assignment rules. If coverage or adviser commitments changed since preview, reject stale proposals and refresh the preview. A repeated confirmation must not create duplicate teachers or assignments.

## Safety and boundaries
- Do not alter saved scores, grading policies, gradebook ownership, attendance, biometric samples, reports, school calendars or class schedules.
- Respect allowed JHS grades and STE eligibility for electives; keep SHS outside this initial design.
- Preserve existing accounts and names. Generate unique demo usernames and use the existing temporary-password/change-on-first-login flow; do not print credentials in application logs or audit text.
- Demo status is metadata, not a change to authorization: generated accounts retain ordinary teacher permissions.
- This is administrator-only setup; it does not select or appoint actual school employees.
- Adviser cardinality and assignment conflicts must be checked on the backend, including existing teachers' adviser commitments.
- Resolve adviser access, advisory rosters, attendance and official reports using the relevant school year. Do not fall back to another year's adviser when a year has no assignment. Teacher subject assignments already belong to a school year and retain that structure.
- The user confirmed that existing section-level advisers belong to SY 2026–2027. Migrate those links only into that school year, preserving the original links for traceability. Never copy them into every historical school year. Reject conflicting pre-existing annual assignments rather than overwriting them.

## Implementation discretion
Use the existing administration forms, backend services, validation and auditing. Reuse an existing batch-preview pattern if available. Determine the smallest compatible way to record demo provenance and prevent repeated application after inspecting account provisioning and existing audit metadata; do not add a broad account-management subsystem.

## Verification
Isolated tests cover one subject/year, one grade, multiple sections, one adviser section, existing-coverage preservation, elective/program restrictions, insufficient adviser coverage, duplicate submission, stale previews, authorization and transaction rollback. Compare protected data before/after. Verify preview on desktop/mobile and keyboard access, then test with synthetic records only.

## Status
Initial design approved; amended to require school-year-specific adviser assignments. User confirmed existing advisers map to SY 2026–2027. No demonstration accounts or assignments created.
