What this change does: Camera Test now shows the actual camera resolution, reported frame rate, live-face score range, and failed-frame count under Capture details. These numbers exist only in the test response and page memory; no camera images or test records are saved. This update diagnoses the reported false rejection; it does not claim to resolve camera-specific accuracy yet.

Scope: Enrollment validation, its callers, the read-only camera-test endpoint, the shared warning formatter, and scanner UI. Expected load is one local camera station, with group recognition supporting up to ten faces; enrollment remains one person at a time.

**Should fix — resolved**

1. **The warning hid whether one frame or the whole capture failed** (`backend/app/services/biometrics.py`, `backend/app/main.py`, `src/services/enrollmentFeedback.js`).
   - **What this is:** Every human-verified enrollment frame receives a live-face model score. A score below 0.6 rejects the entire enrollment capture.
   - **Problem:** Fourteen passing frames and one score of 0.599 produced the same generic warning as an entirely rejected capture. The user could not distinguish a brief bad frame from consistently poor model results.
   - **Fix:** Return score extrema, failure counts, and the unchanged cutoff only from the read-only test path. Show them with camera resolution and frame rate in Capture details; preserve the friendly main warning.
   - **If we skip it:** Repeated retries or hardware replacement would be guesswork, and a threshold change could hide the real problem.

Verified protections:

- RGB channel order, per-channel normalization, and output class order match the [original-model contract](https://github.com/openvinotoolkit/open_model_zoo/blob/master/models/public/anti-spoof-mn3/README.md). The model file is integrity checked.
- The live-score cutoff stays at 0.6. The [upstream demo](https://github.com/kprokofi/light-weight-face-anti-spoofing/blob/master/demo/demo.py) uses the corresponding 0.4 spoof-score cutoff. Scores are model outputs, not measured accuracy for this camera.
- No score averaging, rejected-frame forgiveness, alternate-crop acceptance, or disabled blink/replay checks were added.
- No attendance writer, SMS dispatcher, model trainer, enrollment saver, or recognition-review writer is called by the new diagnostics.
- Camera Test retains its separate read-only connection and rollback. Existing enrollment and attendance policies are unchanged.

Validation:

- 53 isolated biometric tests passed, including replay rejection, duplicate checks across all enrolled roles, group test safety, and database write prevention.
- A new regression verifies that a single frame at 0.599 or 0.01 still blocks a capture containing fourteen passing frames, while reporting the exact score range. All database snapshots and encrypted sample files remain unchanged.
- Six frontend message tests passed. Lint and production build passed; the existing bundle-size advisory remains.
- The local API was reloaded and the updated test page was confirmed reachable.

No hardware fault is established. Consistent low scores could reflect model mismatch with camera images; an isolated low score could reflect a transient capture. The user's next live test is needed to distinguish these cases. Neither diagnosis can be established from the earlier warning screenshot alone.

Verdict: Ship.

This verdict covers the diagnostic update only. It does not certify that the reported live-face rejection is resolved.

Not checked: Fresh live-person, printed-photo, and screen-video captures on the user's physical camera. No new camera frames were saved for this review.
