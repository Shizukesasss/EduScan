# DO 15, s. 2026 grading by class offering

Date: 2026-10-19

## Approved direction and scope

The user selected **policy by class offering**: Admin or Records Officer assigns the assessment group; the teacher sees the prescribed weights; the gradebook and XLSX use the same saved policy and grade-conversion rules. The latest instruction supersedes the earlier new-gradebooks-only choice: include existing and future Grade 7-12 gradebooks, including Finalized and Locked records, for school years to which the order applies.

This is a planning document. No application code, policy rows, score rows, or real gradebooks have been changed for this work.

## Official sources and verified references

- [DO 015, s. 2026](https://www.deped.gov.ph/wp-content/uploads/DO_s2026_015r.pdf): PDF pages 13-14 / printed pages 11-12, paragraphs 44-50 and Tables 9-10; PDF pages 38-41 / printed pages 35-38, Annex D, Tables 1-5.
- [DO 008, s. 2015](https://www.deped.gov.ph/wp-content/uploads/2015/04/DO_s2015_08.pdf): Table 5, printed page 11, used only for the Grade 12 transition explicitly required by DO 015 paragraph 49.
- DO 015 was downloaded from the official URL and the relevant scanned pages were rendered and visually inspected. The source/renderings are local working evidence under ignored `work/do2026-policy/`, not application assets or files to commit.

## Required policy catalog

Weights are percentages in **WW / PT / EX** order. Stable group IDs are stored on each `SubjectTeachingAssignment`, which is already the application's subject-section-school-year class offering. Curriculum IDs are `jhs`, `strengthened_shs`, and `legacy_shs`.

| Assessment group ID | Curriculum / learning area | Weights | Examination scheme |
|---|---|---|---|
| `jhs_academic` | English, Filipino, Mathematics, Science, AP | 20 / 50 / 30 | ST1 30, ST2 30, TE 40 |
| `jhs_tle_mapeh` | EPP/TLE and MAPEH | 20 / 60 / 20 | ST1 30, ST2 30, TE 40 |
| `jhs_values` | GMRC / Values Education | 20 / 50 / 30 | ST1 30, ST2 30, TE 40 |
| `shs_academic` | SHS core and other academic electives | 20 / 50 / 30 | ST1 30, ST2 30, TE 40 |
| `shs_field_experience` | Field Exposure, Arts Apprenticeship, Creative Production and Innovation | 15 / 70 / 15 | TE 100; no ST1/ST2 |
| `shs_arts_sports_health` | Arts, Sports, Health and Wellness electives | 20 / 60 / 20 | ST1 30, ST2 30, TE 40 |
| `shs_research_design` | Research electives and Design and Innovation | 40 / 60 / 0 | No examinations |
| `shs_techpro` | Other TechPro electives | 15 / 65 / 20 | ST1 30, ST2 30, TE 40 |
| `shs_work_immersion` | Work Immersion | 20 / 80 / 0 | No examinations |
| `legacy_shs_core` | Grade 12 transition: core | 25 / 50 / 25 | ST1 30, ST2 30, TE 40 |
| `legacy_shs_academic` | Grade 12 transition: other Academic Track subjects | 25 / 45 / 30 | ST1 30, ST2 30, TE 40 |
| `legacy_shs_academic_practical` | Grade 12 transition: Academic Track Work Immersion / Research / Business Enterprise Simulation / Exhibit / Performance | 35 / 40 / 25 | ST1 30, ST2 30, TE 40 |
| `legacy_shs_tvl_sports_arts` | Grade 12 transition: TVL / Sports / Arts and Design | 20 / 60 / 20 | ST1 30, ST2 30, TE 40 |

`jhs_values` must preserve the Annex D domain structure: WW Cognitive 10, WW Affective 10, PT Cognitive 10, PT Affective 10, PT Behavioral 30, EX 30. Neither generic WW/PT scores nor Attendance scores identify these domains automatically.

Eligibility: Grades 7-10 use `jhs`; Grades 11-12 use `strengthened_shs`; Grade 12 in SY 2026-2027 may use `legacy_shs` only when the offering is confirmed as not yet implementing Strengthened SHS. Never assume all SHS subjects have the academic weights. New subjects/electives require an explicit assessment group; familiar names may suggest a selection, but saving the offering confirms it.

SY is determined from `SchoolYear.starts_on`, checked against its displayed year label. Missing/conflicting dates or curriculum/group combinations block policy assignment/alignment with a clear message. Historical school years before SY 2026-2027 retain their applicable policies and are identified separately in coverage reports. For SY 2027-2028 onward, the same subject-group weights use direct reporting; `legacy_shs` is not offered automatically.

## Calculation and conversion contract

- WW/PT retain the existing graded-activity totals, variable item maxima, blank-versus-zero behavior, draft saving, and class-wide completeness checks. No score or status is invented.
- PS = earned raw score / applicable highest possible score x 100. WS = PS x component weight / 100. IG = sum of component WS.
- Standard EX PS = (ST1 score / ST1 maximum x 30) + (ST2 score / ST2 maximum x 30) + (TE score / TE maximum x 40). TE-only EX PS = TE score / TE maximum x 100. No-exam profiles have only WW and PT as required components.
- Existing normalized draft exam previews remain provisional. Finalization requires all examination roles prescribed by the selected profile; unused WW/PT slots remain unused under current rules.
- SY 2026-2027 uses the exact Annex D Table 4 adjusted table for all applicable Grade 7-12 offerings, including legacy Grade 12. Selected anchors: 0 -> 60, 69.99 -> 74, 70 -> 75, 71.17 -> 75, 71.18 -> 76, 80 -> 83, 99.50 -> 100. Store all published lower and upper bounds, not an approximate interpolation formula.
- Preserve the existing unrounded IG lookup semantics: choose the greatest published lower bound not greater than the raw IG. Thus 71.175 -> 75. Display IG and WS using the existing `half_up`/2-decimal behavior. Do not let floating-point gaps or displayed rounding choose a different term grade.
- SY 2027-2028 onward uses IG directly, rounded `half_up` to a whole term grade, with passing grade 75; no legacy transmutation fallback. Reporting mode must be explicit (`legacy`, `adjusted_2026`, `direct`), independent of the presence of an examination component.
- Backend results, browser previews, calculation breakdown, fixed/adaptive XLSX formulas, and cached workbook results must agree. An empty conversion table must never ambiguously mean both direct reporting and an old-table fallback.

The complete adjusted-table lower bounds below are paired with term grades 60-100 in ascending order. For storage, each band's maximum is the next lower bound minus 0.01; the last maximum is 100.00. Lookup follows the unrounded lower-bound rule above.

```text
Grade: 60    61    62    63     64     65     66     67     68     69     70
Min:   0.00  4.68  9.35  14.01  18.68  23.35  28.01  32.68  37.34  42.01  46.67
Grade: 71     72     73     74     75     76     77     78     79     80
Min:   51.34  56.01  60.67  65.34  70.00  71.18  72.36  73.54  74.72  75.90
Grade: 81     82     83     84     85     86     87     88     89     90
Min:   77.08  78.26  79.44  80.62  81.80  82.98  84.16  85.34  86.52  87.70
Grade: 91     92     93     94     95     96     97     98     99     100
Min:   88.88  90.06  91.24  92.42  93.60  94.78  95.96  97.14  98.32  99.50
```

## Storage and authority

Reuse `GradingPolicy` as the immutable saved policy snapshot: one managed version per school year/curriculum/group, referenced by each gradebook. Store group identity in its existing `subject_category`, a managed version such as `DO015-2026-v1`, component keys/examination portions in `component_definitions_json`, the official conversion table in its existing field, and an explicit `reporting_method` column. A referenced managed policy cannot be edited in place.

Extend the offering with nullable `curriculum_profile` and `assessment_group` fields. Existing offerings start unclassified; neither a migration nor page load guesses SHS groups. Add stable `assessment_key` and `included_in_grading` to gradebook components and `included_in_grading` to assessment items. Defaults preserve all existing calculations until explicit alignment. Excluded former assessments and their scores remain queryable in a read-only retained-assessments disclosure, but do not contribute to official totals, completeness, or exports.

Admin and Records Officer can classify offerings through a narrow policy endpoint. Existing teacher-assignment and school-record administration permissions do not expand. Teachers retain score/activity editing for their own open gradebooks, including activity maxima, but prescribed component identities, component weights, examination roles, and conversion rules are read-only. Admin and School Head retain read-only grade access. Existing Records Officer export, reopen, and adjustment approval permissions remain unchanged.

Both normal Assessment Setup and criteria-adjustment approval validate the managed policy. No teacher or approved legacy request may reintroduce arbitrary criteria such as a separate Attendance contribution. Pending requests survive alignment; a stale criteria request receives a clear conflict and must be reviewed/resubmitted against the new policy. Ordinary score adjustments continue to work.

## Existing gradebook alignment

Provide an explicit, repeatable maintenance operation; never recalculate the live database automatically during application startup or a GET request.

1. Produce a dry-run manifest for all target Grade 7-12 gradebooks in the selected applicable school year(s), irrespective of Draft/Submitted/Finalized/Locked status. List missing offerings, unclassified groups, incompatible structures, proposed component/item mapping, old/new grades and completeness, and historical/inactive coverage. A record is not marked compliant until its assigned and applied policies agree.
2. Preserve every existing `StudentScore` row, including IDs, assessment-item IDs, numeric values, statuses, notes/reasons, actor fields, and timestamps; preserve every existing assessment maximum and student record. Never delete components or items during alignment. Retain unsupported/extra items as excluded rather than silently redistribute their scores.
3. Standard legacy QA with one activity maps that same item to TE; add ST1/ST2 as blank activities only when required. TE-only profiles retain the TE item and exclude other exam items. No-exam profiles retain any previous exam component as excluded. GMRC/Values domains and ambiguous duplicate component mappings require explicit ID-based mapping in the reviewed manifest; never infer a domain from a numeric score.
4. Under a transaction and gradebook/offering locks, require an unchanged source fingerprint, create an encrypted recovery snapshot using the existing configured encryption key, apply the reviewed mapping, and audit old/new policy, component metadata, calculated grades, completeness, and workflow state. Save no encryption key or raw backup to Git.
5. Complete finalized/locked records retain their workflow state and receive a policy-alignment audit. If the required new assessments leave a formerly closed record incomplete, reopen it to Draft with the Records Officer's recorded reason, retaining prior finalization/locking evidence in the audit and recovery snapshot. Never leave an incomplete record described as finalized or invent missing scores. No real record is finalized by this operation.
6. Apply fails and rolls back if any target has an unresolved mapping, stale fingerprint, or score/maxima integrity mismatch. Rerunning the same successful alignment is a no-op without duplicate audit entries. Recovery restores only rows owned by the alignment and refuses if subsequent score or policy edits would be overwritten.

The first real apply occurs only after implementation tests and review of the populated dry-run report. The present request creates the spec and implementation plan; it does not apply an alignment.

## Export behavior

Gradebook -> XLSX is the direction of authority. Select a supplied template only if its saved group, examination structure, conversion, and rounding match; otherwise reuse the adaptive export. Template constants must not select or override policy. Export includes policy version/group, correct existing school details, teacher, section, learner roster, activity maxima, scores, WS, IG, and term grade. Excluded legacy data stays in EduScan/recovery evidence and does not enter official grade calculations.

Keep per-term export and Export All 3 Terms. The combined export requires all three complete, closed terms for the same offering; reject inconsistent curriculum/group/reporting method across terms rather than mix incompatible results. Each term retains its own saved assessment maxima and scored activities. Existing combined Music/Arts and PE/Health behavior and current role restrictions remain.

## Acceptance and non-goals

Use isolated databases and synthetic learners for write tests. Cover every catalog group, Grade 7-12 eligibility, both reporting years, varied maxima, all examination schemes, exact conversion boundaries, wrong-group/role/policy tampering, stale criteria requests, closed and incomplete migration, full rollback, idempotency, source-score integrity, per-term/three-term exports, and retained data visibility.

Independently recalculate representative exported workbooks with installed Excel or LibreOffice when available; inspecting only cached values is not proof of formula correctness. Report unverified external recalculation explicitly if neither is available. Live browser verification uses existing authorized accounts and no real score edits, finalization, attendance writes, or real migration applies.

Do not redesign attendance, scanning, enrollment, SF2, authentication, subject destinations, or annual/semester aggregation. Do not add dependencies. Preserve unrelated uncommitted work and stage only this feature's changes during execution. A missing school-specific classification is a visible rollout blocker, not permission to invent a grading policy.
