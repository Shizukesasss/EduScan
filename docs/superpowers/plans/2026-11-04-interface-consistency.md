# EduScan interface consistency implementation plan

> Execute the approved user brief across the existing React interface. Track progress here; preserve pre-existing edits.

**Goal:** A consistent, accessible school operations interface across all role workspaces.
**Architecture:** Keep React, plain CSS, local fonts, current APIs and route guards. Reuse a shared modal shell, page headings and request feedback. Improve the existing design tokens and canonical component rules rather than introduce a UI library.
**Spec:** The user's six-part implementation brief in this chat; PRODUCT.md supplies product truth.

## Constraints and rulings
- No backend, record, export-format, authentication, calculation or permission changes.
- Existing work is extensive and uncommitted. Work on `codex/eduscan-interface-consistency` in this checkout; a clean worktree would omit that work. Baseline source snapshot is in `tmp/ui-review/baseline-src` for an accurate task-only diff. Do not commit unrelated changes.
- Impeccable engine unavailable; context read directly. Native browser and Node REPL both fail to initialize; attempt an isolated headless browser for visual verification.
- Baseline `npm run verify` passes, with the existing large-bundle warning.
- Visual edits get build/browser checks; meaningful keyboard behavior gets regression tests. Avoid tests that merely repeat CSS declarations.

## Tasks
- [ ] 1. Shared accessibility: modal focus containment/restoration, dismiss behavior, toast announcements, skip links, role names, consistent heading/feedback primitives.
- [ ] 2. Teacher workflows: accurate loading/error/empty states, retry, meaningful headings, roster actions, intervention saving feedback.
- [ ] 3. All-module application: migrate generic dialogs; clarify setup/admin section navigation; polish login/security/scanner/attendance/grading/reports and preserve existing advanced workflows.
- [ ] 4. Visual system: consolidate modal rules, readable density, responsive containment, quiet surfaces, useful action icons and accessible touch targets.
- [ ] 5. Verification: lint/build, existing frontend tests, focused keyboard regression checks; isolated browser desktop/tablet/mobile/zoom review if available; final independent review.

## Review focus
Nested dialogs must restore focus to their own trigger; saving operations must not be dismissed accidentally. A request failure must never become an empty result. Long names and wide gradebooks must remain usable without page overflow. Restricted users must retain only their allowed actions. Official reporting and grading behavior must remain intact.

## Progress
Planning and source inventory complete. Implementation pending.
