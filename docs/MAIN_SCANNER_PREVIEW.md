# Main scanner preview

Open `/scanner?preview=1` as an administrator. The main scanner keeps its camera,
start, pause, restart, group identity, and configured blink behavior, labeled
**Preview only**. It sends captures exclusively to `/api/biometrics/recognize-preview`.
Normal `/scanner` retains its attendance behavior.

The preview endpoint uses the existing recognition helper on a separate read-only
database connection, with isolated blink state and no review writes. It never
calls attendance, visit tracking, SMS dispatch, enrollment, or training. Captures
are processed in memory. Enrollment and assisted-attendance buttons are disabled
in preview. Results remain in page memory until leaving or reloading. Missing or
unsafe response flags stop recognition; there is no fallback to a writing route.

Validation: 12 isolated identity/preview tests and 12 gate regression tests passed;
frontend lint/build passed with existing memoization and bundle-size warnings.
The preview test exercises the real endpoint with two synthetic identities and
open/closed/open eye observations, compares every database table and biometric
file before/after, and verifies attendance, SMS, review, training, and visit
tracking are not called. An intentional database write is rejected. A frontend
self-check verifies the preview-only request, 40-frame capture, and fail-closed
response handling.

Fresh two-person camera accuracy still needs the user's physical test. Photo/video
protection remains disabled following the earlier requested rollback; this preview
does not establish resistance to replay attacks.
