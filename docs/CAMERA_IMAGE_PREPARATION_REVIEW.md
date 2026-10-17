What changed: Anti-spoof inference now uses the matching YuNet-verified human face box with the reference demo's 1.1 horizontal and 1.05 vertical expansion. It previously used the tight, independent Haar box. The LBPH identity/duplicate crop remains unchanged. One human detection still authorizes at most one candidate.

Evidence: The user reported a visible live preview at 960 x 720, 30 fps, with live scores 0.006–0.762 and 19/20 frames below 0.6. This establishes presentation-check rejection, not a camera hardware fault or a proven cause of the low scores.

Verified preparation mismatch: The reference detector expands its box before anti-spoof inference; EduScan omitted that context and used a different detector's box. This correction removes that mismatch. It is a candidate fix for the reported rejection, not an empirically verified accuracy improvement.

Reference sources:
- https://github.com/kprokofi/light-weight-face-anti-spoofing/blob/master/demo_tools/wrapers.py
- https://github.com/openvinotoolkit/open_model_zoo/blob/master/models/public/anti-spoof-mn3/README.md

Unchanged: Integrity-checked bundled ONNX weights, 128 x 128 RGB input, cubic resize, channel means/scales, real-class output index 0, minimum live score 0.6, all-frame rejection on failed presentation scores, blink verification, human verification, duplicate checks, staff assistance, and attendance rules. No alternate-crop retries, score averaging, or best-score selection were introduced.

Validation: 78 isolated biometric/enrollment tests and 10 legacy smoke tests passed. New regressions verify exact expanded color input, image-boundary clipping, invalid-box rejection, and use of the matching human detector box. Existing regressions cover replay rejection even with a blink, independent group checks, a single failing frame blocking enrollment, database write prevention, and unchanged database/sample snapshots during Camera Test. Tests used synthetic data and isolated SQLite, never Supabase or physical camera capture.

Limit: Matching preprocessing does not prove unchanged attack acceptance rates. Fresh live, printed-photo, and screen-video comparisons on the actual camera remain required. Until those pass, use Camera Test only for validation; do not treat this as a certified anti-spoof system. No real attendance, SMS, reviews, enrollments, or camera frames were saved by these tests.
