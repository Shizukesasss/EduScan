# Annex G backend PDF export design

Status: Implemented after user approval of backend PDF export and the supplied form. A later user instruction changes the page size to A5 portrait; see the implementation-plan execution record.

## Intent and scope
Produce an actual downloadable PDF matching the supplied Annex G form, rather than relying on browser print settings. Keep the approved Grades 7–10 workflow from `2026-10-25-annex-g-jhs-report-design.md`. The attached image is visual authority, not an instruction to change grading policy or extend to Grades 11–12.

Reference: `../references/2026-11-03-annex-g-reference.png`. Reproduce the form inside the border, excluding its source-document introduction, Annex G heading outside the form, and page number 48.

## Approaches
1. Server-side ReportLab PDF generation — selected by the user. Predictable local output, downloadable bytes, no browser engine required. Adds one runtime library and packaged font/branding assets.
2. Improve HTML and use browser Save as PDF — rejected for the requested downloadable backend PDF because print settings vary and export is manual.
3. HTML-to-PDF with a bundled browser engine — not selected: introduces a larger deployment/runtime dependency than this structured form needs.

## Format and visual contract
- One learner per PDF; one portrait page containing the two-column form, framed by a thin black border.
- The original request explicitly confirmed A4 portrait. The later request on 2026-11-03 supersedes it with A5 portrait. Preserve the single-page form by scaling its established geometry; new releases record A5 portrait.
- Left column: school identity and logos; learner details; parent introduction; learning progress table; general average; descriptor legend.
- Right column: horizontal monthly attendance table with totals; comments for Terms 1–3; parent/guardian signature lines; certificate of transfer; cancellation-of-eligibility section and signatory lines.
- Match reference wording and line structure where legible. Check descriptor wording against a clear source before freezing template copy; retain the existing approved policy values until verified, never silently change calculations from blurry text.
- Preserve the Track (SHS only) line as blank for JHS; no SHS data is inferred.
- School and learner text wraps in measured cells. No clipped text, hidden subjects, missing months, silent truncation, or unreadably small type. If content cannot fit within the approved page geometry, return a specific layout blocker before release; do not silently spill onto a second page.
- Package a licensed Unicode serif font with normal/bold/italic faces as needed. Do not depend on fonts installed on the server or internet access at export time. Verify ñ, accented names, punctuation, and the full LRN string.
- Use the existing school logo with preserved aspect ratio. The DepEd emblem was extracted from the original public Annex G source PDF; no imitation was generated. Missing required branding is a configuration blocker for final acceptance.

## Data contract and mappings
Reuse `build_annex_g_section(db, school_year_id, grade, section, term_order)` and its existing grade/attendance services. Do not calculate a separate set of term grades in the renderer.

| Form field | Source / behavior |
| --- | --- |
| Name, LRN, sex | Matched learner Person record; preserve LRN as text |
| Age | Existing school-year age calculation; retain the existing open local age-rule confirmation |
| School year, grade, section | Verified LearnerEnrollment and selected SchoolYear; never current mutable placement as historical fallback |
| School header | Validated school profile: name, region, division, district, municipality/city, province; existing school ID stays metadata unless a matching field is approved |
| Adviser | SectionAdviserAssignment for the selected school year and section; missing/ambiguous assignment blocks release |
| School head | Existing year-specific school-head setting; missing required identity blocks release |
| Subjects / learning areas | Assigned learning areas for this year/section, arranged in reference order using stable codes/explicit aliases; extra assigned electives follow as real rows |
| Terms 1–3 | Matching finalized/locked gradebook reported grades, through the selected term only |
| MAPEH | Existing combined result plus Music and Arts and Physical Education and Health subrows; count parent once in General Average |
| Final Grade / General Average | Existing decimal-safe annual calculation after all three terms; otherwise blank |
| Remarks / descriptors | Existing approved grading-policy mapping, with final display-copy verification |
| Monthly attendance | Existing instructional-day/enrollment-aware service: class days, present, absent; selected year through released term, including reconciled totals |
| Term comments | AnnexGTermComment for this enrollment/term; future terms blank |
| Parent/guardian signatures | Blank lines for signing; never synthesize signatures |
| Transfer certification / cancellation | Reproduce blank spaces and labels. Populate only independently verified values that already exist; never infer admission, promotion, or approval |

Header profile currently lacks district/location fields in the report payload, and adviser name is not returned. Add those mappings rather than rendering blank required identities unknowingly. Add LRN/name/sex and required school identity checks to release blockers. Missing term grades remain blank in a visibly marked draft; they never become zero. Unresolved attendance must not become absence.

## New interfaces
- `render_annex_g_pdf(report: dict, enrollment_id: int, *, draft: bool) -> bytes`, isolated in `backend/app/services/annex_g_pdf.py`. Renderer receives assembled data, reads no database, and writes no source grades/attendance.
- `GET /api/annex-g/preview/{enrollment_id}/pdf?term_order=1..3`: authorized admin, assigned adviser, or Records Officer; returns application/pdf. Draft PDF has a DRAFT watermark, with blockers presented in the UI. Do not place blocker prose over official form cells.
- `GET /api/annex-g/school-profile` and `PUT /api/annex-g/school-profile`: administrator only; validated bounded text fields persisted under existing `annex_g.school`. Do not add an arbitrary filesystem-path or URL field for assets.
- Existing `POST /api/annex-g/release/{enrollment_id}` keeps its request/JSON response and Records Officer-only authorization; newly registered artifact is PDF.
- Existing `GET /api/annex-g/releases/{report_id}` keeps access checks and SHA-256 verification. Serve new PDF files with application/pdf and inline filename; continue returning archived HTML as text/html. No regeneration on download.
- Existing general generated-report history remains compatible with PDF artifacts; do not grant teachers generic report-history download access.

## Review, release, and download
Admin configures school metadata. Assigned adviser reviews the draft and saves comments. Records Officer resolves required-data/layout blockers and releases. Released bytes contain no DRAFT mark, are registered with filename, template version, paper size, enrollment/year/term context, generator, timestamp, hash, and release status. Existing HTML records remain immutable and accessible. A new release supersedes only the same enrollment/term version and preserves prior bytes. Generation errors must not supersede a good report.

The Reports workspace gains Preview PDF, Release PDF (Records Officer only), and Download PDF for authorized saved releases. Draft preview does not register a released report. Release and download actions remain separate: downloading an existing release must not generate another version. Preserve comments across preview/download interactions. Teacher access remains adviser/year/section scoped.

## Implementation boundaries and open decisions
ReportLab is the selected implementation choice; exact compatible version and licensed font source are verified during dependency setup and pinned. No installation in this planning task. New dependency is required by the explicitly requested backend PDF capability and supersedes the old HTML-only plan constraint.

Initial scope excludes batch/section PDF export, SHS, editing grades/attendance in Reports, digital signatures, and inferred transfer approvals. Paper size and clear descriptor/branding source remain acceptance inputs, not guessed user approvals. Existing descriptor/age policy is not reinterpreted as part of a layout change.

## Acceptance evidence
- Test matching year/section/learner/term mappings, both grading modes, annual rounding, MAPEH once, electives, and future-term blanks against existing gradebook output.
- Test missing identities, incomplete grades, unresolved attendance, unauthorized access, release failure, immutable reissues, legacy HTML delivery, wrong hash, and layout overflow.
- Parse generated bytes as a real PDF; assert one page, expected page dimensions, and exact synthetic field values. Use pypdf for structural/text checks and Poppler-rendered PNGs for actual layout review.
- Render Terms 1, 2, 3 plus long names, long comments, accented names, all school-year attendance months, and extra subjects. Visually verify every region, wrapping, signatures, logos, and clipping.
- Run frontend lint/build, targeted Annex G tests, then backend regression suite. Use isolated synthetic data; no changes to real learner records or existing released files during QA.
