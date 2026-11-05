# DepEd Google sign-in

EduScan accepts verified Google Workspace identities whose hosted domain and email domain are exactly `deped.gov.ph`. A first sign-in creates a teacher account with no class assignments. Existing Google-linked users retain their school-assigned roles; inactive users cannot sign in. A display name never grants ownership of another account or an unassigned schedule.

## 1. Configure Google

Create a Google OAuth **Web application** client for the school's deployment. Configure the consent screen for basic sign-in, and add every actual frontend origin under **Authorized JavaScript origins**, including its port during development (for example, `http://127.0.0.1:5175` and `http://localhost:5175` if both are used). Use HTTPS for hosted production deployments. Popup sign-in uses a JavaScript callback; this integration does not use a redirect endpoint or require a client secret or Gmail API access.

If the consent configuration is in Testing, Google may require named test users until its publishing requirements are met. DepEd's Workspace administrator may also need to allow this app. Domain-wide access in EduScan does not bypass Google's consent or organization policies.

In `backend/.env`, set:

```dotenv
GOOGLE_CLIENT_ID=YOUR_WEB_CLIENT_ID.apps.googleusercontent.com
EDUSCAN_DEPED_ONLY=false
```

Add the frontend origins to `ALLOWED_ORIGINS` in that file too. The frontend obtains the public client ID from `/api/auth/config`; no duplicate Vite setting is needed. Install backend requirements and restart the API. Google sign-in requires internet access, including access to Google's signing certificates from the API host; never disable TLS verification to work around certificate errors.

## 2. Link existing accounts before their first Google sign-in

Back up the database first. From `backend/`, use the setup command with the **existing EduScan username** and the actual school-authorized DepEd email:

```powershell
.venv/Scripts/python.exe tools/link_google_account.py --username admin --email ACTUAL_ADMIN@deped.gov.ph
.venv/Scripts/python.exe tools/link_google_account.py --username scanner --email ACTUAL_GATE_STAFF@deped.gov.ph
```

The addresses above are placeholders. This is a local administrator operation and must only be run by the system operator. It reserves the address for the existing user ID, preserving that account's role and teaching assignments. It does not mark an email as verified: Google must verify ownership and membership in `deped.gov.ph` on first sign-in before the stable Google subject is bound.

Reserve existing teachers' addresses the same way if their user IDs already own assignments. Do this **before** those people first use Google sign-in; otherwise they receive separate, unassigned teacher accounts. Each Google identity belongs to one EduScan account. Do not reserve the same email for an admin and scanner account; an admin may use the existing scanner workspace with their admin identity, or reserve a separate staff identity for the dedicated scanner account.

Reserved/linked accounts use Google sign-in immediately, including during transition mode. Repeating the same unbound reservation is safe. The command rejects replacing a bound identity, moving another user's email, linking an inactive user, and non-DepEd addresses. If a teacher has already auto-registered, use the existing admin Accounts screen to assign their authorized role/classes as appropriate; the command does not silently merge users or transfer their school records.

Test the linked administrator sign-in and scanner workflow before the next step. Never promote the first Google user automatically.

## 3. Require DepEd accounts only

After verifying the linked accounts, set:

```dotenv
EDUSCAN_DEPED_ONLY=true
```

Restart the API. The login page then shows only Google sign-in, `/api/auth/login` rejects passwords, and previously issued password sessions are rejected even if they have not expired. New verified DepEd users receive teacher access automatically. School administrators assign roles and classes in the existing Accounts and academic setup screens. No assignment is inferred from a Google display name.

If the client ID is absent in strict mode, login fails closed with a setup message. Strict mode cannot fall back to password access when Google is unavailable. Keep the server configuration under school-operator control. Legacy mode defaults to `false` for `EDUSCAN_DEPED_ONLY` only to support the explicit migration described above; it is **not the completed DepEd-only rollout** until you set it to `true`.

## Account security and verification

Google-linked users manage their password through their DepEd Google account. EduScan rejects local password login/reset for those accounts. Administrators can still deactivate users and change their EduScan roles; Google sign-in does not override an inactive account.

The backend uses Google's official `google-auth` library to validate signatures, audience, issuer, timestamps, and the login nonce, then checks verified email and the exact hosted/email domain. It links accounts by stable Google subject, with explicit email reservation only for the setup operation above. The popup callback submits JSON from an authorized origin rather than Google's redirect-form flow.

Automated tests use disposable SQLite databases and simulated Google certificate responses. Live login still needs the actual OAuth client, allowed origins and an eligible DepEd account. See [Google's token verification guide](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token) and [JavaScript API reference](https://developers.google.com/identity/gsi/web/reference/js-reference).
