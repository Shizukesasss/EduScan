# MAPEH native execution ledger — 2026-10-24

Implementation location: EduScan-mapeh isolated worktree. Original EduScan checkout and live database unchanged.

- Schema: area context fields/uniqueness and explicit opt-in PostgreSQL upgrade implemented. Fresh SQLite schemas tested; live DDL deliberately not executed.
- Service/API: separate empty area initialization, dedicated fixed policy, legacy write guards, preview/hash activation and audit implemented. Initial red tests covered unknown area/legacy write paths; final tests pass.
- Workspace: teacher and reviewer area navigation, unsaved edit guard, legacy read-only actions and combined term/annual summary implemented. Build and Node tests pass. Browser unavailable; interactive checks remain pending.
- Exports: supplied template retained, explicit area routing, complete pair requirement and term scopes implemented. Grade7-10 tests independently compare raw scores, calculation results, formulas and caches.
- Snapshot verification: read-only live snapshot copied into memory; activation and synthetic scoring/finalization only there. Five exports, 176 learner-area comparisons, live protected-table fingerprints unchanged.
- Final review fixed: legacy export cross-subject contamination — test_marked_legacy_export_excludes_other_parent_subjects RED→GREEN.
- Final review fixed: existing scored areas falsely called empty — preview now lists existing IDs separately, hashes their protected state and only creates missing records; test_preview_preserves_existing_area_and_hashes_its_scores passes (reviewer independently reproduced original failure).
- Direct-tool guard fixed: align_open_gradebook cannot change legacy/area policy — failing test then passing.
- Final verification: 20 backend tests pass; 43 Node tests pass; npm run verify and git diff --check exit0. Existing Scanner memoization/bundle warnings remain.
- Broader baseline: four grading-regression failures reproduced in original checkout; unchanged and outside this feature.

Pending boundary: present backend/work/mapeh-area-preview/README.md before any live schema/activation. Native desktop Excel recalculation and browser interaction not checked. PostgreSQL upgrade must be verified during reviewed deployment; no live DDL claim made.

Ruling: Keep the original checkout untouched and retain the isolated worktree pending approval — required by the approved live-impact gate; the feature is not visible in the running system yet.

## Approved live activation — 2026-10-24

User approved the concrete activation preview. Encrypted pre-activation PostgreSQL backup created and decrypt/hash verified in ignored backend/data/backups. Explicit schema upgrade ran twice successfully. Activation checked the exact approved hash, marked legacy IDs10,43,50 and created empty area IDs69-74 in one transaction. Existing score, item, component, policy and grade rows preserved; all other database tables unchanged during activation. Original statuses preserved, including Finalized Grade7-Jose.

Deployed only15 feature source/test files after baseline conflict checks; original source copies saved locally under ignored work/mapeh-before-source. Original checkout lint/build passed, all43 Node tests and20 focused backend tests passed; git diff --check passed with existing line-ending warnings. Backend restarted on port8000. Read-only HTTP checks passed for all six teacher area records, unrelated-subject403 denial, Records Officer access, healthy API and all11 preserved Jose legacy grades. No live scores saved or records finalized.

Built-in browser loads EduScan login. Authenticated interactive browser checks and desktop Excel recalculation remain unverified. Four previously identified baseline regression failures remain outside this feature.
