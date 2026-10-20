# Google connection setup and live checks

The tracker owns one Google account connection. Google tokens live in a native OS
credential store, under a namespace tied to the workspace path. SQLite contains
only identity, granted scopes, status, timestamps and a random store reference.
Backups contain no Google tokens. Restore requires reconnecting Google. Disconnect
removes the local credential; revoke the app separately in your Google account
to withdraw Google's grant. Existing Gmail drafts remain in Gmail.

## Configure

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
5. In Settings → Google account choose any combination of Drive app data, Gmail
   read and Gmail drafts, then Connect. Authorize in your normal browser.

Authorization uses code + PKCE S256, state, nonce, signed ID-token validation,
issuer/audience checks and a browser cookie bound to the initiating human session.
Pending links expire in ten minutes and are deliberately invalid after restart.
Reconnect pins the existing stable Google subject. Disconnect explicitly before
switching accounts. Starting a newer link or disconnecting invalidates older links.
New scope selections always open explicit consent; installed apps do not rely on
silent incremental authorization. Only selected and actually granted scopes become
tracker capabilities. No scope grants tracker agent permissions automatically.

## Behavior and failure recovery

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
- A receipt is committed before external draft creation. Successful identical
  retries replay it; changed arguments conflict. A timeout/crash leaves an uncertain
  operation blocked. Inspect Gmail and reconcile it manually before deliberately
  issuing a new operation ID. This avoids guessing whether Gmail accepted a write.
- Drive's optional test uploads only AES-GCM ciphertext to `appDataFolder`, reads it
  back, verifies and deletes it. Supply a random 32-byte base64 key that you generated
  and saved yourself. The tracker neither derives it from credentials nor stores it.
  This is transport groundwork; there is no database/phone synchronization.

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
