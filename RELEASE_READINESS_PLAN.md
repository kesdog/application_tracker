# Application Tracker release readiness review

Review date: 22 October 2026. Implementation authorized on 22 October; delivery is tracked below.

## Implementation status

| Phase | Current state |
| --- | --- |
| 0 | Existing local feature work reconciled into the release baseline. Single-workspace/local-first boundaries retained. The supplied SSH credential has not been used; rotation remains an owner action. |
| 1 | Export literal handling, persisted posting-check catch-up, stale-source rejection, upload limits, complete hashed locks and clean Windows installation implemented. Windows parser/runtime data omissions found through executable testing and fixed. Paired Linux/Windows CI added; remote Linux acceptance remains pending until its first run. |
| 2 | Settings now supports reviewed CSV/XLSX import, replay-safe saving, persistent account-scoped mail review, explicit reply/reminder choices, duplicate consolidation, Trash restoration, full backup downloads and isolated recovery verification. Packaged and source recovery commands restore into a new empty directory. Deadlines appear in upcoming work. Restored/consolidated reminders require review. |
| 3 | Optional authenticated encrypted server credential store and Compose overlay implemented; live values linked through `.env.example`, private `.env` placeholders and `deploy/hosted.env.example`. User confirmed clients/hosting are not configured. Real consent, cross-client Drive behavior, HTTPS and physical devices remain required gates. |
| 4 | Not started: the approved plan requires successful live desktop/web Google compatibility before implementing the independent phone client. Compact sync privacy boundaries are unchanged. |
| 5 | Pinned candidate CI/build/smoke foundations added. Stable publication, signing, hosted version activation and Upgrade/Later/Skip installation remain subsequent work after the connected/mobile gates. No automatic installation or live deployment enabled. |
| 6 | Synthetic email-review/import flows and phone-width layout verified. Clean-environment full gate and installed/packaged recovery/startup checks pass. A real-device/everyday-use pilot remains pending. |

The finding table below records the original audit; this status table identifies delivered changes. See CHANGELOG.md, TESTING.md and RECOVERY.md for the implemented interfaces and current checks.

## Assessment

The core tracker is substantially implemented. The remaining work is chiefly complete user workflows, safe recovery, real provider/device validation, and repeatable delivery. The independent offline phone app and optional unattended AI runner are separate unfinished capabilities.

The existing V1 plan is no longer an accurate implementation inventory: it still defers backups, although a backup/restore CLI exists, and predates substantial follow-up, Google, onboarding and sync work. Replace overlapping completion claims with this release checklist and explicit acceptance evidence.

## Evidence reviewed

- Local source, tests, migrations, build configuration, dependency locks, README, TESTING.md, PLAN.md, FOLLOWUP_PLAN.md, SYNC_PLAN.md, SYNC_TEST_COVERAGE.md, and the local `.run/ci-cd-plan.md`.
- Related chats: **frontend**, **Consolidate tests by code area**, **Add phone and desktop sync**, **Plan shared agent integrations**, **Plan follow-up automation**, **Plan Application Tracker Features**, **App Sync Design**, and **Branch · Contact Discovery Worker**. Some ChatGPT-backed historical responses were returned as references/truncated content; implementation conclusions below rely on local source and the accessible Codex chat content.
- Prior decisions retained: local use without sign-in; optional Google/AI/notifications; one logical agent and mailbox; human-reviewed drafts; Windows and hosted releases; users choose Upgrade/Later/Skip; minimal encrypted Drive data.
- Fresh validation results are recorded below. Historical test totals are not treated as validation of today's checkout.

## Already implemented

Applications/lifecycle, search and filters, advisory duplicate detection, notes/tasks/interviews, attachments, timeline/audit/undo, CSV/XLSX export, manual prepared/ready/sent follow-ups, templates, durable follow-up notices and push delivery, hosted password sessions, installable online phone shell, agent REST/MCP, Google integration adapters, recipient research, encrypted desktop replica sync, and optional onboarding.

These foundations need acceptance on their shipping targets; their existence does not establish clean-machine installation, real Google interoperability or actual phone background delivery.

## Verified gaps and risks

| Priority | Finding | Evidence and consequence | Required completion |
| --- | --- | --- | --- |
| P0 | Spreadsheet formula injection | `backend/app/exports.py` writes strings directly. An isolated call to the real exporter with company `=1+1` produces XLSX cell type `f`; CSV preserves the same prefix. | Treat untrusted text as literal text in both formats. Cover relevant spreadsheet formula prefixes and preserve normal dates/numbers. |
| P0 for distribution | Release builds are not reproducible from the current gate | Docker resolves Python dependencies anew; base tags float; the development lock has unmarked Windows packages and misses parts of the actual test environment. `pip check` verifies the installed environment only. No `.github/workflows` exists. | Fresh Windows/Linux installs, platform-aware complete locks, required CI, and actual artifact startup/migration checks. |
| P0 for hosted Google | No configured headless credential vault | Default Google and sync secret storage accepts native OS vaults. The slim container configures no Secret Service/KWallet backend and no production alternative is wired. | Implement/configure a persistent protected server credential store and prove reconnect/restart/restore. Keep local tracking independent of it. |
| P0 operational | A private SSH key was supplied in the chat instructions | This review did not use or reproduce it. A targeted repository scan did not find a private-key header in the scanned source/config files; that is not a complete history audit. | Rotate/revoke that credential before release automation uses GitHub access, and use normal secret configuration. |
| P1 | Gmail review has no resolution workflow | `ApplicationSyncControl.vue` links to at most 20 emails. There are no receipt resolve/link/ignore endpoints. Review identity is held in `ApplicationSync.account`, which starts empty after restart. | Persistent, paginated review queue; link to existing application, create after review, ignore/dismiss, correct import and retry. Persist decisions and show outstanding reviews after restart. |
| P1 | Periodic posting checks can be starved by restarts | `PostingCheckScheduler.__init__` sets `last_run` to now, and `refresh` waits the configured interval. A desktop run shorter than the default 24 hours never reaches a scheduled scan. Per-record check timestamps do not drive selection. | Persist/use per-record due times, catch up on startup, spread bounded work, and reject stale results if the source URL changed during a check. |
| P1 | Employer replies do not complete the follow-up loop | Manual employer-reply notes reset unanswered counts, but Gmail import does not record that event. It can classify an interview while leaving an older follow-up actionable. | Reviewable reply detection; explicit keep/pause/reschedule/archive decision for existing follow-ups; preserve human edits. Do not infer a send or rejection. |
| P1 | Recovery exists as an operator CLI, not a complete ordinary-user experience | `app.backup` backs up DB/documents and restores to an empty destination; it requires the app to stop for document consistency. CSV/XLSX are partial exports. No Settings backup/restore or Trash application restore is exposed. | Safe backup/recovery path from the distributed app, last-success visibility, retention/off-device guidance, deleted-record restore and staged restore validation. Do not expose live unsafe copying through a button. |
| P1 | Independent mobile client absent | `frontend/public/sw.js` caches offline guidance/icons and intentionally excludes private data. There is no independent IndexedDB replica/offline app shell. | See mobile phase below. The current PWA needs a reachable backend. |
| P1 | Sync lifecycle is incomplete | Desktop protocol exists, but live cross-OAuth-client tests are opt-in/unrun in the previous evidence. Bounded-history bootstrap, safe GC, key rotation/device revocation and browser recovery remain open. | Verify Google compatibility before the phone implementation; prove recovery and supported capacity/version boundaries before a broad sync release. |
| P1 | Upgrade policy exists only as a plan | The other chat chose paired Windows/hosted releases and optional upgrades. No release catalog, updater, hosted version selection or compatibility policy is implemented. | Preserve the agreed choice and prove artifact verification, backup, migration and recovery. |
| P1 | Real-target evidence is missing | Existing Windows executable is dated 25 September and predates the current features. Docker is unavailable on this machine. Prior notes explicitly leave actual iOS/Android and live Google checks pending. | Current clean-machine Windows package and Linux image tests, real phones, real HTTPS and provider acceptance. |
| P2 | Public distribution polish | No root application LICENSE, SECURITY.md or CHANGELOG was found. The configured PrimeUI license requires a valid build-time value; the Docker build currently has no explicit license injection. | Choose a license, dependency notices, support/security channel, release notes, and a documented clean build that handles the client license correctly. |

## Product boundaries to settle before adding scope

1. **Phone capability matrix.** Compact sync intentionally excludes contacts, notes, documents, message subjects/bodies and credentials. It also omits application reminder-pause preferences and interview meeting details. A synced phone therefore cannot simply reproduce the desktop draft/editor experience. Specify what is viewable/editable, where drafts are prepared, how pauses affect the originating reminder worker, and where conflicts are resolved. Preserve the agreed minimal data boundary; do not silently widen it.
2. **Reminder availability.** An independent phone replica with foreground Drive checks does not provide an always-running reminder sender. The existing Web Push sender requires a running backend. Choose the promise: optional always-on hosted reminders, calendar fallback, or a separately researched phone-native scheduling capability. Demonstrate behavior with the desktop off and phone app closed.
3. **Release audience.** The current system is one workspace, one mailbox, one logical agent, and one SQLite writer per instance. Ship that clearly. A shared public multi-tenant service would need a different isolation/account/operations plan; it should not slip into V1 by implication.
4. **Google distribution.** For a broadly distributed Gmail-connected app, decide how users obtain a production OAuth connection. Google's current scope documentation categorizes both `gmail.readonly` and `gmail.compose` as restricted; verification and potentially a server-data security assessment need an explicit plan, subject to documented exceptions. Personal/testing use is a different gate. Also, compose permission includes sending even though this app exposes draft creation only: describe the application behavior and granted provider permission accurately.

Sources: [Gmail scope definitions](https://developers.google.com/workspace/gmail/api/auth/scopes) and [restricted-scope verification and exceptions](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification).

## Phased delivery

### Phase 0 — Freeze the release contract and reconcile the checkout

- Inventory and review the substantial current uncommitted/untracked feature work. Produce a coherent versioned baseline and migration inventory without accidentally omitting sync/onboarding/import files or including personal data.
- Replace stale plan claims with one feature/status matrix: implemented, acceptance pending, unfinished, explicitly deferred.
- Record supported Windows/Linux/browser/phone targets, single-workspace boundary, phone capability matrix and reminder availability promise.
- Rotate the supplied SSH credential and configure release credentials privately.

**Exit:** exact reviewed source baseline and agreed V1 acceptance checklist; no secret material in distributable source/artifacts.

### Phase 1 — Make the core safe and repeatedly testable

- Fix formula export handling and restart-starved posting scheduling.
- Add missing regressions for restart catch-up, source-URL changes during checks, and literal spreadsheet exports.
- Complete fresh dependency installation on Windows and Linux, then run the existing full gate in required read-only CI.
- Exercise migration from a populated older schema; test the produced Windows package and Linux image with isolated synthetic data.
- Define and enforce document upload size/storage limits and useful full-disk errors before broad hosted use.

**Exit:** clean Windows/Linux checkout builds pass; both artifacts start; data survives migration/restart; these checks are reproducible outside the development venv.

### Phase 2 — Complete the everyday human workflow

- Implement persistent Gmail review and correction/ignore/link/create actions.
- Close the employer-reply/reminder loop, with a reviewable decision and no automatic sending.
- Add safe backup/recovery UX and application Trash/restore. Make backup status actionable.
- Add CSV/XLSX import with mapping, preview, validation and duplicate choices. This is the strongest missing adoption feature for people arriving with existing trackers.
- Offer a reviewed duplicate-merge workflow that preserves child records, references, documents and audit history; do not merge on name similarity automatically.
- Surface recorded application/selection deadlines in the upcoming-work view. Decide whether deadline notices are included; existing push currently serves follow-up notices, not every kind of due work.

**Exit:** a new user imports existing data, tracks an application, reviews a reply, handles follow-ups, fixes a mistaken import/deletion and recovers a backup using the supported UI/launcher path.

### Phase 3 — Prove Google and hosted operation

- Run the live desktop/web OAuth appData interoperability gate before investing in the independent phone engine. Stop and revise the transport if it fails.
- Validate real consent, account switching, revoked/expired access, provider throttling, mailbox draft reconciliation and Drive convergence without copying refresh tokens between clients.
- Resolve the hosted secret-store gap; provision HTTPS, persistent storage, external health checks and tested backups/recovery.
- Complete the applicable public OAuth verification/distribution work, or explicitly limit the initial beta to personal/test users with the manual core available to everyone else.
- Test the existing online PWA and optional push on physical Android/iPhone devices, including app-closed delivery, expired login, deep links, quiet hours and downtime catch-up.

**Exit:** both hosted and Windows candidates work against their intended real services; published claims match the tested target audience and devices.

### Phase 4 — Deliver the independent phone experience

- Implement the static HTTPS phone PWA, IndexedDB transactions/outbox, offline shell and Python/TypeScript protocol fixtures.
- Implement verified identity, Drive authorization, foreground token renewal, encrypted key storage/offline unlock, pairing and storage-loss recovery.
- Apply the capability matrix: unavailable desktop-only content is explicit, and phone state changes have clearly defined reminder behavior.
- Prove offline edits in both directions, same-field conflicts, deleted records, clock differences, refresh/restart recovery and desktop-off operation on real devices.
- Complete or constrain bounded-history bootstrap, retention/GC and compromised-device key rotation. Publish tested data limits.

**Exit:** two real devices work offline independently and later converge; loss/replacement of either device has a demonstrated recovery path. This is required to call the no-always-on-tracker phone vision finished.

### Phase 5 — Ship and maintain both delivery tracks

- Implement the existing CI/CD plan: required checks against the current base, trusted automatic acceptance, one source/version identity, paired verified Windows/image artifacts and staged promotion.
- Publish versioned downloads/image digests, checksums, release notes and build provenance. Configure signing before an in-app installer.
- Implement Upgrade/Later/Skip for Windows and workspace-owner version selection for hosted instances. Publication makes a version available; it does not silently migrate existing users.
- Test cross-version sync/API compatibility, interrupted upgrades, failed migrations, rollback before new writes and preservation/reconciliation of writes accepted afterward.
- Complete licensing, third-party notices, build-time PrimeUI license configuration, support instructions and a privacy/retention/deletion description that matches the actual single-workspace product.

**Exit:** a green trusted change publishes both verified releases; existing installations stay on their chosen version until approval, and an accepted upgrade has a tested recovery path.

### Phase 6 — Pilot and release candidate

- Run a time-boxed everyday-use pilot on both delivery tracks with representative imported data, not just empty databases.
- Cover manual-only, Google-connected, offline phone, denied notifications and unavailable-agent configurations.
- Check keyboard navigation, focus/error recovery, contrast and narrow-screen touch workflows across the whole app.
- Retest restart/downtime/low-disk/connection-loss cases and a complete backup-to-replacement-machine restore.
- Close critical defects; leave lower-priority additions explicitly in the backlog rather than expanding the release indefinitely.

**Exit:** all agreed scenarios have dated evidence; no unresolved data-loss or inaccessible-workflow blocker; install/update/recovery instructions are usable by someone who did not develop the app.

## Valuable additions that can wait

- Local job-description snapshot for interview preparation after a posting disappears. Description/requirements fields already exist; capture/review can build on those without syncing private content.
- Saved searches, small bulk actions and simple response/interview conversion reporting after reliability/adoption work.
- Rich calendar integration; current explicit ICS export is sufficient for the initial release.
- Optional unattended AI runner. Shared AI requests and recipient jobs exist, but they do not establish an available general worker with long-poll leases, cancellation and recovery. Preserve manual copy/paste first.
- PDF/rendered-page improvements and domain/seniority matching fixes in the toolbox, with an independent benchmark that is not tuned to the same ten applications. Keep uncertain recipients unconfirmed.

Defer multi-user SaaS, native mobile stores, additional mail providers, multiple agent identities, advanced analytics and broad automation unless the release contract changes.

## Validation from this review

### Implementation delivery checks

- Final clean-environment push gate: **555 Python tests passed, 2 live-Google tests skipped, 135 frontend tests passed across 25 files**. Build/type-check and `pip check` pass; exit status **0**. Log: `.run/release-push-gate.log`.
- Official PrimeVue MCP validation: **71 component usages, 0 requiring review**.
- Fresh hashed-dependency installation and installed-artifact smoke pass: production UI, health, migrations, restart persistence, document upload, backup download and isolated recovery verification.
- Rebuilt Windows executable passes ZIP recovery into an empty directory, startup/health and clean shutdown. Parser data and the custom Python runtime's CA-policy file are bundled when required. Synthetic result: restore exit 0, startup exit 0.
- Browser verification confirms the review/reply/pause workflow and explicit spreadsheet import (one new record and one duplicate skipped). At a 390-pixel viewport, document width was 376 pixels. The preview still displays the PrimeUI license warning; a valid operator-supplied build key remains a production gate.
- No real Google/mail/push operations or production data migrations were performed. Live services and physical devices remain pending because the user confirmed they are not configured.
- The staged snapshot was scanned for private-key/token patterns and unexpected databases/build artifacts, with no findings. `AGENTS.md` remains local after automatic approval review rejected staging it because the supplied instructions contain a private key. No supplied SSH key was used.

### Original audit baseline

- Fresh full gate passed with `.\.venv\Scripts\python.exe scripts/test.py --full`: **536 Python tests passed, 2 live-Google tests skipped, 132 frontend tests passed across 24 files**, plus production build/type-check and installed-environment dependency consistency. Exit status: **0**. Log: `.run/release-readiness-verified.log`; status: `.run/release-readiness-verified.exit`.
- The first sandboxed run stalled before application startup; a single-test faulthandler trace identified Python's local socket-pair creation, inside the asyncio test-client setup. Both stalled runs were interrupted. The unrestricted retry above completed successfully. This was not classified as an application defect.
- Python reported one upstream AnyIO/Starlette deprecation warning; no test failure. These totals are behavior tests, not a measured line/branch coverage percentage, and they do not include packaged-app or real-device/provider acceptance.
- Isolated export probe reproduced XLSX formula typing and CSV prefix preservation without opening Excel or using personal records.
- Local port 8000 did not provide a usable runtime response during the read-only status check. No app was started, no personal records were changed, and no live Google/mail/push operations were performed.
- Docker and physical-phone acceptance were not performed. Source review and offline suites cannot substitute for those gates.
