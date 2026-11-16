# EduScan security audit

Audit date: November 16, 2026

## 1. Security posture

**NEEDS WORK.** EduScan uses React/Vite, FastAPI, and server-side SQLAlchemy with SQLite, MySQL, or PostgreSQL. It handles learner, personnel, attendance, grade, and biometric data. The route inventory found 161 API route registrations in `backend/app/main.py` and five DTR routes. Six registrations in the main module are intentionally pre-authentication. The other registrations declare server-side authentication, including the DTR router-level requirement. Browser storage of eight-hour bearer tokens, previously provisioned demo accounts, and missing request limits before upload parsing remain material concerns for a shared installation.

This review covers the working tree, including existing reporting changes, the route inventory, targeted service and frontend code, checked-in configuration, selected Git history checks, and regression tests with synthetic data. It does not establish live deployment settings, effective PostgreSQL/Supabase grants, or the contents of a live database. Verdicts describe the baseline. **Patched** identifies a workspace remedy. **Partial** identifies incomplete coverage or evidence.

## 2. Critical and high findings

| ID | Severity | Location | Risk and remediation |
| --- | --- | --- | --- |
| F1 | High for shared installations | `backend/app/main.py:135`, `backend/app/auth.py:117`, `backend/app/schemas.py:80` | Startup previously seeded demo identities on all database backends and the initial working tree accepted a shared temporary password. An unauthorized person who signs in first can claim an unused account. **Patched** with strong mandatory temporary passwords and server-database defaults that disable demo seeding. The local SQLite demo default remains configurable. Review previously provisioned accounts and revoke their sessions before hosting. CWE-1392. |
| F2 | High for shared installations | `src/api/client.js:19`, `backend/app/auth.py:60` | JavaScript can read the bearer token. A script running in the app origin can take a session that remains usable until it expires or another server-side gate invalidates it. Migrate browser sessions to secure HttpOnly cookies with appropriate SameSite and CSRF controls, and provide server-side revocation. Verify both same-origin and supported split-origin deployments. CWE-922. |
| F3 | High for network-reachable API | `backend/requirements.txt:1`, `backend/requirements.txt:8` | The baseline multipart parser and resolved Starlette versions are affected by published resource-exhaustion advisories. The parser is invoked for form routes before endpoint authorization completes. **Patched** with FastAPI 0.162.3, Starlette 1.10.0 and python-multipart 0.0.32. CWE-400. [python-multipart advisory](https://github.com/Kludex/python-multipart/security/advisories/GHSA-pp6c-gr5w-3c5g) · [Starlette form advisory](https://github.com/Kludex/starlette/security/advisories/GHSA-82w8-qh3p-5jfq) · [Starlette file response advisory](https://github.com/Kludex/starlette/security/advisories/GHSA-7f5h-v6xp-fcq8) |
| F4 | High advisory rating, reachability varies | `package-lock.json` | npm reported high-severity entries for Vite, nanoid, source-map-js, React Router and its React Router DOM dependent. PostCSS was moderate. **Patched** through compatible lockfile updates. The React Router advisory concerns RSC mode, which EduScan does not use. Vite and toolchain advisories primarily affect development/build paths. [Vite advisory](https://github.com/advisories/GHSA-587h-7wmj-h5pm) |

An active live data exposure was not verified. Hosted authorization and database privileges still need deployment evidence.

## 3. Quick wins applied

| File | Change |
| --- | --- |
| `.gitignore` | Ignore environment variants at any depth, including Vite environment files, while retaining example files. |
| `backend/app/main.py` | Apply the demo seeding and API documentation settings. Reject wildcard CORS origins. Set cache, MIME-sniffing, framing and referrer headers on handled API responses. Drop raw inputs and contexts from validation errors. Bound endpoint-level reads for Annex G, SF2, and camera batches. The camera enrollment cap uses the existing 8 MiB burst limit. |
| `backend/app/config.py` and `backend/.env.example` | Add settings for demo-account seeding and API docs. Defaults are on for SQLite and off for PostgreSQL/MySQL. |
| `backend/app/schemas.py` and `src/pages/Administration/Administration.jsx` | Require a strong temporary password for new password-based accounts and remove the shared value from the account form. |
| `backend/tools/create_admin.py` | Provide server-console provisioning for a named administrator with a hidden password prompt and forced first-login password change. |
| `scripts/setup.ps1` | Honor an explicit demo-account opt-out when setting up a fresh local database. |
| `scripts/manage-eduscan.ps1`, `docs/INSTALLATION.md`, and `docs/POSTGRESQL_SETUP.md` | Clarify the startup defaults and named administrator workflow. |
| `backend/app/services/annex_g.py` | Share the existing 15 MiB workbook limit with the upload handlers. Close the workbook after comparing columns and reading rows, including when parsing fails. |
| `backend/app/services/sf2.py` | Validate the workbook and confirm the named SF2 sheet maps to the package entry the exporter edits. Close the workbook on every path. Replace the installed template atomically from a staged file in the same directory. Use the existing 20 MiB limit at both entry points. |
| `backend/requirements.txt` | Pin FastAPI, Starlette and python-multipart to upgraded releases. [FastAPI release](https://github.com/fastapi/fastapi/releases/tag/0.162.3) · [python-multipart release](https://github.com/Kludex/python-multipart/releases/tag/0.0.32) |
| `package-lock.json` | Resolve compatible frontend security updates. A fresh `npm audit` reports zero findings, down from five high and one moderate. |
| `backend/tests/test_security_controls.py` and `backend/tests/test_smoke.py` | Check API response headers, template preservation, disabled demo seeding, and the stronger temporary-password flow. Use the OpenAPI schema for the removed-route smoke check. |

An installation using an explicit `SF2_TEMPLATE_PATH` reads its active workbook from that location. Admin uploads still publish to the default path. Replace the configured file through the deployment's authorized file-management workflow.

## 4. Prioritized remediation plan

Estimates are engineering time. School decisions, access provisioning, and deployment windows are additional.

| Priority | Effort | Work |
| --- | --- | --- |
| High, F1 | 1–2 hours | Review previously provisioned demo or shared-password accounts, rotate their credentials and revoke affected sessions. Set both demo-account and API docs flags to false on any shared SQLite deployment. |
| High, F3/F4 | 1–2 hours | Roll out the updated packages through the normal deployment workflow. Run a full Python advisory check, including transitives, and set up recurring advisory checks. |
| High, F2 | 1–3 days | Migrate browser sessions to cookie-based transport with CSRF controls, secure logout, and credential-change revocation. Verify both supported login paths and the scanner workflow. |
| Medium, CWE-770 | 2–4 hours | Verify proxy request limits against the API caps. Review archive metadata and add lifetime storage quotas. |
| Medium, CWE-307/CWE-770 | 4–8 hours | Add persisted per-source and per-account request limits for password/Google auth, reset, uploads, and notification endpoints. Validate concurrency and lockout alerting. Confirm the SMS allowance covers every send path and scheduled worker. |
| Medium, CWE-284 | 4–8 hours | Inspect effective database grants and any hosted data API for every application table. Separate migration credentials from runtime credentials where deployment supports it. Verify teacher isolation for attendance, rosters, gradebooks and exports with synthetic assignments. Move applicable predicates into SQL and validate role coverage as new routes are registered. |
| Medium, CWE-200 | 4–8 hours | Review public diagnostic metadata, all client-visible error text, production logging and SMS provider errors. Restrict public docs, and document how to monitor failures without logging credentials or learner records. The workspace patch addresses request-validation and workbook-parser error bodies. |
| Medium, CWE-693 | 4–8 hours | Confirm production HTTPS, HSTS, frontend CSP and frame policy, deploy only built assets, deny sensitive static paths, restrict the upstream network bind, and configure process resource limits. |
| Medium, operational | 1–2 days | Verify encrypted offsite backup retention, restore to a clean authorized environment, and record restore checks. Configure alert routing and a security reporting contact. |
| Medium, governance | School approval | Obtain the school-approved privacy notice and related policies, verify processor arrangements and retention, and document how authorized requests for access, export and disposal are handled. |
| Low, account and abuse controls | 4–8 hours | Define local-account MFA and breached-password screening. Apply enumeration-resistant auth responses where compatible with operator workflows. Decide whether additional bot mitigation is needed for any public flows. |

## 5. Existing controls to preserve

- The backend checks HMAC token integrity, expiry, database-backed user status and current role. Frontend role state controls navigation. See `backend/app/auth.py` `decode_token`, `current_user` and `require_roles`.
- Local passwords use scrypt with random salts. Recovery codes are time-limited, tracked in the database, and consumed atomically. Google identity verification checks the audience, Workspace domain, verified email, and linked identity. See `backend/app/services/password_recovery.py` and `backend/app/services/google_login.py`.
- Sensitive reports, backups and biometric artifacts use backend-controlled storage paths. Protected report and DTR routes enforce server-side access. Biometric samples and stored SMS credentials use application encryption. See `backend/app/services/biometrics.py`, `backend/app/services/settings_store.py` and `backend/app/services/dtr.py`.
- Audit events record privileged operations. Backup scheduling, encryption and a restore-verification workflow exist. See `backend/app/services/audit.py`, `backend/app/services/backup.py` and `docs/DISASTER_RECOVERY.md`.

## 6. Detailed audit checklist

| Item | Baseline verdict | Evidence |
| --- | --- | --- |
| 1.1 Hardcoded secrets | Fail → Partial | Public demo credentials in `auth.py` and `seed_demo.py` remain available in SQLite demo setups. Shared defaults for new accounts were removed. No provider token was established by the selected pattern scan. F1. |
| 1.2 Environment ignore and history | Fail → Patched | Old rules covered the backend default env and some local variants. Checked relevant env paths in available history and found only `backend/.env.example`. New rules cover variants at all depths. |
| 1.3 Public prefix leaks | Pass | Reviewed frontend env references use `VITE_API_URL`. Google sign-in configuration returns a public client identifier. `src/api/client.js:1`, `auth_config`. |
| 1.4 Console and error leaks | Partial | FastAPI validation included raw rejected inputs. Patched response filtering. Other client errors and logging require deployment review. |
| 1.5 Build artifact exposure | Pass | Vite production config does not enable source maps. Actual deployed assets require deployment verification. `vite.config.js`. |
| 1.6 Startup validation | Partial | `config.py` generates local keys and parses numeric settings. Hosted requirements and service configuration are not centrally enforced at startup. |
| 2.1 RLS enabled | Partial | App uses server-side SQLAlchemy. No app migration provisions per-user RLS. Verify effective grants and hosted Data API exposure, particularly when using Supabase. `database.py`, `migrations.py`. |
| 2.2 RLS policies | N/A | Per-user database policies are not part of the server-only app design. Hosted grants remain open under 2.1. |
| 2.3 WITH CHECK | N/A | Reviewed repository does not configure application RLS write policies. |
| 2.4 Policy identity source | N/A | App identity is an EduScan user resolved by the backend. Supabase Auth claims do not drive authorization. |
| 2.5 Service-role isolation | N/A | No Supabase service-role key use was found in the application integration. |
| 2.6 Storage policies | N/A | The app uses backend-controlled files instead of Supabase Storage. `config.py`. |
| 2.7 SQL injection | Pass | Inspected request-facing data access uses SQLAlchemy expressions; raw migration DDL uses internal identifiers. `main.py`, `migrations.py`. |
| 2.8 SECURITY DEFINER | Partial | No application migration defining such functions was found. Effective functions in hosted databases were outside the review. |
| 3.1 Authentication middleware | Pass | FastAPI dependency equivalents cover protected API routes. `auth.py`; DTR router in `services/dtr.py:39`. |
| 3.2 Default deny | Fail | `main.py` has route-by-route dependencies, so a future route can omit authentication. |
| 3.3 Supabase getUser / getSession | N/A | Application signs and validates its own credential. `auth.py`. |
| 3.4 Authentication callback | Pass | Google Identity Services uses a frontend credential callback and POST to the backend; the route does not transport an auth token in a URL. `src/services/googleIdentity.js`, `google_login`. |
| 3.5 Session storage | Fail | Bearer tokens are persisted in localStorage. F2. `src/api/client.js:19`. |
| 3.6 Protected API routes | Pass | Route inventory shows dependencies for data routes. Public registrations cover health, auth configuration and sign-in/recovery. `main.py`, `services/dtr.py`. |
| 3.7 OAuth security | Partial | Google verifies the credential and checks the frontend nonce when supplied. Backend verification does not require or consume a server-issued nonce. `services/google_login.py`. |
| 3.8 Password reset | Pass | DepEd recovery uses time-limited single-use email codes, a cooldown and a bounded attempt count. `services/password_recovery.py`. |
| 4.1 Schema validation | Partial | Typed paths/queries and Pydantic payloads are widespread. Some scalar form/query inputs and upload parsing need explicit resource bounds. `schemas.py`, `main.py`. |
| 4.2 Identity from session | Pass | Actor identity for reviewed writes comes from the authenticated user dependency. Explicit target IDs are checked separately by permissions. `main.py`, `auth.py`. |
| 4.3 Sanitization | Partial | React renders regular text, and Annex G HTML uses escaping. Generated HTML may open under a frontend blob URL. Review every markup-producing path and apply a frontend CSP to contain it. `src/api/client.js`, `services/annex_g.py`. |
| 4.4 HTTP methods | Partial | Mutations generally use POST/PUT/PATCH/DELETE. Some GET exports persist generated artifacts or snapshots. See `temporary_log`, SF2 export, and the grading print route in `main.py`. |
| 4.5 Error leaks | Partial | Request input exposure and two workbook parser messages addressed. Other exception strings and provider diagnostics still need review. `main.py`, `services/sms.py`. |
| 4.6 Webhook signatures | N/A | No inbound provider webhook was found. SMS status is reconciled by EduScan. |
| 5.1 Advisory scan | Partial | First successful npm audit found five high and one moderate. Fresh npm audit after remediation found zero. Upstream advisories confirm the baseline Python dependency issues in F3. Full Python advisory coverage remains pending. |
| 5.2 Suspicious packages | Partial | The checked-in npm lockfile uses standard npm registry tarballs. Package provenance and download history were outside verified coverage. |
| 5.3 Lockfile | Pass (npm) | `package-lock.json` is tracked. Python direct requirements are pinned but no full transitive lock was verified. |
| 5.4 Outdated packages | Fail → Partial | FastAPI, Starlette, multipart and the npm lockfile were updated. Pillow, pypdf and other backend packages still need full advisory coverage. F3/F4. [Pillow advisories](https://github.com/python-pillow/Pillow/security/advisories) · [pypdf advisories](https://github.com/py-pdf/pypdf/security/advisories) |
| 5.5 Unused packages | Partial | `package.json` lists React, React DOM and React Router. Its build and lint tools are configured. A transitive and Python unused-dependency analysis was outside verified coverage. |
| 6.1 Expensive operations | Partial | SMS dispatch has a configurable allowance. Confirm per-actor and global limits across paths. Reset mail has a per-recipient cooldown. `services/sms.py`, `services/password_recovery.py`. |
| 6.2 Authentication limits | Partial | Existing accounts lock after failed password attempts. Google sign-in and requests across usernames lack a general source-based cap. `main.py` `login`, `google_login`. |
| 6.3 Persistent counters | Partial | Account lockout and recovery data persist in the database. General cross-worker request limits are missing. `models.py`, `services/password_recovery.py`. |
| 7.1 CORS origins | Partial → Patched | Defaults are restricted, but configuration previously accepted a wildcard. Import now rejects it. `main.py` app setup. |
| 7.2 Credentialed CORS | Partial → Patched | Credentials are enabled, and the wildcard is rejected. Effective hosted origins require deployment verification. `main.py` app setup. |
| 8.1 Upload validation | Partial | Workbook and frame reads are bounded at the endpoint. Workbook parsing and OpenCV decoding provide format checks. Ingress limits, decoded size and archive-expansion controls remain pending. |
| 8.2 Storage permissions | Pass | Backend paths and authenticated file routes protect reviewed data and uploads. Verify actual deployment filesystem ACLs. `config.py`, `services/biometrics.py`, `main.py`. |
| 8.3 Execution prevention | Pass | Reviewed uploads use application data paths outside the frontend public directory. No backend static mount exposes those paths. `config.py`, `main.py`. |

## 7. Detailed application checklist

| Category | Item | Baseline verdict and evidence |
| --- | --- | --- |
| Access | CORS | Partial → Patched. Explicit defaults in `config.py`, wildcard now rejected in `main.py`. |
| Access | SameSite | N/A for the current Authorization header session. Required for the cookie migration in F2. |
| Access | RLS | Partial. Server-only SQLAlchemy; verify hosted grants and Data API exposure. |
| Access | Scoped queries | Partial. Some teacher roster and attendance routes apply assignment checks after querying. `main.py` `persons` and `attendance`. |
| Access | Server-side gates | Pass. `require_roles`, plus object-specific checks and DTR router gating. |
| Access | Static files | Pass. Sensitive files are outside `public/` in the reviewed repository. Production routing needs separate verification. |
| Access | 404 vs. 403 | Partial. Some object endpoints use different errors for missing and out-of-scope records. Review identifier exposure and apply consistent policy by record family. `main.py` `ensure_gradebook_access`, `preview_generated_report`. |
| Roles | Backend RBAC | Pass. Roles are enforced through API dependencies. `auth.py`. |
| Roles | Server-sourced role | Pass. `current_user` reloads the database user; role decisions use that object. |
| Roles | Mass assignment | Pass in reviewed privileged writes. `UserCreate`, user-update schema and explicit assignments in `main.py`. |
| Roles | Role ranking | N/A. Administrator, teacher, records officer and scanner have distinct duties. Explicit permission lists fit this model. |
| Roles | Default deny | Fail. New route registrations can omit a permission dependency. |
| Roles | Recheck on each request | Pass. `current_user` checks active status and `require_roles` reads the current DB role. |
| Roles | Least privilege | Partial. Distinct roles exist. A school-approved permission matrix and review of each returned field remain pending. |
| Roles | Separate subscription and role | N/A. No subscriptions or billing integration were found. |
| Roles | Privileged audit events | Pass for inspected paths. User changes, grading and records disposal have audit events. Confirm coverage for all privileged paths. |
| Accounts | Password hashing | Pass. Salted scrypt in `auth.py`. |
| Accounts | Minimum length and breached lists | Partial. User creation and password change now both enforce 12 characters. SQLite demo defaults and breached-password screening remain gaps. `schemas.py`, `auth.py`. |
| Accounts | HttpOnly session | Fail. F2. |
| Accounts | Session expiry | Pass. The backend issues a time-limited token on sign-in. `auth.py`. |
| Accounts | Email verification | Partial. Google verification and account linkage are checked. Local operational accounts have no mailbox verification workflow. |
| Accounts | Enumeration resistance | Partial. Recovery responses are uniform. Some password login branches distinguish account state or provider. `main.py` `login`. |
| Accounts | Session revocation on password reset | Partial. DepEd password sessions bind to a password stamp. Ordinary password sessions do not have the equivalent credential revision check. `auth.py`. |
| Accounts | Constant-time comparison | Pass for password hashes, token signatures and reset-code digests. `auth.py`, `password_recovery.py`. |
| Accounts | MFA option | Partial. Google Workspace policy may enforce upstream MFA. Local accounts have no MFA control in this code. |
| Accounts | Self-service deletion | Fail. Staff-managed account and record disposal exist. No self-service account deletion workflow was found. |
| Abuse | Per-IP and per-user limits | Partial. Account lockout, recipient cooldown, and SMS limits exist; no general source limit. |
| Abuse | Persistence | Partial. The implemented account and reset limits use database state. Other applicable limits are missing. |
| Abuse | Brute-force alerts | Fail. Account lockout exists; no operator alert path for repeated attempts was verified. |
| Abuse | Spend caps | Partial. SMS message allowance exists; confirm enforcement across all send paths and any global/email limits. |
| Abuse | Lifetime storage caps | Fail. Retention and upload caps exist; tenant or deployment lifetime quotas were not found. |
| Abuse | Honeypot | N/A. No public standalone registration form was found; address abuse at exposed sign-in and recovery. |
| Abuse | Disposable emails | N/A. Institutional Google access is restricted to the verified DepEd Workspace domain. |
| Input | Server-side validation | Partial. Pydantic payloads and domain checks exist; further constrain form and import resource usage. |
| Input | Parameterized queries | Pass for inspected request-facing queries. SQLAlchemy binds user values. |
| Input | Shell injection | Pass for inspected workbook/PDF subprocess calls. Calls use argument arrays and backend-controlled paths. `services/excel_pdf.py`. |
| Input | Magic-byte validation | Partial. Decode/parser checks are present; an explicit accepted format and signature policy remains pending. |
| Input | Additional upload controls | Partial. Camera processing re-encodes stored samples; API upload reads are now bounded. Add decoded size and archive-expansion controls. |
| Input | Limits before file reads | Partial. Endpoint read caps added. FastAPI still parses the request before those checks. |
| Input | Safe file paths | Pass in reviewed flows. Server-generated or validated storage paths, including backup retrieval. `services/export_files.py`, `services/backup.py`. |
| Input | HTML sanitization | Partial. React escapes normal text and some report generators explicitly escape markup. Review generated HTML opened through blob URLs. |
| Input | Open redirects | Pass for the reviewed Google callback and login navigation. Internal destination selection is used. |
| Input | SSRF protection | Partial. SMS gateway validation is restricted to expected local addressing, which is required for the Android gateway. Verify deployment egress and operator permissions; see `services/sms.py` `validate_local_gateway_url`. |
| AI | Prompt injection | N/A. OpenCV biometric matching has no prompt interpreter. |
| AI | Model tool permissions | N/A. No LLM tool execution path found. |
| AI | PII in model system prompt | N/A. No LLM system prompt found. |
| AI | Untrusted model output | N/A for LLM code execution and rendering. Biometric matching authorizes attendance decisions through separate application checks. |
| Browser | HTTPS | Partial. Launchers bind to HTTP loopback. HTTPS for an externally hosted site and any mixed content need deployment verification. |
| Browser | CSP | Partial. The API patch adds a framing directive. A full frontend script and connection policy needs hosting and Google Identity Services testing. |
| Browser | HSTS | Partial. Requires confirmation on the external HTTPS origin. |
| Browser | Framing | Fail → Patched for API responses. Frontend origin requires its own policy. |
| Browser | MIME sniffing | Fail → Patched for API responses. Verify static hosting headers as well. |
| Browser | Cache policy | Partial → Patched for handled API responses. Sensitive endpoints had inconsistent cache headers. |
| Browser | Production stack traces | Partial. Framework debug mode is off by default; raw exception/validation details needed filtering and some errors still require review. |
| Browser | X-Powered-By | Pass in reviewed app code. Check intermediary response headers in deployment. |
| Secrets | Env vars and Git history | Partial. Env and locally generated files are used for service secrets; default demo credentials are public. Selected Git history checks are not a comprehensive credential audit. |
| Secrets | No frontend secrets | Pass for reviewed Vite env references. Production bundle and exact injected settings remain deploy-time checks. |
| Secrets | Block dotfiles and backups | Partial. Backup paths are outside the frontend public directory. Confirm deployed web root and proxy behavior. |
| Secrets | Production sourcemaps | Pass by Vite config. Verify files in the deployed bundle. |
| Secrets | Least privilege for DB and keys | Partial. MySQL provisioning has a scoped account. Hosted PostgreSQL grants and migration/runtime role separation need verification. |
| Secrets | Encrypt stored third-party tokens | Pass for reviewed stored SMS gateway secret via Fernet. Google ID tokens are verified for sign-in and are not kept as third-party refresh tokens. |
| Secrets | Standard crypto | Partial. Uses hashlib, HMAC, Fernet and library Google verification. The EduScan session token format is application-specific. |
| Secrets | Rotate leakage | Partial. No actual provider secret was verified. Existing demo credentials, local signing keys and hosted secret rotation procedure require operator review. |
| Infrastructure | Remove default/test users | Fail → Partial. Demo provisioning defaults off for server databases. Existing accounts and shared SQLite still require operator checks. F1. |
| Infrastructure | Restrict debug surfaces | Partial. API docs now default off with server databases. Public health returns backend and model metadata used by diagnostics. `main.py`. |
| Infrastructure | Firewall origin | Partial. The supplied launcher binds to loopback; Cloudflare or other hosted upstream isolation is unverified. |
| Infrastructure | Process memory limits | Fail in shipped launcher. Add host limits and ingress controls for a shared deployment. |
| Infrastructure | Dependency upkeep | Fail → Partial. Known parser issues and current npm audit findings were addressed in the workspace. Ongoing advisory checks and full Python advisory coverage remain open. |
| Infrastructure | Offsite backups | Partial. Encrypted backup scheduling is supported. Offsite storage, cadence, retention and permissions are operational checks. |
| Infrastructure | Restore testing | Partial. Scripts and automated restore tests exist; a current live recovery exercise was outside scope. |
| Infrastructure | Audit log | Pass in reviewed privileged routes. `services/audit.py`. |
| Infrastructure | Keep PII out of operational logs | Partial. Some service paths redact, while provider/error logging and audit data retention need operational review. |
| Infrastructure | Alerting | Fail. No deployed 500-error or security alert destination was verified. |
| Infrastructure | Security contact | Fail. No repository security reporting contact was identified. |
| Governance | Terms of service | Partial. No published terms were verified. Confirm what the school deployment uses and requires. |
| Governance | Privacy notice | Partial. The setup workflow records notice and approval evidence. Obtain approved content and verify how it reaches affected people. |
| Governance | Processor list | Partial. Google sign-in, database hosting, SMTP and SMS arrangements depend on deployment; no approved inventory was verified. |
| Governance | Cookie disclosure | N/A for the current EduScan bearer session. Review Google-related browser storage and the future cookie session in F2. |
| Governance | Refund policy | N/A. No billing integration found. |
| Governance | Data processing terms | Partial. Requires verification of the school's actual service and vendor arrangements. |
| Governance | Export and deletion | Partial. Reporting and authorized disposal exist. No end-to-end individual request workflow was verified. |
| Governance | Policy dates | Partial. Approved policy documents and their revision dates were outside repository evidence. |
| Money | Paid access grants | N/A. No paid plans found. |
| Money | Recompute totals | N/A. No payment totals found. |
| Money | Payment webhook signatures | N/A. No payment webhooks found. |
| Money | Payment idempotency | N/A. No charges or entitlements found. |
| Money | Two-account authorization check | Partial. The synthetic schedule test verifies that two teacher identities with the same name receive distinct access. Reporting tests cover assigned and excluded records. Repeat scoped checks against hosted configuration. `backend/tests/test_admin_reporting_permissions.py`. |

## 8. Verification

- The targeted backend run with the upgraded framework and multipart packages passed 109 tests and 22 subtests. It covered authentication, password recovery, reporting permissions, Annex G, and the app smoke tests. The test run reported framework deprecation and existing schema-reflection warnings.
- Separate synthetic checks verified that the named-admin tool provisions an account that requires a first-login password change, that the API can start with demo users and docs disabled, and that the supplied SF2 workbook publishes intact.
- Frontend lint and the production build passed using the updated npm lockfile. The frontend tests reported 28 passes and one attendance loading-state failure. The same test failed with the original installed Vite version. A fresh npm audit of the updated lockfile reported zero findings.
- The backend package versions were verified in an isolated package directory, and the frontend used an isolated install. Apply the updated dependencies in the ordinary runtime before relying on the dependency fixes. Live accounts, settings and infrastructure were outside verification.

## 9. Browser session follow-up

F2 is implemented in the workspace. Browser authentication now uses an opaque HttpOnly, SameSite=Lax cookie. HTTPS cookies are Secure, and the only HTTP exception is loopback use. EduScan stores a one-way session digest and an eight-hour expiry server-side. The API checks the current user, role and authentication provider on every protected request. The web client obtains its session identity from `/api/auth/me` and removes the retired storage keys. Legacy bearer tokens are rejected.

The login and logout routes and all authenticated requests require the EduScan request header. Browser origins must match the configured allowlist when an Origin header is present. Password changes, password recovery, operator resets, deactivation, and controlled restores revoke affected sessions. Sign-out revokes the current browser session.

The frontend also sends a public session context value to reject stale actions when another tab switches accounts. The report download and grading maintenance scripts use a cookie jar and prompt for credentials. Biometric runtime status now requires an administrator, matching the access policy of its UI and runtime-settings endpoint.

The patched Python and npm dependencies were also installed in the ordinary local project environments. Hosted cookie and database settings still require deployment verification.

Local verification exercised password sign-in and rotation, cookie restoration after a page reload, sign-out across two Chrome tabs, and authenticated CLI requests. The final frontend build and lint succeeded, and all 103 frontend tests passed. The full backend run recorded 638 passes and five test failures. The three affected test files passed on rerun after correcting outdated liveness calls and cookie fixtures. A separate final auth, backup and smoke run passed 62 tests. SQLite restore verification cleared session rows and preserved the synthetic data records.

## 10. Form request-size follow-up

The API checks declared form request sizes before invoking multipart parsing and counts bytes as the ASGI server delivers streamed bodies. Oversized requests return HTTP 413. The whole-request limits are 9 MiB for camera uploads, 16 MiB for Annex G workbooks, 21 MiB for SF2 templates, and 251 MiB for backup restores. These budgets include up to 1 MiB for multipart framing and fields. Other multipart forms and URL-encoded forms have a 1 MiB whole-request limit. The existing file-size checks still apply after parsing. Deployment proxy settings remain open.

The targeted backend run covered 101 tests across upload limits, camera uploads, workbooks, and backup recovery. One PostgreSQL integration test timed out during local cluster initialization in the combined run. Its isolated retry completed the encrypted backup and restore round trip.

## 11. ZIP expansion follow-up

Annex G roster and date-of-birth workbooks and SF2 templates now have a 128 MiB total decompressed ZIP limit. Backup restores have a 1 GiB total limit and an 8 MiB manifest limit. EduScan checks archive sizes before processing entries, then reads entries in bounded chunks. Restore files are streamed into a temporary directory and published for recovery only after all required files and hashes have been verified. Duplicate entries and unsupported ZIP compression methods are treated as invalid files.

## 12. Camera decode follow-up

Camera uploads accept JPEG and PNG. EduScan validates image dimensions and rejects frames with a decoded budget above 32 MiB before loading pixels. The 3840 × 2160 limit applies to the oriented image. Oversized frames return HTTP 413 in enrollment, live recognition, and camera tests. The browser capture size remains 960 pixels along the longest edge.

The final focused run passed 20 tests, including the expanded archive limits, backup creation and PostgreSQL recovery, and image rejection before pixel loading. A separate SQLite round trip verified that an encrypted backup restored the expected synthetic record. The broader regression run caught an enrollment response that needed to propagate HTTP 413. The corrected path passed on rerun. The attendance PDF smoke test also passed on its isolated retry.
