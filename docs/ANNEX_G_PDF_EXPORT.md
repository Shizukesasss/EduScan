# Annex G PDF export

EduScan generates a real one-page A5 landscape PDF per learner, using the supplied Annex G two-column form reflowed to landscape A5 with compact line spacing. It runs locally with ReportLab; no browser print settings or external conversion service is required.

## Setup

Install the pinned backend requirements (`backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt`) and restart the API. The renderer includes Noto Serif fonts and the report emblems under `backend/resources/annex_g/`; font license and asset provenance are included there.

Annex G automatically uses the school's confirmed identity: San Jose National High School, Region V, Schools Division of Albay, 1st District, Malilipot, Albay, School ID 301875. The school-details form has been removed. Existing administrator-only profile API settings remain compatible, with non-empty saved values taking precedence over these defaults. The school head and adviser still come from the selected school year's administration records. The clean school emblem is the image supplied by the user.

## Preview, review and release

1. Select school year, Grade 7–10, section and Term 1–3.
2. Review source-data blockers. Grades come from the matching finalized/locked class records; attendance comes from reconciled attendance and verified school-year enrollment.
3. An assigned adviser can save term comments. **Preview PDF** includes saved comments and a DRAFT watermark, without creating a release.
4. Only a Records Officer can **Release PDF** after all required data is complete. The released artifact is saved with its checksum and report context.
5. **Download PDF** downloads that exact saved snapshot. Downloading never creates a new version. **Open previous report** remains available for old HTML snapshots.

Future term grades, comments and annual results remain blank until applicable. At Term 3, Final Grades and General Average reuse existing calculations. MAPEH appears with both component areas but counts once in General Average. Student DOB is never shown in the PDF or report payload. Signature lines and unverified transfer/admission approvals stay blank.

## Form fidelity and overflow

The form follows Annex G from the user's reference, excluding the source page's introductory paragraph and page number. Layout was checked against PDF page 51 (printed page 48) of https://www.deped.gov.ph/wp-content/uploads/DO_s2026_015r.pdf. Performance-descriptor wording was verified visually against that source, preserving the existing approved calculation policy. This feature does not resolve the prior open local-policy confirmation of the age reference date.

Long names and subject labels wrap; wrapped learner names receive extra space before the underline and the following identity fields reflow to preserve separation. Learner-field underlines begin directly after their labels. PDF text is searchable. Unsupported glyphs or content that cannot fit the one-page form return a specific layout error. Long comments must be shortened rather than silently clipped. Missing grades are not converted to zero, missing attendance is not inferred as absence, and no transfer eligibility is invented. Export covers Grades 7–10; SHS and batch export are outside this release.

## Compatibility and API

- Draft PDF: `GET /api/annex-g/preview/{enrollment_id}/pdf?term_order=1..3`.
- Release: existing `POST /api/annex-g/release/{enrollment_id}?term_order=1..3`; JSON interface retained, new artifact is PDF.
- Saved artifact: `GET /api/annex-g/releases/{report_id}`; verifies access and checksum, returning application/pdf for new files or text/html for archived HTML. Responses are private/no-store.
- Admin profile: GET/PUT `/api/annex-g/school-profile`.

Releasing again supersedes only the same enrollment and term; prior bytes remain available. Rendering/registration failures roll back the new release and preserve the previous report. Report generation does not edit source grades, gradebook states, attendance, or enrollment.

## Verification

Focused tests: `backend/.venv/Scripts/python.exe -m unittest discover -s backend/tests -p "test_annex_g*.py"` (use an environment that permits local sockets for HTTP tests). Developer PDF checks use pypdf; visual checks render sample files with Poppler. Synthetic examples for Terms 1–3 are under `output/pdf/` and carry a DRAFT watermark. They are not real learner reports.

## Existing class-record learners without enrollment history

The report workspace can also display learners with saved score entries in the exact selected school year, section and term when no placement exists for that year. They are explicitly draft-only, with a pending-enrollment notice. Current mutable profile fields are not used to infer historical membership or enrollment dates. A learner already verified in another section that year is not silently reassigned.

These draft rows show finalized/locked term grades using the existing grade service. No attendance is inferred, and no enrollment is written by viewing or previewing. Draft PDFs carry the DRAFT watermark. Administrators can use **Verify enrollment** to open the existing confirmation form for that learner; a real start date and confirmation are still required. After saving, the report refreshes to the verified enrollment. Teachers cannot save comments for these provisional rows, and official release accepts only persisted verified enrollments.

Initial selection prefers the current populated school year and classes with saved grade evidence. Empty sections no longer precede populated report classes. The separate placement-review form still exposes the full authorized academic structure. A year touching thirteen calendar months (e.g. May to the following May) keeps both months, with year labels, on the A5 form.
