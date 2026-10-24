# Decimal-safe grade calculation parity

## Intent

Make EduScan's live gradebook, backend grade calculation, and XLSX exports agree at percentage and transmutation boundaries. For example, raw scores of 14.236/20 produce exactly 71.18%; the 71.18 transmutation threshold must therefore produce 76 consistently, rather than dropping to 75 because of binary floating-point representation.

## Goals and constraints

- Keep the current component weights and the ST1/ST2/TE 30/30/40 exam split unchanged.
- Keep existing scores, saved policies, rounding settings, and transmutation tables unchanged.
- Use decimal-safe arithmetic consistently in browser previews, backend calculation, fixed-template XLSX exports, and adaptive XLSX exports.
- Preserve incomplete-draft display behavior and existing unrounded-threshold behavior (71.175 remains below 71.18).
- Add a regression case for the 71.18 boundary and run calculation plus export parity checks.

## Approaches

- **Decimal-safe arithmetic across calculation and export paths — selected.** Prevent representation noise before comparison, so each path applies the same mathematical result. This follows the supplied formula while preserving the approved weights.
- **Add a small tolerance near thresholds.** Fewer changes, but may promote a truly lower score.
- **Force exports to copy the gradebook's current reported grade.** Avoids the export block but keeps the calculation inconsistency in the workbook formula.

The decimal-safe approach is selected because it preserves the mathematical comparison and avoids changing the grading policy. Only final grades affected by floating-point boundary noise may change; raw scores and stored policy remain untouched.

## Scope

Update the shared browser and backend calculation logic and the XLSX calculation/check paths that consume it. Do not change component weights, transmutation boundaries, score completeness rules, or saved score rows.

## Verification

Verify 71.18 maps to 76 and 71.175 remains 75 in browser and backend calculations; verify representative JHS subject, MAPEH, SHS/adaptive exports match the gradebook and formulas without changing fixture scores. Existing test-suite failures unrelated to calculation parity should be reported separately.
