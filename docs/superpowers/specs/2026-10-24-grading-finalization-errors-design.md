# Design: Clear gradebook finalization errors

## Intent
Help teachers find missing grades before finalizing any gradebook. When a required score is blank or otherwise incomplete, show the exact learner and assessment activity instead of a count and a few names.

## Goals and constraints
- On Finalize, show a persistent, dismissible validation panel grouped by learner with the missing activity labels (including ST1, ST2, and TE when applicable).
- Apply the same behavior to every gradebook and MAPEH learning-area book.
- Keep finalization blocked until all required entries are complete; preserve current activity, status, and grading rules.
- Keep browser preflight and server-side rejection details consistent, including when saved data changed after the page loaded.
- Do not change scores, compute grades differently, or auto-save during validation.

## Approaches
- **Persistent grouped panel (selected):** Lists every affected learner and the exact activity or activities. It stays visible until dismissed and is easier to act on when many entries are missing.
- **Detailed toast:** Smaller change, but long class-wide lists may disappear before teachers can use them.

## Implementation choices
Use the current validation inputs, including unsaved score/status edits, and report the missing or invalid learner–activity pairs. Preserve the current validation criteria. Show MAPEH area and term context where relevant. The server must reject the same incomplete records with the same actionable detail. No saved records change as part of validation.

## Acceptance checks
- A missing score identifies the learner and activity.
- Missing ST1, ST2, or TE names the specific exam item for each affected learner.
- Multiple issues are grouped per learner and remain readable until dismissed.
- MAPEH identifies its area and term.
- Finalization remains blocked, and completed, valid gradebooks keep their current behavior.
