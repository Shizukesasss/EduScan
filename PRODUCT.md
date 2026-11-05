# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

School staff using a shared school operations system: administrators manage school records and operations; teachers manage assigned class attendance, grades, and advisory work; gate staff operate the camera station. Records officers, privacy officers, ICT staff, and school heads have restricted oversight or review workspaces.

## Product Purpose

EduScan supports San Jose National High School's attendance, grading, SMS notifications, and official SF2 reporting workflows. It brings gate attendance and school records into one role-based system. Success means authorized staff can carry out these workflows, review and correct records with an audit trail, and produce the school's required reports.

## Positioning

EduScan is a local-first school operations system. Browser camera frames are processed by the local API; the product does not send them to a cloud face-recognition provider. It combines attendance, grading, SMS, and SF2 reporting in a school-operated workflow.

## Operating Context

The web client communicates with a local FastAPI service. A typical gate station uses a webcam and school staff; the system can run against a local SQLite database or a configured MySQL/PostgreSQL database. SMS delivery uses an Android phone gateway on the local network. Local installations can work without internet after dependencies are installed; hosted database and cellular SMS connections have their own network requirements. Official reporting uses supplied school workbooks and roster data.

## Capabilities and Constraints

- Role-scoped workspaces support administrators, teachers, gate scanners, records officers, privacy officers, ICT staff, and school heads.
- Workflows include student and personnel attendance, face enrollment and gate recognition, schedules, attendance review and correction, gradebooks, SMS delivery tracking, official SF2 reports, administration, backups, and retention controls.
- Facial samples and recognition models are encrypted and stored outside the web root; the database stores associated records and metadata. Camera images are not sent to a cloud recognition provider.
- Face matching thresholds are provisional and are not measured accuracy guarantees. The system does not itself establish school authorization or legal approval for biometric processing.
- Attendance and grade records are governed by role permissions, workflow validation, and audit history. Official records are not silently discarded by routine retention cleanup.

## Brand Commitments

The product name is EduScan and the school identity is San Jose National High School. Preserve the existing school logo and actual school terminology when working on the product.

## Evidence on Hand

- Product behavior, setup, and deployment constraints: `README.md` and `docs/INSTALLATION.md`.
- Architecture and role-scoped workflows: `docs/PROJECT_STRUCTURE.md` and `src/App.jsx`.
- School logo: `public/logo.png`.
- Official SF2 workbook: `backend/data/templates/School Form 2 (SF2) Daily Attendance Report of Learners.xlsx`.
- School class-record workbooks: `backend/templates/` and `SHS E-Class Record.xlsx`.
- No measured recognition accuracy claims, external customer testimonials, or approval records are established by the repository; do not invent them.

## Product Principles

- Keep school workflows usable in a local-first deployment.
- Show staff the records and delivery states they need to review and act on.
- Scope actions to each user's school responsibilities and retain attributable audit history.
- Keep biometric artifacts private and outside the public web root.
- Use official school data and templates; communicate provisional recognition behavior without implying guaranteed accuracy.
