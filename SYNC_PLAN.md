# Compact Google Drive sync implementation

The approved design is implemented in stages. Phone and desktop will hold equal
local replicas. Drive transports encrypted immutable events; documents, notes,
contacts, message content and credentials never enter this protocol.

## Implemented desktop foundation

- Migration 0023 adds an opt-in workspace, device identity, causal journal,
  immutable upload intent, inbox, per-record state, conflicts and checkpoints.
- Migration 0024 adds a durable dirty-record work queue and hot-path indexes.
  Existing histories are queued once on upgrade. Imports stage each authenticated
  file atomically, then merge only affected records and blocked dependent children.
- Domain edits and their compact events commit or roll back together. REST,
  MCP, background services and undo share the ORM journal hook. Imports suppress
  journaling and use a dedicated validated projection rather than creation APIs.
- Strict versioned field schemas apply to events and checkpoints. Task completion
  timestamps are included; interview free-text results are excluded. Local UI
  revisions, approval revisions and message content are never imported.
- AES-256-GCM authenticates workspace/batch/version/hash. Gzip precedes encryption;
  input and decoded sizes are bounded. Recovery secrets use the native OS store.
  Recovery exports contain a keyed binding to the verified Google subject, so
  copying ciphertext into a different account cannot enroll that account.
- Full discovery starts with a change-feed token, then paginated listing, followed
  by feed catch-up. Cursors commit with durable inbox staging. Repeated event IDs
  must have identical content; duplicate filenames do not identify records.
- Device sequences and ancestry drive merges; clocks do not select winners.
  Disjoint summary edits merge; competing values, protected transitions and
  follow-up sequence collisions enter a durable human review queue. Resolutions
  cover the current branch heads and reject stale submissions.
- Imported follow-ups cannot copy missing content, approve it or request drafts.
  Preparing local message content explicitly restores the existing review flow.
  Startup does not prepare imported follow-ups or generate automatic follow-ups
  for imported applications. Automation remains with the originating local
  application; this is a side-effect policy, not merge precedence.
- Background desktop checks debounce outbox edits by three seconds and poll every
  five idle minutes. Manual checks are available in Google settings. Provider
  errors retain pending edits and use bounded exponential backoff plus jitter.
  Unexpected check failures are retried rather than permanently stopping the worker.
- Checkpoints are created initially, after 1,000 events or 30 days. This first
  implementation streams a consistent SQLite snapshot into immutable checkpoint
  parts (at most 1,000 events or roughly 1 MiB event JSON each), without holding
  the write lock while encoding. It retains all causal history. Journal deletion is
  disabled: bounded-history bootstrap and safe GC are not claimed complete.
- Restoration assigns a fresh device identity, preserves existing event IDs and
  pending edits, disconnects Google and requires the original recovery export.

## Reusable authentication/session boundaries

`backend/app/session_manager.py` uses only the Python standard library. Inject a
`SessionStore`, credential-version callback and optional clock. The store owns
atomic pruning/replacement/insertion; the manager owns random opaque token
issuance, digest validation, expiry, credential changes and revocation.
`SqlHumanSessionStore` adapts the existing tracker schema; `HumanSessionManager`
retains HTTP/session compatibility. Cookie/CSRF policy stays in the web adapter.

`backend/app/authorized_api.py` injects credential acquisition, HTTP and a
generation-aware invalidation callback. It has no tracker, ORM or FastAPI imports.
Rate limits and full storage do not revoke permission. It never retries uncertain
writes. `OAuthSessionManager[T]` remains provider independent and single use.

## Required live gate before phone implementation

Use two independently consented OAuth client types in the same Google Cloud
project/account. Verify each can list/decrypt files written by the other, and can
observe them through the changes feed. Never transfer refresh tokens between them.
The mocked store tests do not establish appData visibility across OAuth clients.
Run `backend/tests/sync/test_live_cross_client.py` only after explicitly setting
its opt-in and both already-connected workspace data directories.

## Remaining phone and lifecycle work

- Independent static HTTPS Vue PWA, IndexedDB transaction/outbox storage, shared
  Python/TypeScript protocol fixtures and offline app-shell installation.
- Verified Google identity plus separate Drive-only authorization, user-driven
  access-token renewal, secure recovery-key wrapping and offline unlock.
- QR pairing, global status badges, foreground/network-resume triggers, Android
  Chrome and installed iOS Safari testing.
- Bounded-history checkpoint bootstrap, active-device retirement, safe retention,
  explicit compromise recovery/key rotation and browser storage-loss recovery.
- Benchmark IndexedDB, actual Google request counts/bytes and anonymized real
  workspaces. Synthetic measurements do not establish 100,000-record support.

## Validation

Detailed results and explicit limits: [SYNC_TEST_COVERAGE.md](SYNC_TEST_COVERAGE.md).

Run `.\.venv\Scripts\python.exe scripts/test.py --segment sync auth agent followups`
during changes and `--full` before delivery/pushing. New tests cover two-replica
offline convergence, conflicts/resolutions, ordering, encryption/schema rejection,
replay, upload uncertainty, provider failures, recovery, human endpoint restrictions
and the framework-independent session/auth adapters. Follow-up, migration and
existing Gmail/agent tests remain part of the full gate.

Synthetic sizing: `.\.venv\Scripts\python.exe scripts/sync_benchmark.py`.
Engine/query profiling: `.\.venv\Scripts\python.exe scripts/sync_e2e_benchmark.py`.
Generated data/results stay under ignored `.run/`; no real private data is read.
