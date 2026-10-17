# Enrollment, attendance, and camera review — 16 October 2026

Update: the approved duplicate-check, shared human-verification, legacy-liveness, and staff-assisted changes are now documented in [Camera fixes and validation](CAMERA_FIXES_VALIDATION.md). The camera audit below records the earlier findings before those fixes.

## Completed fix and verified cause

The live database recorded the new person at 01:39:55 Manila time and completed face enrollment at 01:39:59. The attendance closer created an Absent event at 01:40:06, backdated to the configured 00:00 cutoff. A separate LBPH gate request created a Time In at 01:40:36. The enrollment endpoint itself does not write attendance.

The scanner previously kept its recognition timer running behind the enrollment modal. Opening enrollment now pauses that loop, stops its camera stream, and waits for a pending gate request before opening the modal. Closing or completing enrollment leaves recognition paused. The user must enable the gate camera and start recognition separately. A delayed camera permission response is also discarded after the gate session changes.

Daily close now skips an absence cutoff that occurred before a person's registration when no explicit academic enrollment start date was supplied. Registration before the cutoff keeps the existing absence rule. An explicit academic start date still controls backdated roster attendance. Existing students remain subject to the school's configured attendance rules, independently of face enrollment.

An administrator can correct an accidental visit to **No scan**, clearing both displayed times while retaining the original events and a reason. Subsequent genuine scans start with Time In. Dashboard, scanner history, daily rows, and exports use the same cleared-event rule. Other people, dates, corrections, and day resets retain their scope.

Live verification: Saba, Markie B. now reports No scan with neither Time In nor Time Out. Both original events and all 20 encrypted face-sample records remain. The correction is attributed to the signed-in System Administrator. No data was deleted, and no recognition threshold, grading formula, or gradebook permission was changed.

**Configuration to review:** the school-wide absence cutoff is still **00:00**. Choose the school's actual cutoff in System Setup; this fix does not replace that policy. Midnight will still make established students due for absence closing at the start of future instructional days.

## Scoped camera audit

**What this repo does:** EduScan stores school records and grades and uses local camera frames and LBPH recognition to record gate attendance. This audit covers enrollment, detection, duplicate checks, liveness, attendance closing, and their connected views. The assumed load is one local API/scanner installation, concurrent school-workspace users, and the existing maximum of ten faces in a gate frame.

The findings below distinguish observed code behavior from accuracy that still needs real-world testing. They are recommendations; biometric settings and algorithms were not changed in this fix.

### Must fix before relying on all recognition routes

1. **The older single-frame endpoint bypasses the blink gate.**
   - **What this is:** `backend/app/main.py`'s `/api/biometrics/recognize` calls `BiometricService.recognize()` and can immediately write a gate event.
   - **Problem:** Unlike the current burst route, this path does not call the liveness verifier. This is a verified difference in the code, even though the current scanner uses the burst route.
   - **Fix:** Route legacy requests through the shared liveness-controlled path, or retire the endpoint after checking its clients. Test that a static recognized face cannot record attendance through either route.
   - **If we skip it:** A direct client can avoid the liveness requirement used by the normal scanner.

2. **Rigid landmarks and blinking can exclude people with facial differences.**
   - **What this is:** `backend/app/services/biometrics.py` requires a particular two-eye, nose, and mouth arrangement during enrollment; gate verification requires eye detections to change from open to closed to open.
   - **Problem:** Captures outside those geometric bounds fail, and a person who cannot produce the required blink sequence cannot complete that check. The code restrictions are verified; recognition accuracy for particular people with facial differences has not been measured.
   - **Fix:** Provide a supervised school-ID/manual attendance alternative using the existing audited correction flow. Test any alternative capture or challenge with consenting participants, without globally loosening validation or treating a failed capture as proof someone is not human.
   - **If we skip it:** Legitimate students may be unable to enroll or record attendance through the camera.

### Should fix and validate

3. **The multi-face gate does not use enrollment's secondary human-face detector.**
   - **What this is:** Enrollment combines Haar detection, YuNet verification, landmarks, and crop overlap. The multi-face gate calls `process_faces()` without that secondary verification.
   - **Problem:** An object that produces a Haar false detection reaches the LBPH matcher without the extra enrollment check. The path difference is verified; a real animal falsely recording attendance was not reproduced.
   - **Fix:** Verify human detections once per gate frame and correlate them with each candidate crop while preserving multiple-person support. Add negative cases for animals, objects, and face-like patterns, and confirm no attendance writes.
   - **If we skip it:** Enrollment and gate recognition have different levels of protection against false face detections.

4. **Duplicate protection needs calibration beyond synthetic test images.**
   - **What this is:** The existing duplicate check compares new samples with other consented identities, including inactive identities. It checks exact hashes, LBPH distance, spatial similarity, and agreement across at least 60% of accepted samples; unreadable saved samples block enrollment.
   - **Problem:** The test suite confirms those mechanisms using synthetic images. It does not establish how well they handle a real person's changed pose, lighting, glasses, or a similar-looking person. A real-world duplicate bypass was not reproduced in this task.
   - **Fix:** Measure duplicate acceptance and false rejection using separate capture sessions and consented school-camera data before changing thresholds. An optional second identity comparison using OpenCV's SFace embeddings can be evaluated alongside LBPH, but is not an automatic accuracy guarantee.
   - **If we skip it:** A passing synthetic test could be mistaken for a guarantee that all duplicate enrollments are rejected.

5. **Enrollment has no live-person challenge.**
   - **What this is:** Enrollment verifies human-looking frames and sample quality, but does not call the liveness verifier.
   - **Problem:** A photograph or replay can contain valid human facial features; unique crops do not prove a live person is present. The missing challenge is verified in code; a real replay attack was not performed.
   - **Fix:** Keep enrollment supervised and evaluate an accessible randomized challenge or a validated presentation-attack detector. Test printed photos and screen replays as separate negative cases.
   - **If we skip it:** Human-face detection alone may be treated as protection against photos and videos.

**Verdict:** The enrollment/attendance separation is fixed. Keep camera enrollment supervised, address the legacy liveness route, and validate accuracy before claiming that duplicate faces, animals, or replay attacks can never pass.

**Not checked:** Real-animal acceptance rates, real replay attacks, representative real-face duplicate rates, and usability for people with facial differences. This was not a fresh audit of the grading, authentication, or entire database modules.

## Practical capture recommendations

- Keep the current sample count, but capture useful variation: a clear frontal view and small left/right turns under normal gate lighting. Avoid collecting only near-identical frames. Use even front lighting and a camera height that accommodates both short and tall students. NIST identifies exposure, lighting, and camera angle as sources of false non-matches: [NIST FRTE](https://pages.nist.gov/frvt/html/frvt11.html).
- Calibrate on held-out captures, recording both wrong-person matches and missed matches. LBPH's output is a distance and its threshold controls rejection; it is not a percentage probability: [OpenCV LBPH documentation](https://docs.opencv.org/4.x/df/d25/classcv_1_1face_1_1LBPHFaceRecognizer.html).
- If LBPH remains insufficient after capture improvements, evaluate a second embedding comparison on the same data. OpenCV documents a local YuNet/SFace pipeline with aligned crops and similarity matching: [OpenCV face detection and recognition](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html).
- Treat unknown or unverifiable captures as needing assistance, not proof that a person is an animal, an impostor, or absent. Maintain a documented alternative for students who cannot use the camera. NIST's authentication guidance is a useful security reference for presentation-attack detection and non-biometric alternatives, rather than an attendance regulation: [NIST SP 800-63B](https://pages.nist.gov/800-63-4/sp800-63b.html).

## Review and validation of this change

**What this change does:** It separates face enrollment from active gate recognition, prevents absence from being backdated before registration, and supports an attributable correction for accidental scans. It preserves the underlying events and biometric samples and lets later genuine attendance work normally.

- 21 attendance/roster/reporting regression tests passed, including the midnight-cutoff reproduction, explicit enrollment dates, correction scope, future genuine Time In, and unchanged batch query count.
- 21 duplicate/enrollment tests passed, including encrypted-sample persistence, duplicate rejection, human-detector failure, and enrollment/re-enrollment producing no attendance events.
- 10 gate/visit tests and 10 legacy smoke tests passed. Isolated test records were used; the smoke suite did not run against Supabase.
- Frontend lint and production build passed.
- An isolated browser page loaded the actual scanner and enrollment components with synthetic canvas video and a fake API. After three deliberate fake recognition requests, enrollment stopped the gate stream and waited for the pending request. Capturing 20 enrollment frames and closing enrollment left the request count at three and both video streams stopped.
- Live Supabase and the signed-in administrator view confirmed the audited No scan correction, with two raw events and twenty face samples retained. The API was restarted successfully.
- Verification also repaired a stale removed-sort-field argument in startup/demo seeding and supplied a missing academic fixture in the legacy smoke test. No seed/demo script was run against live data.

No additional defects were found in the reviewed fix. **Verdict: Ship the attendance fix.** The separate camera findings above remain recommendations, not completed biometric upgrades.

**Not checked:** Hardware accuracy, representative facial-difference testing, and the already accepted server request being undone. Previously submitted gate requests can complete; this fix stops future requests and drains the current one before opening enrollment, with a 30-second client timeout.
