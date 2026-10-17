# Attendance photo/video protection and multiple faces — 16 October 2026

## Changes

Both attendance recognition endpoints now require a separate photo/video presentation check for every human-verified face. This uses the bundled, integrity-checked `anti-spoof-mn3` model locally through the installed OpenCV runtime. Camera frames are not sent to an external service. LBPH still checks identity, and the configured blink challenge remains separate.

The presentation check is mandatory even if blinking is disabled in the existing settings. Missing, corrupt, or unusable anti-spoof model files stop camera attendance; the system does not silently skip protection. Station readiness checks the required model. Staff-assisted registration and audited attendance remain available without a camera.

A rejected or missing presentation score blocks that identity's attendance. Its blink progress is discarded. Within one capture burst, the lowest presentation score controls the result, so a rejected frame cannot be hidden by a successful blink or later accepted frame. A fresh capture can retry normally. The common attendance writer independently checks the presentation result before any visit hold or new event.

The existing maximum is **ten faces per frame**. Each distinct recognized identity must pass independently. Two live, recognized people can both complete their checks in one capture; a rejected presentation for one identity does not approve or block another identity. Enrollment remains restricted to one person at a time.

The scanner explains multiple-person use and shows photo/video rejection feedback even while another person's visit is already saved. It uses neutral wording and offers staff assistance rather than labeling a failed capture as an impostor.

Attendance dates, schedules, Present/Late rules, Time In/Time Out alternation, cooldown and visit boundaries, school records, grading formulas, account permissions, and assisted corrections were preserved. No database schema or saved biometric runtime setting was changed.

## Model and limits

- [Official model documentation](https://github.com/openvinotoolkit/open_model_zoo/blob/master/models/public/anti-spoof-mn3/README.md) describes an RGB classifier trained on CelebA-Spoof, with `[live, spoof]` output.
- [Official manifest](https://github.com/openvinotoolkit/open_model_zoo/blob/master/models/public/anti-spoof-mn3/model.yml) supplies the download, input contract, size, and checksum. Downloaded bytes were verified against its SHA-384; runtime verifies SHA-256. The MIT license is bundled.
- Tight color crops are resized to 128×128 with cubic interpolation, converted to RGB, then normalized with the documented per-channel mean and scale. Grayscale LBPH crops are not used for this check.
- Acceptance requires a live score of at least 0.6, corresponding to the [upstream demo's 0.4 spoof cutoff](https://github.com/kprokofi/light-weight-face-anti-spoofing/blob/master/demo/demo.py). This is a model decision score, not measured school-camera accuracy.

**This is risk reduction, not a guarantee that every photo, screen replay, deepfake, or mask will be rejected.** A normal RGB webcam and this classifier are not a certified presentation-attack solution. Actual school-camera validation with separate live, print, and screen-replay captures is still required, including representative people with facial differences. Stronger assurance may require a validated solution with trusted depth/IR hardware. Keep enrollment supervised and retain assistance when camera checks fail.

## Checks

- **85 backend tests passed:** 39 biometric/enrollment/presentation, 12 gate/visit, 24 attendance, and all 10 legacy smoke tests. Isolated databases and synthetic inputs were used, not live student enrollments or attendance writes.
- New regressions verify RGB normalization, actual bundled model loading/inference, missing/corrupt model handling, invalid outputs, score propagation to each detected face, verifier-error propagation, and rejection despite a completed blink or a previously recorded visit.
- Controlled spoof-score tests confirm both public routes cannot write attendance for a rejected presentation. They test enforcement; they do not establish physical photo/video detection rates.
- Multiple-face tests use the existing LBPH matcher, independent presentation/blink observations, and the common attendance path. They cover two passing identities and a passing identity beside a rejected identity.
- Assisted-option validation, admin/adviser permissions, existing visit rules, and all legacy smoke tests remain passing. No live SMS was sent for tests.
- Frontend lint and production build passed. The pre-existing bundle-size advisory remains.
- An isolated browser page loaded the real scanner with synthetic canvas video and a fake API. It displayed separate live/rejected-face feedback, including the rejection warning while the other identity's visit was held. No hardware camera or live attendance API was used. The temporary page was removed.
- A warm local microbenchmark added approximately 141 ms for 16 presentation checks and 1,191 ms for 160 checks on synthetic crops. This excludes camera capture, human detection, LBPH, database work, and cold model loading; it is not an end-to-end latency guarantee.
- EduScan's API was restarted and returned healthy with PostgreSQL and the new presentation fields. The live scanner showed API/database and recognition readiness with its camera off, and retained the assisted-attendance control. No live attendance request was submitted.
- Read-only Supabase checks before and after restart found unchanged record counts across all 40 mapped tables, including 20 encrypted face-sample records and the existing active model. Attendance and biometric runtime settings were unchanged. No pending migration or restore was applied.

Not checked: physical printed-photo or phone/video attacks, representative real-camera accuracy, and real-world multi-person timing. Do not claim zero spoof acceptance from these tests.
