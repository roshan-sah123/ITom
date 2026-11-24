# Standalone ITOM sign-in

This independent React application signs users in with Microsoft Entra ID and
redirects to the existing portal. It does not import the portal or change its
source, dependencies, generated assets, API or ingestion.

**This is a sign-in launcher, not an access-control boundary.** Users can still
open the portal directly. The portal does not receive an authenticated identity,
tokens or a session, and its hardcoded operator label remains unchanged. The
portal does not read this app's MSAL cache, even on the same production host.
Protecting portal data requires an authentication gateway or backend enforcement.

## Development

Run these commands from the repository root in PowerShell.

1. Install only this application's dependencies:

   ```powershell
   npm.cmd --prefix frontend-revamp\sso install
   ```

2. Create `.env.development.local` beside this README using `.env.example` and
   fill in the Application (client) ID and Directory (tenant) ID from Entra. The
   local development values have already been configured on the original
   workstation. Only the development server reads this file, so development IDs
   can never be built into the production launcher. `.env.*` files other than
   `.env.example` are ignored by the existing repository rules.

   ```text
   VITE_ENTRA_CLIENT_ID=<application-client-id>
   VITE_ENTRA_TENANT_ID=<directory-tenant-id>
   VITE_ENTRA_REDIRECT_URI=http://localhost:5173/oauth2callback
   VITE_PORTAL_URL=http://localhost:5174/
   ```

   These Vite values are public browser configuration. Never add a client
   secret, password or privileged telemetry credentials. Restart the sign-in
   server after changing configuration.

3. In Entra, register `http://localhost:5173/oauth2callback` under the
   **Single-page application (SPA)** platform, not Web. Use a single-tenant
   registration. User assignment, MFA and Conditional Access are controlled by
   the Entra administrator. Sign-in requests only OpenID Connect identity scopes,
   not Graph permissions.

4. Start the unchanged portal in one terminal. The command-line port and host
   override its development settings without editing them:

   ```powershell
   npm.cmd --prefix frontend-revamp run dev -- --host localhost --port 5174 --strictPort
   ```

5. Start the separate sign-in app in another terminal:

   ```powershell
   npm.cmd --prefix frontend-revamp\sso run dev
   ```

6. Open `http://localhost:5173/` and select **Sign in with Microsoft**. Do not use
   `127.0.0.1` for the sign-in app; the origin must match the registered callback.
   After a successful callback, the browser opens `http://localhost:5174/`.
   The portal still needs its existing backend on port 8080 for telemetry.
   This sign-in application does not start or modify that backend.

## Behavior and verification

MSAL Browser handles Authorization Code with PKCE inside a React interface.
Initialization and callback processing run once before rendering the controls;
an additional MSAL React provider is not needed for this small standalone app.
Only a successful callback with an account in the configured tenant triggers a
redirect. Merely finding a cached account, visiting the callback directly or
adding a destination query parameter does not open the portal automatically.
No tokens, authorization codes or user details are appended to the portal URL.

Returning to the sign-in page lets the user start another sign-in. Microsoft can
reuse its existing SSO session unless tenant policy requires interaction.
**Sign out of Microsoft** is available when this app has a cached account; it
clears this application's MSAL session and visits Microsoft's sign-out endpoint,
returning to the registered callback. It does not close or protect portal tabs.

```powershell
npm.cmd --prefix frontend-revamp\sso test
```

The tests cover configuration checks, the same-host redirect-loop guard, callback
order, successful redirection, absent responses, tenant mismatch and failure
handling.
They do not prove that the Entra registration or a real employee's MFA works.
Verify those interactively without sharing credentials, codes or tokens:

- Complete sign-in and confirm the destination is the portal, without tokens.
- Cancel sign-in or deny consent and confirm no automatic portal redirect.
- Check an unassigned user if enterprise-app assignment is required.
- Open the callback directly and confirm it offers sign-in rather than redirect.
- Return to the launcher and test sign-out.

## Microsoft shows "Approval required"

This is an Entra consent-policy requirement, not a React callback error. Enter a
justification on the Microsoft page and select **Request approval**. An authorized
Entra reviewer can open **Enterprise apps > Admin consent requests > My Pending**,
select ITOM-Portal, then **Review permissions and consent**.

The request contains `openid`, `profile`, `email` and MSAL's automatically added
`offline_access` scope. The latter allows token renewal within the permissions
already consented to; it does not grant access to all organizational data.
No directory administration or telemetry permissions are needed for this launcher.
Being the app registration's owner does not automatically allow granting
organization-wide consent.

Admin consent and user assignment are separate. If **Assignment required** is
enabled for the enterprise app, the administrator must also assign the approved
test users or groups. After approval, restart sign-in at `http://localhost:5173/`
instead of reusing the old callback.

## Production (same host)

The production launcher is served by the existing portal host at
`https://itom.coforge.com/oauth2callback`. After sign-in it opens
`https://itom.coforge.com/`. No existing portal, API, NGINX, Docker or FastAPI
file is changed: both the NGINX container and FastAPI already serve every file
under `frontend/`, so the launcher is added as the new folder
`frontend/oauth2callback/`.

1. In Entra, open **App registrations > ITOM production app > Authentication**.
   `https://itom.coforge.com/oauth2callback` must be listed under
   **Single-page application**. If it is listed only under **Web**, remove it
   there and add it under Single-page application; otherwise Microsoft rejects
   the browser token request with AADSTS9002326.
2. Grant admin consent for the production app's enterprise application, and
   assign users or groups if **Assignment required** is enabled.
3. Create `.env.production.local` beside this README. These are public browser
   IDs; the client secret is not used by this launcher and must never be added:

   ```text
   VITE_ENTRA_CLIENT_ID=<production-application-client-id>
   VITE_ENTRA_TENANT_ID=<directory-tenant-id>
   VITE_ENTRA_REDIRECT_URI=https://itom.coforge.com/oauth2callback
   VITE_PORTAL_URL=https://itom.coforge.com/
   ```

4. Build from the repository root:

   ```powershell
   npm.cmd --prefix frontend-revamp\sso run build
   ```

   The build fails before writing anything if a value is missing, the redirect
   URI is not HTTPS or the portal URL points back to the launcher. It replaces
   only `frontend/oauth2callback/` (`index.html` plus hashed `assets/`), using
   `/oauth2callback/` as its asset base. The portal build does not empty
   `frontend/`, so rebuilding the portal keeps this folder.
5. Deploy `frontend/oauth2callback/` with the rest of `frontend/`. Users start at
   `https://itom.coforge.com/oauth2callback`. FastAPI redirects that address to
   `/oauth2callback/` and browsers keep Microsoft's `#code=...` response
   fragment across that redirect; NGINX serves the folder directly.
6. Verify on the HTTPS host: sign in, confirm the portal opens without tokens
   in its URL, then cancel a sign-in and confirm the portal does not open.

The launcher only works at its configured origin. Opening the production build
elsewhere shows an origin error instead of contacting Microsoft. Production
access control is still not supplied by this launcher; the portal and its APIs
remain directly reachable.
