# Google connection setup and live checks

The tracker owns one Google account connection. Google tokens live in a native OS
credential store, under a namespace tied to the workspace path. SQLite contains
only identity, granted scopes, status, timestamps and a random store reference.
Backups contain no Google tokens. Restore requires reconnecting Google. Disconnect
removes the local credential; revoke the app separately in your Google account
to withdraw Google's grant. Existing Gmail drafts remain in Gmail.

## Configure

### Set up inside Application Tracker

Open **Settings → Connections → Connect Google**. This presents Google's one-time
registration steps and the exact JavaScript origin and callback for this installation.
Create a Desktop app OAuth client for local use, or a Web application client for
hosted use, in Google Cloud, then use **Import Google
credentials JSON** to import its downloaded client file. Application Tracker stores
the credentials in its existing secure vault and applies them immediately; no
environment-file edit or backend restart is needed. Only a presence marker is
written with workspace files; backups do not contain the imported registration.
Changing to another client requires disconnecting the current Google account first.

Connect Google with no optional capabilities selected to link only your identity.
The consent request contains only `openid` and `email`. Gmail read, Gmail drafts,
and Drive are requested only when selected and remain unavailable to agents until
granted. Desktop clients use the loopback callback in the normal system browser;
hosted GIS sign-in uses a Web application client.

On later starts, an explicitly configured environment client takes precedence.
Otherwise the saved registration is restored from the vault. A locked vault leaves
local tracking and password login available. Google Cloud registration and real
account consent are still required; importing a file is not proof of a live connection.

### Optional Google workspace sign-in

Local use continues without sign-in. A hosted workspace can additionally offer
the standard Google Identity Services button. Use a **Web application** OAuth
client, register `APP_PUBLIC_URL` as an **Authorized JavaScript origin**, and set
`GOOGLE_CLIENT_ID` plus `GOOGLE_LOGIN_SUBJECTS` (comma-separated trusted Google
`sub` identifiers). Leave the allowlist blank to keep Google sign-in unavailable.
For Docker, the Google overlay passes this allowlist from `deploy/hosted.env`.
Never enable arbitrary Google accounts on this single shared workspace. Obtain
subject IDs from a trusted, independently verified identity source; an email
address or a JWT decoded without signature validation is not sufficient.

Workspace sign-in uses the official GIS script and a popup credential callback.
It does not need `GOOGLE_REDIRECT_URI` or a client secret. The backend verifies
the signed ID token, issuer, audience, verified email, allowed subject and a
single-use nonce bound to a Secure/HttpOnly browser cookie. The challenge expires
after five minutes and on server restart. Identity credentials are never stored.
The resulting session has the same expiration, CSRF, revocation and password-change
rules as password login. Password login remains available as a fallback.
Configured hosted responses allow GIS in CSP and permit popup communication.

This is separate from Gmail/Drive authorization below. Selecting Google sign-in
does not connect a mailbox, grant agent access or request Gmail/Drive permissions.

### Optional Gmail and Drive connection

1. Enable Gmail API and/or Drive API in your Google Cloud project. Configure the
   consent screen and test users. Restricted Gmail scopes require Google's
   verification process before wider distribution; testing-mode grants can expire.
2. For local use create a desktop OAuth client. For hosted use create a web OAuth
   client with the exact HTTPS callback registered. Keep configuration private.
3. Add to `.env` and restart the backend:

   ```dotenv
   GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/connections/google/callback
   # GOOGLE_CLIENT_SECRET=your-client-secret-if-required
   ```

   Hosted callbacks use `APP_PUBLIC_URL` followed by
   `/api/connections/google/callback`. Local callbacks use `APP_HOST`/`APP_PORT`.
   Open the UI at that exact origin, including the hostname and port.
4. Install project dependencies, then unlock a supported native credential store:
   Windows Credential Manager, macOS Keychain, Secret Service or KWallet. Plaintext,
   chained and unknown keyring backends are rejected. Headless hosts without a
   usable safe store keep offline tracking; they cannot connect Google.
5. In Settings → Connections choose any combination of Drive app data, Read and
   search Gmail, and Create Gmail drafts, then Connect Google (or Reconnect Google
   for an existing account). Authorize in your normal browser. Connecting with no
   capabilities selected links identity only; mailbox imports require Read and
   search Gmail. Missing registration opens the in-app setup instead of silently
   disabling the control.

Authorization uses code + PKCE S256, state, nonce, signed ID-token validation,
issuer/audience checks and a browser cookie bound to the initiating human session.
Pending links expire in ten minutes and are deliberately invalid after restart.
Reconnect pins the existing stable Google subject. Disconnect explicitly before
switching accounts. Starting a newer link or disconnecting invalidates older links.
New scope selections always open explicit consent; installed apps do not rely on
silent incremental authorization. Only selected and actually granted scopes become
tracker capabilities. No scope grants tracker agent permissions automatically.

## Behavior and failure recovery

Successful consent first loads a small app-origin return document at the API
callback, which the offline service worker does not intercept. An external
same-origin script then replaces the callback address with Settings → Connections.
A manual link is available if scripting is unavailable. This breaks the cross-site
redirect chain before the offline worker handles the app shell, avoids a misleading
reconnect page, and removes the callback query from the current history entry.
Callback responses are not cached and send no referrer. Access-log redaction keeps
Uvicorn's structured arguments intact while removing authorization codes and state.

- `search_mail` returns at most 25 message IDs; `get_mail_message` returns selected
  headers and bounded plain text, with email content marked untrusted. Both require
  the tracker's read permission and Google Gmail read capability.
- `draft_followup` uses the existing draft permission and requires a current
  follow-up revision plus a stable operation UUID or idempotency key. It creates a
  draft for the selected recipient; unresolved placeholders block mailbox drafts.
  There is no send operation, even though Google's compose scope permits sending.
- Disconnected, revoked or locked credentials leave tracking operational. Explicit
  draft requests fall back to a local EMAIL_DRAFT note when drafts are disconnected.
  Failures discovered during an external write return an error; they are never
  silently retried or reported as a successful mailbox draft.
- A disabled Gmail or Drive API is a project setup error, not expired consent.
  Enable the named API in the same Google Cloud project, then retry. The tracker
  preserves the account's granted capabilities for `accessNotConfigured` and
  `SERVICE_DISABLED` responses. Saving OAuth Data Access settings alone does not
  enable an API or add permissions to an existing account connection.
- Application sync retries temporary limits on Gmail list/message reads at most
  three times. It honors short `Retry-After` values and otherwise waits 5, 10 and
  20 seconds; longer provider delays stop the run with completed imports saved.
  Every retry checks the linked account again. Draft writes are not retried.
- Each Gmail account has a persisted completed-scan date boundary. The next run
  uses Gmail's `after:`/`before:` filters with Unix seconds, with a five-minute
  overlap for boundary/indexing edges. Receipts skip every previously processed
  message, including review items, so the overlap never re-downloads their bodies.
  A successful scan records its start time, not its finish time or a sender's Date
  header. Failed, cancelled and interrupted scans leave the prior boundary intact;
  retries skip saved receipts and resume the unread work. Drive failures do not
  undo a completed Gmail boundary. The boundary stays local to each account and
  survives application restarts. Initially unmatched actionable messages are
  matched once more from this run's cached payloads, without another Gmail read.
- A receipt is committed before external draft creation. Successful identical
  retries replay it; changed arguments conflict. A timeout/crash leaves an uncertain
  operation blocked. Inspect Gmail and reconcile it manually before deliberately
  issuing a new operation ID. This avoids guessing whether Gmail accepted a write.
- Drive's optional test uploads only AES-GCM ciphertext to `appDataFolder`, reads it
  back, verifies and deletes it. Supply a random 32-byte base64 key that you generated
  and saved yourself. The tracker neither derives it from credentials nor stores it.
  This optional transport diagnostic is separate from encrypted compact sync.
  Desktop SQLite and the independent phone IndexedDB replica now share the v1
  merge/encryption protocol. See [PHONE_SYNC.md](PHONE_SYNC.md) for the separate
  Web OAuth registration, cross-client acceptance check and device setup.

## Live acceptance checklist (operator required)

These steps are not replaced by mocked tests:

Before testing Google capabilities, verify hosted HTTPS workspace login, reload,
and logout. Start Google consent while signed in and verify the return to Settings
succeeds despite the workspace cookie's SameSite=Strict setting. Start a new flow,
log out of the workspace in another tab, then return from consent: the callback
must reject that revoked initiating session. A completed callback cannot be reused.
See [LOGIN_WORKFLOW.md](LOGIN_WORKFLOW.md) for the function and class breakdown.

1. Connect one test Google account. Decline one optional scope; verify only granted
   capabilities are shown. Reconnect with another account and verify rejection.
2. Enable read/draft for the one tracker agent. From each configured real client,
   search a known application email and read the same message. Disable read and
   verify both are denied; restore it without restarting either client.
3. Request a draft for a test follow-up with a known recipient. Confirm the draft
   appears in the connected account and nothing is sent. Retry with the same key;
   verify there is one draft. Revoke draft permission and verify denial.
4. Revoke Google access in the Google account, then exercise a mailbox lookup.
   Verify reconnect state, offline applications and local draft fallback.
5. Optionally run the encrypted Drive test. Save your recovery key outside Drive
   and tracker credentials. Verify the test reports verification and deletion.
6. Rotate the tracker token. Both real clients must be denied, while the Google
   connection and local data remain. Repeat the concurrency checks in
   [AGENT_CONNECTIONS.md](AGENT_CONNECTIONS.md).

An opt-in real read smoke test is in
`backend/tests/agent/test_google_live.py`. Set `TRACKER_GOOGLE_SMOKE=1` and
`TRACKER_GOOGLE_SMOKE_QUERY` only after connecting your account. It uses the current
configured workspace and performs a bounded Gmail search; it does not create or
send mail. It is skipped during ordinary automated runs.

Official references: [Google desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app),
[ID-token verification](https://developers.google.com/identity/sign-in/web/backend-auth),
[Gmail scopes and verification](https://developers.google.com/workspace/gmail/api/auth/scopes),
[Drive app data](https://developers.google.com/workspace/drive/api/guides/appdata).
