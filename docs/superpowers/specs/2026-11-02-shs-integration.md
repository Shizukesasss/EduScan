# SHS grading integration

Integrate upstream EduScan commit `5dc93e29` with this checkout's current, uncommitted work while preserving existing attendance, scanner, Administration, SF2, and launcher behavior. The upstream SHS grading, validation, class-record exports, templates, and schema changes should work together in the integrated system.

Use an isolated branch. Keep secrets, biometric artifacts, and generated demo reports out of Git. Check migrations on an isolated database before considering the shared Supabase database. Verify backend and frontend tests, builds, and the relevant export and workflow paths. Do not push or migrate the shared database as part of integration verification.
