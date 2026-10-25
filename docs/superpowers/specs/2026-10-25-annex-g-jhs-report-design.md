# Annex G electronic learner report for Grades 7–10

**Status: Approved to implement by the user on 2026-10-25.** The user selected the adviser-draft and Records Officer release workflow and instructed implementation. The first-Friday-of-June age reference remains subject to local Schools Division confirmation.

## Goal

Provide an EduScan workflow for preparing and releasing the DepEd Annex G performance report for Grades 7–10. The report must use school-year-scoped enrollment, finalized grades, reconciled attendance, and verified learner details. EduScan must not create or guess academic or personal data to fill gaps.

## Confirmed Annex G content

The supplied [DepEd Order 015, s. 2026](https://www.deped.gov.ph/wp-content/uploads/DO_s2026_015r.pdf), Annex G (PDF page 51 / printed page 48), includes these report areas:

- School identity and school year; learner name, LRN, age, sex, grade, and section.
- Learning-area results for Terms 1–3, Final Grade, and Remarks; MAPEH is shown with Music and Arts and Physical Education and Health subareas; General Average.
- Monthly attendance totals, teacher comments/recommendations for each term, and parent/guardian signature spaces.
- Certificate of Transfer and cancellation-of-transfer sections when applicable.
- Performance descriptors and corresponding grade ranges from the Annex G template: 90–100 Advancing, 80–89 Benchmarking, 75–79 Connecting, 65–74 Developing, and 0–64 Emerging; remarks show Passed or Failed as printed in Annex G.

The requested first release covers Grades 7–10 only. It excludes the SHS Track field and Grades 11–12.

## Age rule and DOB handling

Annex G labels the field **Age** but does not state a reference date. The existing [DepEd E-Class Record manual for Grades 7–10](https://www.deped.gov.ph/wp-content/uploads/2018/08/The-Electronic-Class-Record-User-Manual-for-Grades-7-10.pdf) uses **age as of the first Friday of June**. The report should calculate age on the first Friday of June in the selected school year, subject to confirmation that the Schools Division has not issued a different local rule.

Date of birth stays administrator-only. Teachers and Records Officers receive only the calculated age within the report they are authorized to access. A missing DOB is a release blocker; the system must not infer an age from grade level, name, or other fields.

For the grades, DO 015 paragraph 52 defines each learning-area Final Grade as the average of its three Term Grades, rounded to the nearest whole number; 75 or higher meets the minimum standard. Paragraph 53 defines General Average as the average of the learning-area Final Grades, also expressed as a whole number. The report should apply these rules with EduScan's decimal-safe rounding. MAPEH is one learning area in General Average; its Music and Arts and PE and Health subrows remain visible as in Annex G.

Backfill existing blank DOBs only from a verified school roster or learner record. The current roster importer supports dry runs and an approval/document reference, but it updates every mapped person field; do not use it unchanged for a DOB-only request. Add a DOB-only backfill mode that matches by LRN or verified school identifier, changes only blank `date_of_birth` values, leaves existing DOBs and every other person field untouched, and audits the source hash/reference, matched learners, and administrator. Never apply a source date on a weak name-only match. Do not expose DOB in general roster exports.

## Data sources and historical enrollment

- Enrollment and section membership must come from a verified, school-year-specific roster. `Person.grade` and `Person.section` are current mutable fields and are not a historical source of truth.
- The current schema stores enrollment dates on `Person` but has no dedicated year-specific learner placement history. Add the smallest effective-dated school enrollment record needed to identify the learner’s Grade 7–10 section and enrollment interval for the selected school year. A verified official roster import creates or updates these records; do not migrate current fields into historical records by assumption.
- Read term grades only from the matching school year, grade, section, learning area, and term gradebooks after they are finalized. Reuse the existing grading-policy service, including the selected school year’s grading mode. Do not write scores, reopen gradebooks, or create a parallel subject-grade calculator.
- Read each Term Grade as the finalized value produced by that year's gradebook (including the 2026–2027 transition transmutation or 2027–2028 zero-based mode). Compute annual Final Grade and General Average using paragraphs 52–53 above; do not use a four-term rule or a separate spreadsheet formula.
- Resolve the visible MAPEH parent row from the two learning-area gradebooks using EduScan's existing MAPEH combination rules. Show both area subrows. Count the combined MAPEH Final Grade once in General Average, not the two subrows separately.
- Reuse the existing attendance/SF2 attendance source. Do not count a missing scan as an absence. Unresolved attendance days must be surfaced and block release until reviewed or closed through the normal attendance workflow.
- School identity, grading-period dates, and the assigned adviser come from the selected school year’s existing administration records.

If a required historical placement or report value cannot be verified from those sources, mark the learner report **Needs attention** and identify the missing source. Never substitute the learner’s current placement for a past school year.

## Roles and workflow

1. **Prepare:** An administrator or Records Officer selects school year, grade, and section. EduScan creates per-learner report drafts from that year’s verified enrollment roster. The draft shows missing DOB, placement, gradebook, and attendance data explicitly.
2. **Adviser review:** Only the adviser assigned to that section for the selected school year can review that section’s drafts and save term comments/recommendations. The adviser cannot edit imported grades or attendance from this screen. A teacher who is not the year-specific adviser has no report-edit access.
3. **Records review:** The Records Officer checks completeness and returns a draft with a note or releases the current term's report. Release is blocked by missing verified enrollment, missing DOB/age, missing finalized grades through that term, or unresolved attendance through that term. Terms 1 and 2 releases leave future terms, Final Grade, and General Average clearly blank; after Term 3 is finalized, the report includes the annual Final Grades and General Average. Signature and transfer fields remain printable on the report; version one does not collect electronic signatures or make transfer determinations.
4. **Administrator oversight:** Administrators manage school/report setup and can view report status and audit history. Administrative access does not silently change gradebook, enrollment, or attendance source records.
5. **Release:** Generate one print-ready Annex G PDF per learner with the exact Annex G labels and layout. Register each term release in existing generated-report history with its school-year, learner, and released-term context, creator/reviewer, SHA-256 hash, timestamp, and release status. A later term release supersedes the prior version for the current view but keeps the earlier released PDF available in history; it never overwrites the prior file.

Drafts and releases are term-by-term, matching the three parent/guardian signature lines in Annex G. A Term 2 release includes finalized Term 1 and Term 2 data. Future terms and annual values remain blank until available and cannot be represented as finalized.

## Minimal persistence

- Add effective-dated, school-year enrollment placements sourced from approved roster imports.
- Add per-learner, per-school-year Annex G draft state for term comments and workflow status.
- Reuse `GeneratedReport` for released PDF files, review metadata, hashes, and download history.

Do not duplicate grades, attendance events, dates of birth, or calculated age in the draft. Capture a released PDF snapshot so later source changes cannot silently alter the report already issued.

## Out of scope

- Grades 11–12 and SHS Track reporting.
- Editing grades or attendance from the report workflow.
- Parent/guardian accounts, digital signatures, or automated transfer decisions.
- Fabricating or bulk-filling DOBs without a verified official source.
- Changing scoring weights, transmutation, zero-based grading, or gradebook finalization rules.

## Verification plan

- Compare every rendered Grade 7–10 field and label with Annex G.
- Verify age at the selected school-year reference date, including birthdays immediately before/on/after the cutoff and missing DOB behavior.
- Verify all three term grades, annual final grades, General Average, and MAPEH values against finalized gradebooks and the approved grading calculation, including 2026–2027 and 2027–2028 policy modes.
- Verify month-by-month attendance against the normal attendance/SF2 source, including a missing scan and an unresolved attendance day.
- Verify section/year authorization for adviser, Records Officer, and administrator; verify raw DOB does not appear in teacher or general roster APIs.
- Verify release/reissue history, PDF checksum, and that source grades, attendance, and enrollment are not changed by report generation.
- Run focused backend and frontend tests, then the full backend suite; manually inspect a synthetic-data PDF. Never submit real learner data during the test.

## Open policy check

Before production release, confirm with the School/Division Office that the first-Friday-of-June age convention remains the intended Annex G reference date. Annex G itself does not define one.

Annex G's sample does not show a separate elective row. For implementation, include any JHS elective learning areas assigned to the section as their own rows and include their finalized grades in General Average (paragraph 53 says to average the learning-area Final Grades). Keep that behavior data-driven so an approved School/Division instruction can adjust it later. Do not silently omit an assigned elective grade.
