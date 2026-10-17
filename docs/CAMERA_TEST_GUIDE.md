# Safe camera tests

Open `http://127.0.0.1:5174/scanner/test` while signed in as administrator. Confirm the heading is **EduScan Camera Test** and the banner says **TEST MODE — no attendance, SMS, review changes, or saved camera frames**. This page has no live-recognition or enrollment button.

Use willing participants and existing authorized enrollments. Do not enroll new people merely to complete a test. Unknown people can be detected and screened but cannot pass identity recognition.

## Today: baseline and photo

1. Enable the test camera. Select **Live person**. The enrolled person should face the camera in normal lighting, then blink naturally while **Run 4-second test** captures. A useful baseline has one face, the correct name, and all camera checks passing. No attendance should be created even when the baseline passes.
2. Select **Photo**. Move the real person's face completely outside the view. Hold a clear photo of the enrolled person in the camera view; avoid glare. Run the test and keep the photo visible until the result appears. Try once with a stationary photo, then repeat with gentle movement.
3. Read the individual **photo/video check** and **liveness** results. A known face that passes every check from a photo is a failed security test. The page displays **REPLAY PASSED — protection needs review**. This still cannot create attendance.
4. If no clear face is detected or the identity is unknown, the photo was not accepted, but that does not establish the anti-spoof model's accuracy. Fix framing or compare with the successful live-person baseline before drawing a conclusion.

## Later: video and multiple people

1. Select **Video**. Keep real faces out of view. Play a clear video of the enrolled person, including natural blinks, on a phone or other screen. Run a test without glare, then repeat at another ordinary viewing angle. A blink in a video must not be treated as proof of a live person. Any **REPLAY PASSED** result needs review.
2. Select **2 people**, then **3 people**. Have the participants appear together, face the camera without overlapping, and blink naturally during capture. The result reports the maximum number of clear verified faces seen in the same frame, separately from identity matches and all-checks-passed counts. Expected detection is two or three; recognizing each name also requires that person's existing enrollment.
3. If available, test a live person beside a photo/video. Compare each person's result. A live person passing must not authorize the replay next to them.

Each run stops automatically after its capture and processing. Canceling a run never switches to live attendance. Results remain only in the current page session; reloading clears them. Keep notes of the test type, lighting, faces seen, correct/incorrect identity, presentation result, and blink result without retaining camera images unnecessarily.

## Safety implementation and checks

- A dedicated administrator-only `/api/biometrics/test` endpoint accepts up to 40 frames, bounded by the existing 8 MB upload limit. It never calls the gate attendance writer, visit tracker, SMS dispatcher, or export worker. The live endpoints retain their original limits and behavior.
- Test recognition uses request-local blink state. It neither reuses a completed live visit nor changes live blink state. Review creation/resolution is suppressed. Test camera frames are not stored.
- Test queries run on a separate database connection in a read-only transaction (SQLite also enforces query-only mode). Cleanup restores the connection before it returns to the pool. This blocks accidental test writes even if recognition code later regresses.
- The browser sends diagnostic captures only to the dedicated endpoint, checks the server's test-only response, and never falls back to a live endpoint.
- 89 isolated backend tests passed, including a successful diagnostic capture, replay rejection, three faces, unchanged rows across all mapped tables, unchanged encrypted files, preserved live blink/review state, role/upload validation, and an attempted database write being blocked. All legacy smoke and assisted-attendance checks passed. Frontend lint/build passed.
- The actual Supabase connection reported read-only during a blank-frame diagnostic check and returned to normal pool behavior afterward. All 40 table contents (row counts and fingerprints), attendance settings, and biometric settings matched the pre-test snapshot after restart and verification.
- A temporary browser harness used the real test component, synthetic canvas video, and a fake API. It verified one request per run, a prominent warning when a photo passes, a three-person summary, and refusal of a response that did not confirm test safety. The temporary harness was removed.

Physical status: the user has a photo available. The actual in-app preview returned **Permission denied by system** before any capture was submitted. The physical photo test is pending camera access; video and group tests are pending participant availability tomorrow night. Automated fixtures do not establish hardware accuracy.

If access is denied, review **Windows Settings → Privacy & security → Camera** and camera access for Codex (if listed), or the desktop-app camera setting. Microsoft documents these controls in [Manage app permissions for a camera](https://support.microsoft.com/en-us/windows/privacy/manage-app-permissions-for-a-camera-in-windows). Return to the test page and enable the preview after changing the setting. Do not run a physical test until the preview is visible.

This test tool preserves attendance rules and the assisted option. It does not certify that every presentation attack will be blocked.
