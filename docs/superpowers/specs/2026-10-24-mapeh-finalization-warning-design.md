# MAPEH finalization warnings

## Intent

When a teacher clicks Finalize for a MAPEH learning-area gradebook, clearly explain why finalization is blocked if the selected area has no complete grades or its matching Music and Arts / PE and Health gradebook is incomplete. Teachers may still save drafts independently.

## Scope and constraints

- Apply the feedback to every term; validation is for the selected term and its matching area pair.
- Keep the current completeness rules, grading calculations, score-save behavior, and server-side finalization guard unchanged.
- Do not save, finalize, or modify any live class record as part of implementation or verification.
- The existing error toast and validation flow are the smallest suitable UI; no persistent warning banner or new controls are needed.

## Approaches

1. **Error when Finalize is clicked (recommended; inferred from the request).** Reuse the current validation/toast path and show a MAPEH-specific explanation for an empty/incomplete selected area. Keep the existing partner-area message, tightening its wording if needed. This is immediate and contextual without adding constant UI.
2. Persistent warning while either area is incomplete. This surfaces status earlier but adds repeated UI and duplicates the Finalize-time validation.
3. Disable Finalize until both areas are complete. This prevents the action but hides the reason and does not explain that Save Draft remains available.

## Behavior

- If the selected MAPEH area has no score entries or incomplete scores, clicking Finalize displays an error naming the selected area and term, explains that its scores must be completed, and reminds the teacher that the draft can still be saved.
- If the selected area is complete but its partner area is missing or incomplete, clicking Finalize displays an error naming the partner area and term.
- In both cases, keep the confirmation dialog closed and do not finalize either area. A complete selected area and complete partner area continue through the existing confirmation flow.
- Leave Save Draft available for the selected area as long as existing role and status rules allow editing.

## Verification

Add isolated tests for an empty/incomplete selected area, a complete single area with an incomplete partner, and a complete pair. Cover term-specific messaging for Terms 1–3 where the existing test helpers permit. Run focused frontend and backend grading tests. Inspect the diff and build checks; do not test against or write to live data.
