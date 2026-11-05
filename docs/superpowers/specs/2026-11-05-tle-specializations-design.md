# Typed TLE specializations

## Intent

Allow admins to select TLE and type a specialization instead of choosing one from a dropdown. Multiple TLE specializations must coexist, each assignable to a teacher and usable through the existing subject, gradebook, and Excel workflows.

## Behavior

- Selecting the approved JHS TLE subject reveals a text field labeled “Specialization,” with an example such as Cookery or ICT. There is no specialization dropdown.
- Save each specialized TLE entry as a distinct subject, displayed as `TLE - Cookery`, for example. Generate a unique subject code automatically.
- Allow adding another TLE specialization even when a TLE entry already exists. Trim whitespace and reject duplicate specialization names regardless of case.
- Retain support for the existing plain TLE subject and its saved records. An empty specialization means plain TLE; existing uniqueness rules still apply.
- Editing a specialized entry restores its typed specialization and retains its subject identity, assignments, and gradebooks.
- Specialized TLE subjects use the same year, section, grade, teacher eligibility, permissions, and assignment rules as ordinary JHS subjects. Each specialization has independent assignments and gradebooks.
- Use the existing TLE grading setup and TLE workbook for both individual-period and all-period Excel exports. Preserve the specialization in visible subject labels and workbook subject headings.

## Approach

Use the existing subject identity and workflows, with a consistent TLE specialization naming convention and centralized recognition of specialized TLE subjects. This is the appropriate approach because the requested assignments and gradebooks already belong to individual subjects.

Keeping one TLE subject with a descriptive specialization would combine otherwise separate assignments and gradebooks, contrary to the user's clarification. A separate specialization subsystem would duplicate established subject workflows without providing a requested benefit.

## Constraints and implementation choices

- Extend the existing React and Python application without adding dependencies.
- Do not convert TLE specializations into electives: they retain TLE workbook routing.
- Audit subject recognition in grading, reports, and workbook selection so the typed suffix does not cause an unsupported-subject error or select a different grading policy.
- Preserve unrelated changes already present in the workspace.
- Implementation may choose helper placement and generated code format. If existing report grouping needs explicit TLE recognition, update it consistently.

## Verification

Cover creation of multiple typed specializations, normalization and duplicate rejection, edit preservation, independent teacher assignment and gradebooks, TLE policy/template recognition, and both Excel export scopes. Run relevant backend and frontend checks and the production frontend build.
