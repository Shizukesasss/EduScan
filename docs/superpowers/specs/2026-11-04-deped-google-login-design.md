# DepEd Google login

## Intent and agreed requirements
Allow every Google Workspace account belonging to `deped.gov.ph` to sign in to EduScan. Automatically create a teacher account on first sign-in. Admin privileges and teaching assignments remain school-controlled.

## Approaches
- Recommended and accepted in principle: Google sign-in with automatic teacher provisioning. This meets the requirement to admit every DepEd account.
- Administrator-created accounts only: provides individual approval but conflicts with the requested domain-wide access.
- Email text validation with the existing password form: cannot establish Google Workspace membership and does not meet the intended identity verification requirement.

## Proposed behavior
The React login page uses Google Identity Services. FastAPI verifies the Google ID token signature, audience, issuer, expiry, verified email, and exact `hd=deped.gov.ph` organization domain; the email domain must also exactly match. Client hints are not authorization checks.

Persist Google's stable subject identifier and email separately from the existing username. First sign-in creates an active teacher with no local password login and no forced local password change. Subsequent sign-ins use the linked Google subject and retain school-assigned roles. Inactive accounts stay blocked. Do not automatically link a Google identity to an existing privileged account based on a matching name or username.

New teachers receive no automatic class assignments. Existing teacher authorization must continue to restrict access to assigned classes. Review and test those boundaries before enabling automatic provisioning.

Proposal for the existing admin and scanner accounts: provide an administrator-run migration/setup command that explicitly links designated verified DepEd identities to existing accounts, preserving their roles and assignments. Enable DepEd-only login after this setup; reject local password login in that mode so it cannot bypass the domain restriction. Scanner access then uses an authorized DepEd-linked account. Never automatically promote the first Google user.

## Configuration and rollout
Requires a Google OAuth web client ID and authorized site origins, configured for the frontend and backend. Supply setup documentation and a clear unavailable state when configuration is missing. A working Google client configuration and any required DepEd organization consent are external prerequisites for live sign-in.

## Scope and validation
Change login, identity storage/migrations, authentication endpoints, account setup, and account-security behavior for Google users. Retain the existing session mechanism and role-based routes. Do not import Google mail or request Gmail permissions.

Verify valid-domain provisioning, repeat login, invalid tokens and domains, disabled users, privilege preservation, local-login rejection in DepEd-only mode, and assignment isolation. Run backend checks and the frontend lint/build. Live Google login requires the configured OAuth client.

## Approval
Approved by the user on 2026-11-04, including migration of existing admin and scanner accounts to DepEd identities.
