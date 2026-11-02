# Independent phone sync

The phone app is at `/phone/`. It is a separate Vue entry point with its own
IndexedDB database and offline app shell. It talks directly to Google Drive;
viewing, unlocking and editing downloaded records do not require the desktop
process. Existing hosted-workspace phone access continues to use the shared API.

## Google setup and live compatibility

1. In the desktop OAuth client's Google Cloud project, enable **Google Drive API**
   under **APIs & Services → Library**. Adding a consent-screen scope does not
   enable its API.
2. In **Google Auth Platform → Data Access**, add
   `https://www.googleapis.com/auth/drive.appdata`. The phone requests identity
   (`openid email`) and this app-data permission. Desktop Gmail capabilities
   remain independent.
3. Create a separate **Web application** OAuth client for the phone. Register its
   HTTPS hosting origin under **Authorized JavaScript origins**. For a local
   cross-client check, also register `http://127.0.0.1:8000`. The GIS popup token
   flow used by the phone needs no client secret in browser code and no callback
   redirect URI.
4. In desktop **Settings → Connections → Google**, grant Drive and reconnect.
   Under **Set up or manage device sync → Verify the phone Google client**, enter
   the Web client's public ID. Authorize the same account for the Web client and
   run the check from an origin registered on that client.

The live check exchanges only empty encrypted probe batches. Each OAuth client
must discover and decrypt the other's file and observe it through its own change
feed. Cleanup authenticates the exact probe contents before removing files; it
does not delete workspace journal files. The desktop and browser keep their own
OAuth tokens. A successful sign-in or local mock test is not this acceptance check.

If Google's account picker stalls after an earlier sign-in, use **Use existing
Google sign-in** in the check panel. This lets Google reuse its existing session;
Google still requests authentication or consent when necessary, and the check
still verifies that both clients use the same account. The desktop's verified
account email is supplied as Google's optional login hint during this retry.
The normal connect button
continues to request account selection.

The prototype's separate desktop/Web client check passed live on 29 October 2026
at its registered localhost origin, including reciprocal discovery, decryption,
change-feed observation and cleanup. The checker briefly polls read-only evidence
because Google can acknowledge an upload before publishing its change. Uploads
are not replayed. Actual Android/iPhone installation remains separately required.

Desktop probes expire after ten minutes and live receipts are held in memory.
Finish each check before restarting the backend. A backend restart or a provider
outage during an uncertain first probe upload can leave an empty encrypted test
object behind; it contains no tracker records. Such unrelated workspace removals
do not become local record deletions or block normal catch-up.

## Pair and use the phone

1. On desktop, open **Settings → Phone** and press **Pair phone**. This explicitly enables compact encrypted
   Google storage, enrolls a new workspace if necessary, runs the first sync,
   and prepares a private pairing QR. Existing workspaces reuse their key.
2. Scan the QR on Android. Choose and confirm an offline passphrase, then press
   **Connect and sync**. Google sign-in/approval, enrollment and the first phone
   download happen in that flow. No recovery-key copy/paste or public client ID
   entry is needed. First-time private Site sign-in may require rescanning.
3. Once the offline shell is ready, install using Chrome's menu. Browser install
   approval and Google consent remain controlled by the browser/provider.
4. After reopening, unlock with the local passphrase. Downloaded summaries and
   work stay available offline; foreground sync catches up automatically.

The private pairing QR grants recovery access. Do not share or photograph it.
It is generated locally after the human-only no-store API response, never sent
as a query parameter, persisted, or uploaded to Drive. The phone consumes its
URL fragment and removes it from browser history before mounting/loading GIS.
Hiding the QR after five minutes clears the UI; it does **not** revoke a key
someone has already copied. Keep a recovery export separately under advanced
setup. A scanned QR cannot replace an already-paired browser vault.

Manual recovery pairing remains available under **Advanced setup and recovery**.
Google compatibility diagnostics are also under advanced settings. These are
operator tools rather than steps in everyday phone setup.

Google must be reconnected after the page restarts or its in-memory access token
expires. Offline unlock does not require Google. Sync runs in the foreground,
after a three-second local-edit debounce, after network/visibility resume and at
five-minute intervals while connected and unlocked. Background mobile execution
is not assumed. Manual **Sync now** overrides a provider backoff.

The phone locks after five minutes without activity and on page departure.
Returning from a suspended app checks elapsed wall time before catch-up. Locking
clears the usable key, token, displayed records, review choices and edit forms.

Conflicting values are retained for review. A reviewed resolution covers the
current branch heads; stale edits/resolutions are rejected. Follow-up sequence
collisions support a reviewed replacement number. Follow-up READY/SENT values are
observations: they never approve local message content, create a draft or send mail.

Documents, contacts, notes, full job descriptions and message content do not enter
this protocol. Keep a desktop portable backup and the recovery export separately.
Browser storage can be cleared or evicted; unsynchronized edits then cannot be
recovered from Drive. The app requests persistent storage where supported.

## Static deployment

The HTTPS phone shell is hosted independently at
`https://application-tracker-phone-sync-20261029.heartygleam1024.chatgpt.site/phone/`.
The Site is owner-private, so its initial visit can require your ChatGPT sign-in.
Tracker records stay in the encrypted browser vault and Google Drive; the Site
hosts static assets only. Desktop continues at `http://127.0.0.1:8000` and need
not remain online for phone edits to reach Drive.

Desktop **Settings → Phone** includes **Pair phone**, also available under device sync in Connections. Its
private QR carries the recovery export in a URL fragment for `VITE_PHONE_URL`;
the ordinary public app link contains no key. Keep private pairing QRs secret.
Register the exact HTTPS origin on the existing phone Web OAuth client, retaining
the localhost origin. No client secret belongs in the static app.

`pnpm --dir frontend build` builds both entry points. The FastAPI app serves
`/phone/`, its manifest and its separately scoped worker alongside the desktop UI.
The phone shell is public static code; tracker API routes keep their existing
authentication. Hosted CSP allows the phone's GIS script and Google API requests.

For independent static hosting:

```powershell
pnpm --dir frontend build
.\.venv\Scripts\python.exe scripts/package_phone.py
```

For a fresh isolated Sites checkout whose `.openai/hosting.json` retains the
registered project ID, add `--site-directory <checkout>` to prepare an empty
`dist/` from the same validated public allowlist. Existing output is preserved;
use a fresh output directory when rebuilding. Follow the Sites source workflow
to commit/push/package that isolated checkout, then deploy its exact version.

Deploy `output/phone-app.zip` to the root of an HTTPS static origin and open
`/phone/`. It includes only the phone HTML/worker/manifest, referenced public assets
and icons. No backend, `test.md`, workspace database, `.env`, recovery key or OAuth
tokens are included. The package rejects a simulated browser-test build.

The public ID may optionally be supplied before building with
`VITE_PHONE_GOOGLE_CLIENT_ID`; the setup field also accepts it directly. This is a
public browser identifier. Never place a client secret in a `VITE_*` variable.

## Drive footprint

The default stores gzip-compressed encrypted change batches. Idle sync and pairing
into an existing workspace upload nothing. A brand-new empty workspace writes one
small authenticated bootstrap; a populated workspace bootstraps from its changes.
Periodic full-history snapshots and receipt-only acknowledgments are disabled by
default, avoiding duplicate cloud history. Explicit recovery checkpoints and reads
of older checkpoints remain supported. Real outgoing changes carry causal vectors.

Only compact allowlisted fields are transmitted; descriptions, attachments and
message bodies are excluded. History still grows with actual edits. Garbage
collection remains disabled so a device that has been offline can merge safely;
this is not a fixed-size storage guarantee or a replacement for desktop backups.

## Reusable boundaries

All phone core modules are under `frontend/src/phone/core/`, without Vue or tracker
API imports:

- `auth.ts`: injected token acquisition, identity HTTP, clock and required scopes;
  `Authorization` can be implemented by another provider. Tokens remain in memory.
- `storage.ts`: `ReplicaStore` interface plus encrypted IndexedDB implementation.
  Crypto runs outside its short atomic transaction; revision checks protect
  against stale tabs. A full storage failure rolls back the event, sequence,
  outbox and projection together.
- `drive.ts`: injected authorization/HTTP; immutable uploads, pagination and typed
  provider errors. Uncertain writes are reconciled, never automatically replayed.
- `protocol.ts` / `crypto.ts`: strict Compact Sync v1 validation, causal merge,
  gzip/AES-GCM envelope, account-bound recovery and local key wrapping.
- `engine.ts`: injected store/transport/clock, durable inbox/outbox/intents,
  dependency reapplication, cursors, human conflict resolution and retry state.
- `compatibility.ts`: live cross-client acceptance with an injected desktop probe API.

`runtime.ts` composes these adapters. `PhoneApp.vue` owns presentation and lifecycle.
Python's independent `session_manager.py` and `authorized_api.py` remain reusable.
Browser vault keys use PBKDF2-SHA-256 (600,000 iterations) and AES-256-GCM; records
and queue payloads are encrypted at rest as well as on Drive. Public account,
workspace, device and queue-index identifiers remain local metadata.

## Device acceptance still required

On each real device, pair and install, sync in both directions, enable airplane
mode, close/reopen/unlock, edit an application and a task, reconnect and verify
desktop convergence. Repeat with a conflict, an expired Google session, background
suspension beyond five minutes and storage-loss recovery into an empty profile.
Check that local messages/documents remain absent from the imported copy.

Chromium layouts at Android/iPhone-sized widths do not establish Android hardware,
Safari, or installed iOS behavior. Detailed local test evidence and outstanding
acceptance results are kept in ignored `test.md`.
