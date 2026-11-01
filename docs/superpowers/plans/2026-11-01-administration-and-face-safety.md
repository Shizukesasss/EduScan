# Administration and Face Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify Administration while preserving school-record creation, and prevent ambiguous face captures from creating another person's enrollment or attendance.

**Architecture:** Keep Accounts and People & Records as separate destinations. Remove roster import from the active UI and API, while retaining historical audit storage used by Annex G. Keep academic references and year-specific assignments, but explain their scope in the UI. Recognition uses SFace identity scores; LBPH remains the trained local model and audit distance. Reject uncertain identity results rather than assigning attendance.

**Tech stack:** React, FastAPI, SQLAlchemy, OpenCV, Python unittest, Vite.

**Spec:** User request in the 2026-11-01 EduScan chat, with the later clarification to retain People & records and route scanner help there.

**Constraints:** No real face dataset is available for a 50-person field accuracy measurement. Synthetic 50-identity tests verify behavior and capacity only. Never persist face features or include biometric material in Git.

## Tasks

- [x] Update Administration tabs: Accounts first, People & Records retained, school-year context clarified, roster import removed. Redirect scanner help to People & Records.
- [x] Remove roster import API routes and update affected API tests and README. Preserve Annex G imports and historical data.
- [x] Add failing tests for mixed-person enrollment and conflicting labels in one camera burst. Implement fail-closed checks.
- [x] Add synthetic 50-identity gallery and 750-sample LBPH training tests; document why they are not accuracy measurements.
- [x] Run frontend build and relevant backend tests, inspect the diff, and report the broad-suite failures and required field validation.
