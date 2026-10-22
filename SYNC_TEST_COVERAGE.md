# Compact sync and reusable authentication coverage

Validated on 21 October 2026. The production build/type-check, `pip check` and
PrimeVue MCP validation pass. The final full gate passed **528 backend/tooling
tests and 136 frontend tests**. Two opt-in real-Google probes were skipped because
provider configuration/consent was not supplied. The focused sync/migration/auth/
tooling gate also passed 102 backend tests and 21 frontend tests. The complete
full-gate log is saved locally at `.run/sync-final-validation.log` (exit status 0).

## New behavior covered

| Area | Evidence |
| --- | --- |
| Independent offline replicas | Two separate SQLite databases/devices create records offline, merge disjoint edits, converge in either sync order and preserve local descriptions. |
| HTTP end to end | Two independent FastAPI lifespans, databases and credential stores use the production GoogleConnection and DriveTransport. Only Google's HTTP responses are simulated. Covers paginated discovery/feed, multipart encrypted uploads, downloads, offline REST edits, bidirectional convergence and reviewed conflict resolution. No Gmail calls occur. |
| Conflict safety | Competing fields, close/interview contradictions, delete/edit, follow-up sequence collisions, later unrelated edits and competing human resolutions retain conflicts. Stale resolution submissions are rejected. |
| Causality | All 24 delivery permutations of a four-event, three-branch history produce equivalent state. Missing ancestors remain pending until available. |
| Transaction/replay safety | Domain changes and outbox rows roll back together. Duplicate files/events are idempotent. Lost upload responses reconcile the durable encrypted upload intent. |
| Privacy and integrity | Events and checkpoints reject descriptions, message content, contacts, notes, free-text interview results, document identifiers/paths and credentials. Wrong keys, altered headers/ciphertext, unsupported versions and decoded-size violations fail closed. |
| Failures/recovery | Quota/rate-limit/provider/auth failures retain local edits and schedule backoff. Expired cursors rediscover safely; missing remote files never delete records. Corrupt batches do not advance cursors. Restores rotate device identity and retain pre/post-restore pending edits. |
| Interrupted merge and worker recovery | Inbox/journal/dirty work commits atomically before applying a page. A replacement engine completes staged work after a simulated interruption. Background checks survive transient exceptions without exposing their exception bodies. |
| Incremental query budgets | Idle checks read no journal payloads and issue fewer than 50 SQL statements with unrelated history present. Small downloads stay below 100. Queue/index migration backfills existing histories without changing event IDs. |
| Bounded checkpoint work | Small forced file limits exercise multipart generations, snapshot consistency and a simultaneous independent local write during encryption. Existing-data enrollment does not select excluded descriptions, message bodies or subjects. |
| Domain import | Imported children preserve relationships and task completion timestamps. Import/restart does not prepare messages or create automatic follow-ups for imported applications. Missing message content cannot be copied, approved or drafted until explicitly prepared locally. |
| Human setup/UI | Setup requires local-human/session access, expected origin and explicit encrypted-storage consent. Agent bearer headers cannot initialize sync. Recovery exports never appear in status. UI tests cover disabled setup, secret hiding, stale conflict responses, preserving reviewed choices across refresh and clearing confirmation when a value changes. |
| Reusable sessions | A standalone in-memory store demonstrates session replacement, shared validation/revocation, exact expiry, credential-version invalidation and capacity without tracker/ORM/FastAPI dependencies. Existing hosted cookie/CSRF/login tests still pass. |
| Reusable API authorization | An unrelated provider adapter demonstrates injected tokens/HTTP/invalidation. Only authorization failures invalidate credentials; 403 rate limits, full storage and server failures retain them. Unsafe destinations are rejected and uncertain writes are not retried automatically. |
| Upgrade compatibility | A populated 0022 database upgrades without enabling sync, changing Google credential references or clearing private descriptions. Existing application, Gmail, agent, follow-up and backup tests remain in the full gate. |

The sync feature has 51 collected cases: 50 offline cases and one opt-in live
cross-client probe. This is behavior coverage, not a measured line/branch
coverage percentage. Crash-boundary tests exercise rollback and lost responses;
they do not constitute process-kill testing at every persistence instruction.

## Visible verification

Two isolated previews on ports 8021/8022 used synthetic data and the same simulated
Google HTTP boundary as the API E2E tests. Browser actions initialized the first
workspace, paired the empty second workspace using its recovery export, downloaded
the original record, edited the company independently in both browsers, selected
the second replica's proposal, refreshed without losing the reviewed choice,
confirmed it and synchronized both replicas. Both showed zero pending changes and
conflicts. API reads confirmed matching company values, preserved desktop-only
description and no description on the imported copy.
Screenshot: `output/playwright/sync-http-e2e.png` (ignored local artifact).
PrimeVue MCP checked 67 usages with none needing review. The existing frontend
also displays an "Invalid PrimeUI License" notice in this preview; the configured
`VITE_PRIMEUI_LICENSE_KEY` integration needs a valid operator-supplied key for a
release. This notice did not block the tested sync flow.

## Measured engine bottlenecks and fixes

`scripts/sync_e2e_benchmark.py --sizes 1000` creates two real SQLite replicas and
runs the production encrypted engine against a simulated object store. It asserts
record count and ten-edit convergence. Timings below are single local runs, vary
with machine load and exclude real Google/network latency.

| Phase, 1,000 applications | Before | After | SQL before → after |
| --- | ---: | ---: | ---: |
| Initial upload/checkpoint | 7.116 s | 2.769 s | 8,116 → 3,132 |
| Peer bootstrap | 8.807 s | 5.511 s | 16,094 → 9,189 |
| Idle check | 2.875 s | 0.011 s | 3,021 → 18 |
| Ten-edit upload/catch-up | 4.390 s | 0.919 s | 6,125 → 199 |
| Ten-edit download | 2.192 s | 0.084 s | 3,125 → 136 |

The old receive path remerged every entity even when nothing changed. A durable
dirty-record queue now limits merge work to changed records and dependent children.
Hot lookup indexes, bulk event staging/outbox updates and payload-free acknowledgment
scans remove unnecessary ORM hydration. Inbox staging survives interruption. A new
deterministic E2E regression also caught and fixed a child-ordering bug: a reviewed
follow-up resequencing now unblocks its sibling on the peer without another edit.

## Synthetic benchmark

`scripts/sync_benchmark.py` generates the real migrated SQLite schema, excluded
large descriptions/requirements, 5–15 edits per application, 0–2 interviews and
0–3 follow-up records. All data is synthetic. MB below means decimal MB.

| Applications | Events | SQLite incl. journal/indexes | Encrypted checkpoint total | Checkpoint parts | Encrypted journals | Total files |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1,000 | 13,494 | 33.92 MB | 0.742 MB | 14 | 0.890 MB | 149 |
| 10,000 | 134,994 | 338.19 MB | 7.416 MB | 135 | 8.902 MB | 1,485 |

Checkpoint files now hold at most 1,000 events or approximately 1 MiB of event JSON.
The engine streams a consistent WAL snapshot while allowing local edits, then
persists encrypted intents atomically. Readers stage each authenticated file
separately. All causal history remains retained; this is bounded-file encoding,
not bounded-history compaction or GC.

The 10,000-application serialization run peaked at 8.61 MB of traced Python
allocations versus about 697 MB in the earlier eager benchmark. The script also
stopped retaining all generated input in Python, so this comparison measures the
whole serialization harness change, not application RSS or full-engine bootstrap.
The 1,000-application cold run peaked at 17.28 MB including initialization overhead.
At 10,000, measured encryption totaled 19.58 s and decoding 27.06 s under tracemalloc;
the previous single-file encoding was 10.51 s. Bounded files trade some compression,
CPU and request count for lower allocation peaks and shorter write locks. The new
harness also verifies decoding and streams SQLite input, so total elapsed times
are not directly comparable. A ten-event encrypted payload was 1.65 KB.

Reproduce with `scripts/sync_benchmark.py --sizes 1000 10000`. Results are saved
under ignored `.run/`. These figures exclude binary documents and do not measure
IndexedDB, real Google request costs/latency, full live bootstrap or GC/compaction.
Fresh discovery currently downloads both journals and checkpoint parts, so the
10,000-application workload represents about 16.32 MB of encrypted discovery
payload, not just its 7.42 MB checkpoint. A checkpoint/manifest bootstrap that
safely skips covered journals remains future work.

## Not verified or implemented yet

Live cross-OAuth-client appData visibility, consent, browser authorization and
Android/iOS behavior require the operator's Google configuration and devices.
The user confirmed Google is intentionally unconfigured during prototype work.
The independent offline phone replica, browser key wrapping, QR pairing,
bounded-history bootstrap, device retirement/key rotation and safe journal
garbage collection remain subsequent work. No live user data was uploaded.
