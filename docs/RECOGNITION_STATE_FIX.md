Read-only live inspection confirmed two authorized, active enrollments: Markie has 20 samples and Bryani has 16. The active model's in-memory YAML label counts match these 36 samples. No new captures, attendance, SMS, reviews, files, or model training were created for that inspection.

Verified code defects and corrections:
- Pause retained the previous result panel, and Start retained it while waiting for a new response. Both now replace the panel with a neutral status. Restart already replaced it; generation checks still ignore older requests.
- A recognition burst accumulated named identities from earlier frames, even after the person left the view. It now returns only the latest frame's identities; prior results serve blink continuity only. A final frame with no face clears earlier matches.
- When two detected faces predicted the same label, the first could receive that identity and the second became unknown. Both are now unrecognized with an explicit ambiguity warning. No second-best identity is forced. Independent group identities remain supported.
- A non-advancing/paused video could submit repeated old frames. The browser now blocks such a burst before sending it and asks to reconnect. Live results also show unknown-face explanations instead of hiding them.

No attendance rules, thresholds, enrollments, scores, or saved attendance were changed. The previously authorized rollback of photo/video checks remains in effect. Camera Test still uses its read-only connection and isolated blink state, without attendance/SMS/review/frame writes.

Validation: Four new regressions cover departed identities, an empty final frame, same-label collisions, and independent two-person recognition. The 46-test biometric suite passed after correcting the no-write group fixture to explicitly simulate out-of-range unknown faces; it no longer assumes arbitrary random pixels must be out of LBPH range. Other enrollment tests passed in the broader run, as did 12 gate tests and 10 smoke tests. A browser-flow self-check verified that frozen video makes no API request and Pause clears the previous identity. The frontend production build passed; the existing memoization lint and bundle-size warnings remain.

Limit: These changes resolve state and collision bugs. They do not establish that fresh live Markie/Bryani captures are correctly classified. LBPH identity confusion can still occur for a single face. Verify each alone and together using Camera Test before normal attendance; no existing attendance corrections were made.
