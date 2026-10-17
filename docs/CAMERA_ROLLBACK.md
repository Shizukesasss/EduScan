The user explicitly chose to restore the flow before the new photo/video checks while retaining duplicate-face checks.

Enrollment no longer runs the anti-spoof classifier or requires an enrollment blink sequence. Gate recognition no longer runs the anti-spoof classifier; its earlier configured blink challenge remains. Human verification, image quality, one-person enrollment, duplicate prevention across enrolled roles, encrypted biometric storage, model integrity checks, staff assistance, attendance rules, and atomic new-person registration remain in place. Existing model/sample files and school data were not deleted or migrated.

The shared enrollment validator serves real enrollment and read-only Camera Test. Both gate recognition routes share the restored recognition service. API presentation verification and score are null, not a fabricated pass. Camera Test explicitly reports protection disabled and retains its isolated read-only database connection, local test blink state, and no attendance/SMS/review/frame-saving behavior.

Obsolete anti-spoof enforcement tests were removed with that functionality. Coverage now verifies restored enrollment without a blink or anti-spoof score, preserved duplicate rejection, independent group/legacy blink behavior, read-only testing, and legacy/group response compatibility. Synthetic fixtures and isolated SQLite were used; no real person was enrolled or recognized during automated tests.

Earlier CAMERA_IMAGE_PREPARATION_REVIEW.md and CAMERA_FALSE_REJECTION_REVIEW.md describe superseded anti-spoof work. This rollback does not resolve that model's accuracy; it removes that model from the active flow. Photo and video replay protection is consequently reduced, and a blink alone must not be treated as proof against replay.
