# Replace quarter with term order

## Intent

Remove the duplicate Quarter input and table column from Administration. The system uses terms, and the quarter number is currently repeated in several persisted and API fields.

## Goals

- Replace persisted `quarter` fields with `term_order` in grading periods, gradebooks, legacy gradebook state, and grade change audits.
- Replace the Grading Period form and table's Quarter field with no visible numeric field; keep the period name (for example, TERM 1) as the administrator-facing label.
- Update API payloads, frontend term selection, gradebook lookup, audit records, exports, and tests to use `term_order`.
- Migrate existing values in place so period IDs, gradebooks, scores, and audit history remain connected and unchanged.
- Preserve term ordering and the existing single-term and combined-term export behavior.

## Non-goals

- Change grading weights, grade calculations, term dates, finalization rules, or saved grades.
- Rewrite historical audit JSON snapshots or legacy class keys; those are retained as historical content for compatibility.
- Rename assessment components such as “Quarterly Assessment”; they refer to assessment content, not the school grading period.

## Approaches

- **Selected — rename to `term_order`:** migrate stored columns and update callers, preserving the numeric order the gradebook and exports need while removing Quarter terminology from active schemas and the UI.
- Derive all term order from names and remove stored order entirely: fewer columns, but custom or legacy period names can no longer be ordered reliably.

## Constraints and implementation decisions

- Add an idempotent versioned database migration after migration 0023. Rename existing columns and copy no data, so existing values and links are preserved.
- For new grading periods, derive order from a numbered term name (such as TERM 1); keep an existing record's order when editing it. Reject a new name with no unambiguous term number with a clear validation error.
- Keep the database term-order field internal; do not add a replacement numeric field to the form or table.
- Apply the change to the canonical `EduScan` checkout on `main`; do not edit the detached `EduScan-mapeh` copy.

## Success checks

- The Administration form and table no longer show Quarter.
- The migrated schema has `term_order` columns instead of the four `quarter` columns, and preserves their existing values.
- Existing gradebook selection, scoring, finalization, and term exports continue to use the same periods and stored scores.
