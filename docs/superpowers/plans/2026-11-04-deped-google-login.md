# DepEd Google Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admit verified DepEd Google accounts and provision teachers while preserving school-controlled privileges.

**Architecture:** Use Google Identity Services in React and google-auth verification in FastAPI. Store a unique Google subject and email on each user. Explicitly reserve existing accounts for named DepEd emails through a local setup command; bind the subject only after Google verification.

**Tech Stack:** React, FastAPI, SQLAlchemy, google-auth, pytest.

**Spec:** `docs/superpowers/specs/2026-11-04-deped-google-login-design.md` (approved).

## Global Constraints
- Exact Google Workspace domain and email domain: `deped.gov.ph`.
- New accounts are teachers, with no automatic class assignments or promotions.
- Disabled accounts remain blocked; local password login cannot bypass DepEd-only mode.
- Preserve existing unrelated workspace edits. Work inline in the supplied checkout under the user's implementation authorization; do not commit their other changes.
- Keep legacy mode during setup; explicitly enable `EDUSCAN_DEPED_ONLY=true` after linking privileged accounts. Do not change the live database or credentials during development.

## Review Focus
- Matching display names must not grant access to legacy unlinked schedules or rosters.
- Concurrent first logins cannot create duplicate identities or produce an unhandled integrity error.
- Existing local sessions must stop working in DepEd-only mode.
- Missing Google configuration or an unavailable script must produce a clear login error.
- Google accounts must not get a local password reset path that bypasses identity checks.

### Task 1: Identity storage and verified provisioning
Files: `backend/app/models.py`, `backend/app/migrations.py`, `backend/app/config.py`, `backend/app/services/google_login.py`, `backend/tests/test_google_login.py`, `backend/requirements.txt`.
Interfaces: `verify_google_credential(credential, nonce=None) -> dict`; `google_user(db, claims) -> User`; `reserve_google_email(db, username, email) -> User`.
- [x] Write tests for exact domains, verified claims, subject binding, disabled users, role preservation, collision handling, and reservation rules; run and observe failure.
- [x] Implement verification using google-auth with audience, issuer, expiry, signature, nonce and domain checks; persist unique nullable identity fields with idempotent migration.
- [x] Run identity and migration tests; expect all pass.

### Task 2: Authentication endpoints and assignment boundaries
Files: `backend/app/main.py`, `backend/app/auth.py`, `backend/app/schemas.py`, `backend/tools/link_google_account.py`, `backend/tests/test_google_login.py`.
Interfaces: GET `/api/auth/config` exposes client ID and DepEd-only mode; POST `/api/auth/google` accepts credential and nonce and returns existing LoginResponse plus auth provider. Current sessions carry their authentication method.
- [x] Write failing API tests for provisioning, invalid credentials, strict-mode password/old-session denial, Google password-change denial, and empty assignment results.
- [x] Implement endpoints, session enforcement, explicit email reservation CLI, and remove name-based authorization for Google-linked users.
- [x] Run focused authentication/authorization tests; expect all pass.

### Task 3: Login UI and deployment guide
Files: `src/pages/Login/Login.jsx`, `src/pages/Account/AccountSecurity.jsx`, `src/api/client.js`, `src/services/googleIdentity.js`, `backend/.env.example`, `docs/DEPED_GOOGLE_LOGIN.md`, `tests/google-identity.test.js`.
Interfaces: frontend obtains one backend-owned client ID; Google button sends signed credential and per-attempt nonce. Preserve legacy form only during migration mode.
- [x] Write failing tests for script-load recovery, nonce setup and role routing; run them.
- [x] Implement accessible loading/error/unavailable states, Google-managed account security, and documented admin/scanner setup and strict-mode rollout.
- [x] Run Python suite, Node tests, frontend lint/build and bounded UI review; record external live Google prerequisites and browser limitation below.

## Execution ledger
- Ruling: Execute inline without another approval round, following the user's explicit instruction to implement the approved design.
- Ruling: Keep this feature uncommitted because the supplied checkout contains substantial unrelated edits and `.git` is read-only in this environment.
- Pre-flight: Tasks 2 and 3 consume Task 1's identity verifier and the backend configuration endpoint; frontend uses backend configuration rather than a duplicate Vite client ID.
- Task 1: complete. Identity validation, reservation, migration and provisioning verified in disposable databases.
- Task 2: complete. New API, strict-session enforcement, linked-account restrictions, assignment isolation, and actual setup CLI verified. The race test models a competing committed identity and re-reads it after the unique conflict.
- Task 3: complete. Google button loader, retry/timeout and nonce tests pass. Existing design retained; missing configuration shown in both rollout modes. Account management displays DepEd email and hides unsupported local password actions.
- Final focused verification: 30 login tests passed, including real RSA signature/audience/issuer/expiry/nonce verification with only certificate HTTP responses replaced. 18 Node tests passed. `npm run verify` and `git diff --check` passed; build retains the existing large-bundle warning.
- Full backend regression run: 576 passed, 3 failed, 244 subtests passed (the run began before six additional login tests were added; the final 30-test login run includes them). Failures: `test_verify_liveness_passive_success`, `test_verify_liveness_passive_fail_no_variation`, and `test_verify_liveness_off` in `backend/tests/test_biometrics_pipeline.py`. These existing untracked tests pass outdated positional arguments to `BiometricService.verify_liveness`, treating the frame list as its configuration dictionary. Confirmed independently with the biometric test file alone; no biometric implementation was modified for this feature.
- Independent review: both P2 findings resolved: missing Google configuration now always explains unavailability; Accounts config failure now uses local error state instead of a changing parent callback that could cause repeated requests/toasts.
- Visual limitation: two bounded attempts to open the localhost preview in the browser tool timed out before rendering; visual desktop/mobile verification could not be completed. Temporary mock and preview servers were stopped. No live Google login was attempted without an OAuth client and DepEd identities.
- Rollout limitation: actual `GOOGLE_CLIENT_ID`, authorized origins and named admin/scanner DepEd addresses are still required. Live database/account linking and enabling strict mode were deliberately left for that configured rollout, as approved in the design.
