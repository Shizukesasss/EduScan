# Camera fixes — 16 October 2026

Follow-up: mandatory local presentation checks for photo/video risk and independent multiple-face validation are documented in [Photo/video protection](PHOTO_VIDEO_PROTECTION.md). The validation below records the earlier camera fixes before that follow-up.

Implemented the three camera changes approved after the enrollment/attendance review. No attendance cutoff, calendar rule, visit/cooldown rule, grading formula, account permission, database schema, or biometric runtime setting was changed. Existing records and encrypted face files were preserved.

## Duplicate enrollment

Exact sample hashes still reject a reused face immediately. For new captures, the existing LBPH distance threshold and spatial-similarity threshold remain unchanged. The matcher now checks every qualifying stored identity instead of only the nearest texture match. Three distinct captures must agree on both LBPH and spatial similarity to reject a duplicate; this also prevents an already enrolled face from being hidden among mostly different captures. Matching stops as soon as that requirement is met.

Checks still include inactive identities with authorized samples, exclude the person's own samples during authorized re-enrollment, and block enrollment when existing encrypted samples cannot be read. The transaction and enrollment lock remain in place. No active gate model is changed by the duplicate check.

This is a stricter duplicate policy, not a measured accuracy claim. A similar-looking person could be rejected, and changed pose or lighting could still hide a duplicate. Validate with separate, consented capture sessions before tuning thresholds. SFace and a new identity model were not added without representative validation data.

## Human verification and recognition routes

Enrollment, single-frame recognition, and multi-face recognition now share the bundled, integrity-checked YuNet detector and the existing landmark/overlap checks. YuNet runs once per frame. Each candidate crop needs its own corresponding verified detection; an unverified crop never reaches LBPH. Multiple verified people remain supported, up to the existing ten-face limit. Missing or broken detector files stop camera processing instead of bypassing verification.

The older `/api/biometrics/recognize` endpoint now uses the same liveness-controlled attendance path as `/api/biometrics/recognize-many`, while retaining its single-result response and single-person restriction. It also reports liveness status. The blink challenge requires open–closed–open eyes, including when the first observation has closed eyes. Challenges are isolated by station and person, expired state is removed, and a previously recorded visit retains the existing hold behavior. The configured administrator liveness setting is respected.

## Assisted option for facial differences

- In **Enroll person**, select **Register without face samples for staff-assisted attendance**. This saves only the school record using the existing registration API. It does not collect face samples, train the model, or record attendance. A delayed camera permission result is discarded if the mode changes or the dialog closes.
- In **Attendance**, use **Assist** beside a registered person. Authorized staff must check the school ID or official roster in person, enter the verified arrival/departure times, choose Present or Late under the existing school rules, and provide a reason. Do not record medical details.
- Assistance uses the existing attendance correction and audit trail. The server requires identity confirmation, an active school record, arrival time, valid time order, and a specific reason. Admin access and assigned-adviser access are unchanged; scanner accounts cannot write corrections. Original gate events remain intact.
- The scanner explains the alternative and gives administrators a shortcut to Attendance. It pauses and drains active recognition before leaving for assistance. Existing registered people can use assistance without replacing their face samples or changing consent settings.

## Validation

- 29 biometric/enrollment tests passed: exact and recaptured duplicates, mixed datasets, non-nearest identity comparisons, distinct identities, preservation on failed re-enrollment, detector failure, per-frame human matching, both public recognition routes rejecting objects, full blink sequences, station separation, and expiration.
- 24 attendance tests passed, including assisted validation, account/adviser restrictions, correction attribution, preservation of original events, midnight registration behavior, roster/reporting, and Time In/Time Out behavior.
- 11 gate/visit tests passed, including legacy liveness, visit holds, multiple people, and durable attendance writes.
- All 10 legacy smoke tests passed against isolated local databases. They did not reset or restore Supabase.
- Frontend lint and production build passed. The existing bundle-size advisory remains.
- An isolated browser page used the actual registration and attendance components with a fake API. Camera-free registration sent only `/persons` with biometric consent false; a valid assisted visit sent only `/attendance/corrections` with explicit assistance and identity confirmation. Empty assisted submissions produced no request. The temporary test page was removed.
- The running API was restarted, responded healthy with PostgreSQL, and advertised the new assisted payload and legacy liveness fields. The signed-in administrator's live Attendance page showed the Assist controls without submitting a live visit.
- Read-only Supabase checks before and after restart confirmed unchanged counts: 3 persons, 5 users, 20 biometric samples, 1 model, 14 attendance events, 1 correction, 57 gradebooks, and 0 student scores. Attendance and biometric runtime settings matched exactly; no pending migrations or restore were applied.

## Review and limits

What this change does: it applies consistent camera validation and liveness across recognition routes, strengthens duplicate comparisons, and gives authorized staff an attributable alternative to biometric attendance. Connected callers, registration callbacks, API responses, tests, and existing attendance correction permissions were checked. No unresolved defect was found in the scoped change.

Verdict: Ship these fixes for supervised use.

Not checked: actual school-camera latency and accuracy, representative real faces and facial differences, real animals, printed photographs, or screen replay attacks. Human-face detection and a simple blink check do not guarantee resistance to photos or video. Keep enrollment supervised; do not treat a failed camera check as proof that someone is not human or should be marked absent.
