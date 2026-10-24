# MAPEH learning-area gradebooks

## Approved decisions
One MAPEH workspace contains two independent gradebooks per term: Music and Arts, and Physical Education and Health. Each uses WW20%, PT60%, Examinations20%; the examination component uses ST1 30%, ST2 30%, TE40%. Existing combined MAPEH records remain preserved as read-only legacy records; new area records start empty. No scores are copied, inferred, split or reweighted.

## Intent
Match the supplied MUSIC AND ARTS AND PE-HEALTH - Grade 7-10 Class Record.xlsx in the website and exports for JHS. Preserve academic history, access restrictions, existing unrelated subjects and scores.

## Approaches
1. Separate subjects shown independently: simpler but fails the agreed single MAPEH workspace.
2. One workspace with two linked gradebooks: selected; independent scores and finalization while retaining familiar subject assignment.
3. Duplicate combined scores into both areas: rejected because it invents area results.

## Structure and access
Keep the existing MAPEH subject and teaching assignment as the parent authority. Add an explicit learning-area discriminator to gradebooks and their unique context key, rather than inferring area from subject-name text or creating unrelated teaching assignments. Valid new area values are Music and Arts and PE and Health. Existing records keep their IDs, context, score/item rows, original policy and status; an explicit legacy marker supplies read-only behavior without rewriting their original workflow status.

Teachers assigned MAPEH for the selected school year/section access both area tabs. Administrator, principal and records officer retain their existing read permissions; score edits remain teacher-only under current rules. All mutation routes, including reopen, score/criteria adjustment application, assessment setup, finalization and legacy compatibility routes, reject changes to marked legacy records. Legacy records remain viewable in a distinct history view and downloadable as legacy records under existing export permissions, never counted as either new area.

## Gradebook behavior
Show Music and Arts and PE and Health tabs within MAPEH, using the same continuous learner roster and per-area WW/PT/Exams tabs. Each area stores its own activities, maxima, scores, policy snapshot and workflow. Changing area uses the existing unsaved-edit safeguard; edits cannot leak to another area. Opening/initializing new records must be idempotent for year, term, section, parent subject and area. Use saved template transmutation rules consistently with the approved examination calculation; teacher cannot choose another policy accidentally. Existing future-facing policy defaults for unrelated subjects remain unchanged.

## Combined grades and exports
A combined term grade is the template's ROUND(AVERAGE(Music-and-Arts term grade, PE-and-Health term grade),0), available only when both areas are complete and finalized/locked. The annual final grade uses the template's rounded average of all three combined term grades, blank until all three are available. Missing areas are never treated as zero or copied from the other area.

Use the exact supplied workbook, preserving styles, merged cells, print settings and formula structure. Explicit area metadata maps records to TERM n M and A and TERM n PE and H. A single-term export fills only that term's two sheets; Terms1-2 fills four sheets; All3 fills six. Both area gradebooks for every requested term must satisfy the existing completeness/finalization gates. FINAL GRADES shows only complete requested term pairs; annual grade stays blank for partial exports. Match context by school year, grade, section, parent subject and authorized assignment; never mix teachers' unrelated MAPEH records. Respect existing export role permissions and current per-term/combined button placement.

## Live-data boundary
First implement and verify with isolated copies. Produce a reviewable list of existing MAPEH records proposed for the legacy marker, their preserved grades and planned empty area records before applying a live migration. Do not finalize any real record. No live migration is authorized by design approval alone; show impact and obtain approval before applying it. No deletes or automatic score conversion.

## Verification
Test Grade7-10, each area and all three terms, unequal activity maxima, zero/perfect scores, ST1/ST2/TE30/30/40, rounding cutoffs, complete/incomplete combinations and exact template grade parity. Test single/two/three-term scope and missing-area blocking. Fingerprint old scores, policies, activities and workflow states before/after isolated migration. Test all mutation routes reject legacy writes and cross-area/cross-teacher access is denied. Verify unsaved edits on area switches. No production data edits for testing.

## Non-goals and remaining implementation choices
No SHS redesign, attendance changes, new subjects for other departments or bulk score migration. Implementation may choose marker/area field names and reuse existing policy/export helpers; it must document schema changes and rollback. Desktop spreadsheet recalculation requires a usable Excel session and must be reported separately from cached-value/formula checks.
