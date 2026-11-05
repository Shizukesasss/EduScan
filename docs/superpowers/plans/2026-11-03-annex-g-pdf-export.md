# Annex G Backend PDF Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Download a reference-matched Annex G PDF populated from existing learner, gradebook, attendance, and comment records.

**Architecture:** Keep data assembly in annex_g.py; add a pure ReportLab renderer. Release registers immutable PDF bytes through the existing GeneratedReport workflow. Serve historical HTML without conversion. Frontend consumes the same authorization context and adds explicit PDF preview/download actions.

**Tech Stack:** Existing FastAPI/SQLAlchemy/React stack; ReportLab runtime dependency; licensed bundled Unicode serif font; pypdf and Poppler for QA.

**Spec:** `docs/superpowers/specs/2026-11-03-annex-g-pdf-design.md`; prior JHS design remains binding where not explicitly superseded.

## Global Constraints
- Grades 7–10 only; one learner per PDF; one portrait page.
- A4 portrait is confirmed by the user for implementation.
- Never change scores, gradebook state, attendance, or enrollment while rendering/exporting.
- Reuse finalized/locked reported grades, existing annual rounding and MAPEH combination; parent MAPEH counts once.
- Future terms/annual results stay blank until applicable; missing data never becomes zero or inferred absence.
- Assigned advisers prepare/comment; Records Officers release. Preserve admin-only raw DOB and school-profile controls.
- Preserve historical HTML files, access checks, release history, and integrity verification.
- Match the supplied form, not its source-document introduction/page number. No clipping, hidden subjects, silent truncation, or arbitrary extra pages.

## Review Focus
- Mutable current placement must not replace the selected year's historical enrollment.
- Incomplete or mismatched grades and unresolved past instructional days must block release.
- MAPEH/elective rows and long localized text must fit without changing calculations or dropping content.
- Failed rendering/registration must leave the prior release available and not superseded.
- PDF/HTML content types, filenames, access checks, and checksum handling must remain correct across reissues.

---

### Task 1: Assemble complete form data and validated school metadata

**Files:** Modify `backend/app/services/annex_g.py`, `backend/app/schemas.py`, `backend/app/main.py`; extend `backend/tests/test_annex_g.py`.

**Interfaces:** Preserve `build_annex_g_section(db, school_year_id, grade, section, term_order) -> dict`; extend school/adviser metadata. Add validated `AnnexGSchoolProfilePayload` and admin-only GET/PUT `/api/annex-g/school-profile` under existing settings key.

- [ ] Add failing tests for year-specific adviser/head/profile values, missing name/LRN/sex/required metadata blockers, empty DOB, and rejection of unrelated-teacher access. Include two school years with different advisers and current placement different from historical placement.
- [ ] Run `python -m unittest discover -s backend/tests -p test_annex_g.py`; confirm expected missing-behavior failures.
- [ ] Add district, municipality/city, province and adviser identity to the assembled data using verified settings/SectionAdviserAssignment. Do not expose DOB. Validate bounded metadata strings; no arbitrary image paths/URLs. Ambiguous advisers block release rather than picking one.
- [ ] Preserve calculated term results and yearly attendance. Establish stable subject display ordering through codes/aliases matching the reference; append real assigned electives, never create scores for unassigned subjects.
- [ ] Add assertions against finalized source gradebooks for Terms 1–3, annual results, rounding, MAPEH once and elective inclusion. Confirm Term 1 leaves Terms 2/3/annual cells blank and Term 2 leaves Term 3/annual cells blank.
- [ ] Run focused tests green; commit this unit when using a development branch.

### Task 2: Implement the isolated one-page PDF renderer

**Files:** Create `backend/app/services/annex_g_pdf.py`, `backend/tests/test_annex_g_pdf.py`, `backend/resources/annex_g/` assets/license documentation; modify `backend/requirements.txt`, `backend/requirements-dev.txt`.

**Interfaces:** `render_annex_g_pdf(report: dict, enrollment_id: int, *, draft: bool) -> bytes`. Renderer raises a named layout error listing the overflowing region; endpoint translates it to 409. No DB/network operations in renderer.

- [ ] Add failing tests using synthetic assembled report dictionaries. Assert PDF header, one page, expected geometry, all reference section headings, exact LRN/name/subject/term values, attendance totals, and no future-term zeroes. Check draft watermark only when draft=True.
- [ ] Verify/install a compatible ReportLab release in the implementation environment and pin it. Add pypdf as a development-only dependency. Bundle a licensed Unicode serif font and available approved logos; document their provenance. Do not invent the missing DepEd emblem.
- [ ] Implement measured reusable text/cell/table drawing with centralized page geometry. Left: identity, learner details, intro, learning areas/terms/final/remarks, average and descriptors. Right: monthly attendance/totals, three term comment boxes, guardian lines, transfer/cancellation and signatories.
- [ ] Preserve literal untrusted strings as text, not markup; safely escape any Paragraph markup. Render missing values blank in draft. Keep raw DOB out of PDF content/metadata.
- [ ] Add long-name/comment/subject and all-month fixtures, accented names and punctuation. Assert explicit layout failure for beyond-capacity content, never partial output or extra pages. Long normal content must wrap within bounded readable sizes.
- [ ] Run `python -m unittest discover -s backend/tests -p test_annex_g_pdf.py`; render all fixtures to PNG with Poppler and inspect every region. Confirm paper size and descriptor/logo source before final layout acceptance.

### Task 3: Add draft PDF delivery and atomic PDF release

**Files:** Modify `backend/app/main.py`, `backend/app/services/reports.py` only as necessary for transaction support; extend `backend/tests/test_annex_g.py` and add `backend/tests/test_annex_g_pdf_api.py`.

**Interfaces:** New GET `/api/annex-g/preview/{enrollment_id}/pdf?term_order=1..3`. Existing release POST request/JSON unchanged. Existing `/api/annex-g/releases/{report_id}` dispatches PDF or legacy HTML with correct response type after existing access/hash checks.

- [ ] Add failing endpoint/service tests for draft PDF content type/filename, role and historical adviser scope, missing-data/layout blockers, wrong checksum, new PDF release, old HTML release, and immutable reissue.
- [ ] Return draft PDF bytes inline with DRAFT watermark, appropriate filename, and private/no-store cache policy. Preview creates no GeneratedReport, never changes grades/attendance, and does not release.
- [ ] Render and validate bytes before superseding anything. Register the new .pdf with template version, geometry, learner/year/term metadata and checksum; mark Released and supersede only prior same-enrollment/same-term releases.
- [ ] Resolve existing `register_report` internal commit carefully: add an optional `commit=True` argument, preserving all current callers. Annex G uses commit=False/flush and one encompassing transaction; remove copied artifacts on rollback. Test render, copy, flush and commit failure paths so prior release status/bytes are preserved.
- [ ] Continue serving historical .html snapshots from saved bytes, not regenerated data. Serve .pdf with application/pdf; expose safe inline filename. Verify checksum before either response. Preserve teacher-specific access rather than allowing generic download endpoints.
- [ ] Confirm draft/released downloads do not create duplicate records. Snapshot all gradebook/score/attendance/enrollment row values before and after API tests and assert unchanged.
- [ ] Run focused Annex G tests and existing admin-reporting/reliability regressions green.

### Task 4: Connect the Reports workspace to PDF actions

**Files:** Modify `src/components/Reports/AnnexGWorkspace.jsx`, `src/components/Reports/AnnexGWorkspace.css`; modify `src/api/client.js` only if a reusable authorized blob-preview helper is required.

**Interfaces:** Consume existing section/comments/release APIs, new PDF preview/profile endpoints, and version-aware released-file delivery. Preserve server-side role gates and Report navigation/table pagination.

- [ ] Add admin school-profile editing with visible labels, validation and saved state, preserving existing metadata. Display missing source/branding requirements explicitly; never guess school identity.
- [ ] Replace browser-only draft printing with Preview PDF. Fetch as an authorized blob, open a user-triggered preview window without popup races, revoke object URLs after use, and show errors without losing comments.
- [ ] Records Officer action becomes Release PDF. Prevent double submission while pending, preserve all release blockers, and refresh released history after success.
- [ ] Add Download PDF per saved PDF release using that registered artifact. Legacy HTML gets Open previous report rather than a misleading PDF filename; downloads never call release. Use existing report-history filename/type metadata or add a server-provided format field, not a guessed type.
- [ ] Restore keyboard focus appropriately after preview/save; provide per-action loading/disabled/error states. No nested interactive controls or clipped action menus.
- [ ] Run `npm run verify`; browser-check admin, assigned adviser, unrelated teacher, and Records Officer using an isolated synthetic database. Confirm preview/download/release actions, comments persistence and historical HTML.

### Task 5: Verify complete export and document deployment

**Files:** Create `docs/ANNEX_G_PDF_EXPORT.md`; keep test PDFs/PNGs in a dedicated temporary synthetic-output directory.

- [ ] Run all focused Annex G tests, `python -m unittest discover -s backend/tests`, `node --test tests/*.test.js`, and `npm run verify`. Record unrelated baseline failures without changing their code.
- [ ] Generate synthetic Term 1, Term 2 and Term 3 PDFs with distinct subject/learner values, extra electives, both MAPEH areas, long text, and complete attendance months. Independently compare every exported value to the selected class-record and attendance inputs.
- [ ] Use pypdf to assert single-page geometry and text presence; use Poppler PNGs for actual visual QA against the saved reference. Fix layout findings in a bounded batch and recapture.
- [ ] Verify release/reissue hashes, rollback behavior, existing HTML delivery, safe filenames, permissions and absence of any source-record mutations.
- [ ] Document runtime dependency/font assets, school profile setup, confirmed paper size, descriptor/branding source, draft/release/download workflow, and compatibility with archived HTML.

## Planning handoff
No runtime packages, source code, DB rows, or released files have been changed by preparing this plan. Final paper size and clear descriptor/DepEd-emblem sources remain explicit acceptance inputs. Batch export and SHS remain outside scope.

## Execution ledger
- User confirmed implementation and A4 portrait in chat.
- Ruling: work in the existing checkout to preserve the ongoing, uncommitted interface changes and approved report workspace; do not create a second checkout that omits them.
- Baseline: 23 existing Annex G tests pass.
- Dependencies: use ReportLab 4.4.9, pypdf 6.10.0 for QA, and licensed Noto Serif fonts packaged with the app. Network package setup needed the correct CA bundle.

## Implementation verification
- Completed data/profile mappings, A4 portrait renderer, authenticated preview/release/download, legacy HTML delivery, bundled licensed fonts and source emblem, and administrator configuration UI.
- 39 focused Annex G tests passed, including PDF structure/text, permissions, atomic reissue/rollback and post-commit refresh-failure regression. All 10 administrator reporting permission regressions also passed.
- Frontend lint/build passed and all 10 Node tests passed. Existing Vite bundle-size warning remains.
- Rendered and visually inspected synthetic early-term and year-end PDFs; checked names, all month labels, MAPEH subrows, future-term blanks, comments and signatory regions. No clipping observed.
- Headless Edge browser with an isolated synthetic SQLite database: admin draft PDF preview passed, Records Officer release and download passed, assigned teacher comment action present/release absent, no browser errors. Parsed downloaded release and checked exact synthetic learner/source gradebook values.
- Independent code review found and then verified a fix for shared report registration cleanup after a successful commit followed by refresh failure. No remaining material review findings.
- Full backend discovery was attempted but interrupted after local C: disk space exhausted; it is NOT claimed passing. Cleaned only task-created downloaded source PDF/browser profiles and stopped synthetic servers; did not remove school files.
- User confirmed A4 portrait. Descriptor wording and emblem were obtained from the original public DepEd source, so those acceptance inputs are resolved. Existing local age-policy confirmation remains unchanged.
- Follow-up on 2026-11-03: user changed the required output to A5 portrait and asked to tighten learner-field underline spacing. The renderer now emits A5, keeps its one-page form, derives underline starts from measured label widths, and records the new paper size/template version. Historical A4 releases remain unchanged.

Final status: Tasks 1–4 implemented and verified. Task 5 PDF/role/browser/frontend verification complete; full backend-suite completion remains limited by disk space. Targeted results: 39 Annex G tests and 10 administrator-reporting permission tests passed, plus 10 frontend tests. No production learner records were edited as part of the isolated PDF/browser verification.
