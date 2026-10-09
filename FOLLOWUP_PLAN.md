# Follow-up preparation, reminders, and optional AI execution

Status: the manual workflow, settings, variable editor, queue, durable in-app reminders, and shared AI requests are delivered. Phase 5 now supplies hosted authentication, phone installation, HTTPS configuration and portable backups. Actual server provisioning and real-phone acceptance remain pending; phone push delivery and the unattended runner remain later phases. No mailbox is connected and no external automation has been created.

## Implementation progress — 9 October 2026

| Phase | Current result |
| --- | --- |
| 1 | Persistent settings, prepared message snapshots, revisions, safe legacy migration and shared rendering implemented. |
| 2 | Editable default template, highlighted variables, searchable picker and live preview implemented in General Settings. |
| 3 | Atomic preparation on create/import, edit/copy/ready/sent, notes, actual-send correction, undo and successor preparation implemented. |
| 4 | Dedicated paginated queue, exact message links, snooze/reschedule/pause/archive and persistent grouped in-app notices implemented. Push delivery attempts, retry state and digest delivery await Phase 6. |
| 5 | Implemented: separate human login/sessions, CSRF/origin checks, HTTPS-only hosted configuration, private Docker/Caddy stack, phone installation shell and portable database/document backups. Pending acceptance: server/domain provisioning, container execution and real-device installation. Local loopback operation remains available. |
| 6 | Pending: Web Push subscriptions, push handlers, delivery/retry outbox and real-phone notification verification. The public offline service worker is ready; no phone notifications are delivered yet. |
| 7 | Versioned Copy AI instructions plus authenticated REST/MCP get_followup_request and revise_followup implemented, including customization and revision conflicts. Mailbox result reconciliation remains future work. |
| 8 | Deferred as planned: BSM-free unattended runner, leases and long polling. |

Verification covers legacy database preservation, deterministic rendering, immediate preparation, agent import idempotency, revision conflicts/concurrent editing, approval invalidation, send/undo scheduling, quiet hours and notice suppression. Frontend tests cover safe highlighting, selection replacement, unsaved edits, stale-save retention, clipboard fallback, server filters, deep links and grouped notices. Browser checks use an isolated QA database; production application data is not changed. A 390-pixel viewport check does not replace the actual-phone verification required for push.

The initial template is deterministic English text. Language and tone preferences guide manual edits and travel with AI requests; selecting French does not translate the template automatically. Saved messages retain their text until the user explicitly applies a refreshed-variable or latest-template preview. Reminder notices are currently in-app only, and the daily_digest setting is reserved for the future delivery phase.

The first increment passed 220 backend tests and 83 frontend tests, with browser verification of settings, immediate preparation, editing, Ready approval, copying, variable insertion/native undo and a 390-pixel viewport without horizontal overflow. The app was subsequently restarted and its 152 applications and 150 prepared follow-ups were preserved through migration 0016. Phase 5 validation and restart results are recorded below. Hosting provisioning remains pending.

### Phase 5 delivery

Hosted routes fail closed without a valid password hash and public origin. Browser sessions are stored as hashes, expire after the configured lifetime, survive process restart and are invalidated by password changes/logout. Origin/CSRF checks cover all human writes, including multipart documents; reads, exports and live events require sign-in. Agent authentication and permissions remain separate. A revoked session closes its live event stream.

The installable shell starts in Follow-ups, keeps deep links through login, and caches only public offline guidance/icons. Settings explains installation and online-only access. The Docker backend runs as a non-root user behind Caddy and persists data in a named volume. Backup/restore preserves messages and uploaded files, relocates Windows/Linux document paths, checks database integrity and refuses to overwrite existing data. [Deployment instructions](deploy/README.md) include password generation, updates, restore and server/phone acceptance checks.

Phase 5 automated verification: 230 backend tests and 92 frontend tests, including login/logout/expiry/restart/password rotation, persistent rate limits, agent/human separation, forged origin/transport/write rejection, stream revocation, backup/restore across Windows/Linux paths, login deep links and cache privacy. The frontend type-check and production build pass. Browser checks verified hosted sign-in, a protected settings save, sign-out, and installation guidance at 390 pixels without horizontal overflow. The local app was backed up and restarted with migration 0017, retaining 152 applications and 150 follow-ups. Docker is unavailable on the development machine, so the container build and HTTPS stack must be exercised on the selected server. Real iPhone/Android acceptance and Web Push remain pending.

## Agreed outcome

Every eligible application receives a prepared follow-up when it is added to the tracker. A user can edit the message, copy it into their mail client, mark it ready, and record it as sent without using an AI agent. An optional agent uses the same saved content and customization settings.

The first version has one editable default template in General Settings. Template variables are highlighted and selectable from all application data. The first follow-up is due seven calendar days after the original application date, with existing global and per-application overrides. Mobile access and notifications target an always-on hosted backend.

The visible message workflow is Prepared → Ready → Sent. Pausing, snoozing, and archiving are separate controls, not additional message states. Notes are sufficient for replies in this release. Direct mailbox integration, email-thread management, automatic sending, a template library, and BSM are outside this implementation.

## Product behavior and shared rules

### Templates and variables

Store a plain-text subject and body with variable tags. Display recognized tags as highlighted variables while preserving normal text editing, selection, undo, paste, and keyboard access. A searchable field picker inserts variables at the cursor. A separate preview shows resolved values for a selected or sample application.

Use stable canonical tags such as {company_name} and {position_name}. Map these to the existing company and job_title fields. Accept friendly aliases such as {company name}, {company}, and {job_title}, but normalize recognized aliases when saving. Publish one backend-owned variable registry for the editor, renderer, API, and AI work requests.

Make every field in the application read schema discoverable: company, role, intermediary, application date, posting and email references, contact name/email/phone, contact method, deadline and deadline kind, location, remote policy, contract, source, description, requirements, lifecycle/outcome, posting information, and follow-up preferences. Put identifiers and technical posting-check fields in an Advanced group. Never expose credentials or execution tokens as template variables.

Provide explicitly named related-data variables for notes, document filenames/references, tasks, and interviews. These resolve to deterministic plain-text summaries, with stable ordering and documented empty behavior. Do not require expressions, loops, arbitrary code, or network requests to render a template. Add useful context tags for follow-up number, due date, previous sent date, and the signature saved in General Settings.

Unknown tags and missing values remain visibly highlighted in the preview. They must be filled, removed, or replaced before marking a message Ready. Do not silently copy an unresolved tag or insert fabricated information. The default greeting should work without a contact name.

### Customization and preservation of edits

General Settings holds the default template, signature, language/tone preferences, global AI instructions, timing, attempt limit, timezone, and reminder preferences. An application can override the relevant preferences and add job-specific instructions. An individual follow-up can add one-off instructions and direct text edits.

Apply the effective configuration in this order: global defaults, application overrides, then follow-up overrides. Display the effective instructions beside the editor. Deterministic settings such as signature and date formatting can be applied without AI. Free-text instructions remain guidance for a human until an agent explicitly processes them; do not claim that the app interpreted them.

Capture the template revision and source-field snapshot when preparing a follow-up. Save message text on the follow-up itself. Global template updates affect new messages by default. Existing messages offer an explicit Apply latest template action with a before/after preview. Application-data changes offer Refresh variables without silently overwriting direct edits. Ready messages return to Prepared whenever their text or effective instructions change. Previously sent history remains available in the audit trail.

### Manual workflow

On application creation or import, prepare one initial follow-up and schedule it in the same database transaction. Use the shared application creation service so human entry and agent imports behave identically. Respect the configured automatic-follow-up limit, including zero, and exclude closed/deleted applications.

Copy actions work on resolved text and never change the workflow state. Mark ready records the approved content revision. Mark sent records the actual timestamp supplied by the user, defaulting to now, and allows correction/undo. The tracker does not infer sending from copying, elapsed time, or readiness.

After a confirmed send, prepare the next follow-up immediately if the automatic limit permits it. The next due date is based on the confirmed send date, not the import date or ready date. Preserve existing phone and combined follow-ups; label their completion appropriately and do not force an email body onto a phone-only record.

### Scheduling and notifications

The initial due date is application date plus the configured calendar-day delay at the user's saved reminder time and timezone. Initial workspace timezone can be Europe/Paris, with a configurable default reminder time of 09:00. Store timestamps in UTC and compute calendar-day dates in the selected timezone so daylight-saving changes do not shift the intended local hour.

Old imports can be overdue immediately. Show them in the queue, but group their first notification into a summary rather than flooding the phone. Closed/deleted applications, archived follow-ups, and paused applications are not actionable. Snooze changes the next reminder time; reschedule changes the follow-up due date. Keep these distinct in data and UI.

At the due time, Prepared means review/edit is needed; Ready means the message is ready for manual sending. Sent produces no reminder. Notifications link directly to the follow-up and never mark it complete. The queue remains authoritative if push is unavailable or delivery fails.

## Current repository foundations

The existing FollowUp model stores sequence, due/sent timestamps, PENDING/DRAFTED/SENT/CANCELLED status, channel, automatic flag, and a template reference. It does not store a subject/body or approval revision. The current reminder scheduler refreshes an in-memory snapshot every 60 seconds. Global timing defaults live in backend configuration, while the existing Settings view combines appearance and agent settings.

Automatic follow-ups already use the original application date and schedule the next automatic reminder after a sent record. Application notes, activity/audit records, pagination, urgency presentation, authenticated agent operations, and MCP are reusable foundations. The human API is primarily protected by local-machine restrictions rather than hosted-user authentication. There is no dedicated Follow-ups route or push-notification infrastructure.

Relevant existing files: backend/app/models.py, work.py, work_schemas.py, applications.py, scheduler.py, main.py, agent_ops.py, agent_schemas.py, mcp_server.py; frontend/src/App.vue, AgentSettings.vue, ApplicationWork.vue, Dashboard.vue, api.ts, Pagination.vue, and presentation/taskPresentation.ts.

## Phase 1 — Shared data model and migration

Deliverable: persistent settings and editable follow-up content, with one set of rules for manual and agent operations.

- Add database-backed general follow-up settings, initialized from current configuration defaults without overwriting saved settings on restart.
- Store the default subject/body, revision, signature, effective customization defaults, timezone, delay, automatic limit, and notification preferences.
- Extend follow-ups with subject/body, template revision/snapshot, source-field snapshot, customization overrides, one-off instructions, content revision, approved revision, preparation/update timestamps, reminder timing, and archive metadata. Store application-level instructions and pause controls separately.
- Implement Prepared/Ready/Sent as the canonical message states. Preserve existing cancellation through archive metadata. Define a safe SQLite migration, including any table rebuild needed for enum/check constraints and foreign keys.
- Map legacy PENDING to Prepared. Map DRAFTED to Prepared while preserving its draft evidence; do not assume a legacy saved draft was approved. Keep SENT and its timestamp. Map CANCELLED to an archived record.
- Recover old draft content only where existing history proves which note belongs to which follow-up. Preserve unrelated or ambiguous EMAIL_DRAFT notes. Do not fabricate historical sent-message text.
- Introduce the variable registry, deterministic renderer, input validation, revision checks, and centralized effective-preferences resolver.
- Provide compatibility handling for existing agent status inputs during transition, with documented legacy mappings.

Acceptance: a pre-upgrade database migrates without losing follow-ups, notes, sent timestamps, or history; startup remains idempotent; unknown variables and stale edits are rejected predictably; legacy sent records do not become actionable.

## Phase 2 — General Settings and highlighted template editor

Depends on Phase 1.

Deliverable: one global template that users can configure visually.

- Restructure Settings into General, Appearance, Agent access, and Notifications sections while retaining current settings.
- Add the subject/body editor, variable highlighting, searchable grouped field picker, signature and customization controls, and live preview against an application.
- Expose all application fields and explicit related-data summaries through the same registry, including useful follow-up context fields.
- Display missing/unknown variables clearly. Make saving a template possible even if a chosen preview application lacks optional fields; distinguish template syntax validity from readiness of one resolved message.
- Show inherited versus overridden values and provide Reset to default controls.
- Save global instructions and customization options in a form that can be consumed by the future AI route as well as the manual editor.
- Template changes increment the revision and do not automatically rewrite existing messages.

Acceptance: a user inserts {company_name} and {position_name}, sees highlighted variables and a correct preview, saves/reloads settings, and gets the same rendering through the backend. Keyboard editing, undo, pasted text, and mobile selection work correctly.

## Phase 3 — Prepare on creation and complete the manual workflow

Depends on Phases 1–2.

Deliverable: the complete core feature without an AI agent or mailbox connection.

- Prepare the initial message inside the shared application creation transaction for human entry and agent imports. Retried imports must not produce duplicate initial messages.
- Backfill missing content on eligible existing pending follow-ups once, retaining due dates, direct edits, and all existing notes. Do not generate a new duplicate reminder merely because content was missing.
- Add an application follow-up editor with subject/body, field insertion, preview, application customization, per-message instructions, and ordinary note entry.
- Provide Copy subject and Copy message with clear success/failure feedback and selectable-text fallback. Copied content is plain text without highlight markup.
- Add Mark ready, Return to prepared, Mark sent with editable time, and Undo. Mark ready must reference the current content revision; later approved AI dispatch requires the current revision to match the approved revision.
- Text or instruction edits to Ready content invalidate approval. Timing-only edits do not rewrite the message.
- On confirmed send, immediately prepare the next eligible message and calculate its due date from the confirmed send date. Respect application pauses and automatic limits.
- Preserve phone/BOTH workflows and ensure closures/deletions stop actionable reminders without destroying message history.
- Extend existing agent create/context/update paths to expose the same message/customization data through the shared service. Agent-generated text does not imply user approval or a send.

Acceptance: importing an application produces exactly one editable message immediately; the complete edit/copy/ready/sent cycle works without an agent; free-text instructions remain visible; sent-time correction and undo restore coherent state and scheduling.

## Phase 4 — Dedicated Follow-ups view and durable reminder schedule

Depends on Phase 3.

Deliverable: one place to manage all follow-ups and their reminder controls.

- Add a Follow-ups navigation route and compact paginated queue. Show company, position, due date, state, and next action; filter by state, due/overdue, paused/archived, and application.
- Reuse urgency colors and pagination. Dashboard follow-up rows link into this view rather than creating a second independent queue.
- Provide snooze, reschedule, per-application pause/resume, and archive controls. Expose global delay/limit settings with per-application overrides in appropriate editors.
- Add persistent scheduled-work records linked to a follow-up and its current scheduling revision. Separate human-reminder work from optional agent execution work.
- Add a database-backed notification outbox. Detect due work with the existing backend scheduler; claim work transactionally and revalidate its current state before delivery.
- Use a unique delivery key to prevent ordinary duplicate reminders after repeated scans, restarts, or concurrent claims. Track pending, attempted, delivered, retryable failure, and superseded work separately from Prepared/Ready/Sent.
- Recover due work after downtime, group overdue imports, respect quiet hours and digest preferences, and cap repeated reminder frequency.

Acceptance: snoozing or sending supersedes an old scheduled notice; restart does not lose due work or replay delivered notices; repeated scans do not flood notifications; the queue and dashboard show consistent counts.

## Phase 5 — Hosted access and phone installation

Depends on Phase 4; must precede production mobile push.

Deliverable: a secure, always-on, single-workspace deployment that a phone can use.

- Choose a hosting provider during implementation based on persistent storage, budget, and operational requirements. This plan does not select or provision a paid service.
- Run the existing FastAPI app, built frontend, scheduler, and SQLite database on one persistent instance initially. Use persistent storage and backups; do not put the SQLite file on ephemeral deployment storage or deploy multiple independent writable instances.
- Add authenticated human access and HTTPS before exposing the application remotely. Keep human sessions distinct from existing agent tokens. Protect API, events, files, settings, and mutation routes consistently; address session expiry and request forgery for the chosen authentication mechanism.
- Maintain local-desktop operation. Hosted access is a supported deployment mode rather than an unconditional weakening of local access protections.
- Add a web-app manifest, icons, and service worker for installation and notification handling. Cache the application shell carefully; do not imply offline database editing is available in this release.
- Support links to one specific follow-up through login, page reload, and installed-app launch. Verify mobile editing, copy actions, layout, and Settings.
- Document startup/restart, health checks, backup/restore, migrations, and the limits of an offline/unavailable backend.

Acceptance: authenticated phone access works over HTTPS; unauthenticated requests cannot read or mutate workspace data; deployment restart preserves settings, drafts, and scheduled work; installation and follow-up deep links work on actual target phones.

## Phase 6 — Mobile push notifications

Depends on Phases 4–5.

Deliverable: actionable reminder notifications independent of any AI runner.

- Add explicit Enable notifications, permission/subscription status, Test notification, per-device subscription removal, quiet hours, and digest controls in Settings.
- Use standards-based Web Push and service-worker notifications. Browser/OS push infrastructure remains necessary, but no BSM service or separate application message broker is required.
- Provide iPhone Home Screen installation guidance and request permission only from an explicit user action. Feature-detect support and explain unavailable/denied permission states.
- Deliver from the persistent outbox. Handle expired subscriptions and retryable network errors without repeatedly sending the same ordinary reminder.
- Link notifications to the exact prepared/ready message. Recheck current state when opened; a notification already delivered cannot always be recalled after a user changes the job.
- Use minimal notification previews by default. Keep in-app due work visible if push fails. Offer optional calendar reminder export as a fallback without requiring mailbox credentials.
- Distinguish push-service acceptance from proof the user saw a notification. Opening/dismissing a notification never marks the message sent.

Acceptance: due notices arrive with the web app closed on supported target phones; tapping opens the correct job; permission denial and invalid subscriptions do not break manual use; quiet hours, downtime catch-up, and duplicate suppression are demonstrated.

## Phase 7 — Shared AI work requests and existing agent routes

Depends on Phase 3; can be developed alongside hosted/mobile phases.

Deliverable: agent assistance that preserves the same customization and approval rules.

- Create one versioned work-request format containing application data, rendered message, variable registry/context, template revision, effective language/tone/signature, global/job/one-off instructions, relevant notes, mailbox reference, operation ID, and allowed action.
- Keep execution instructions separate from the email subject/body. Do not put agent credentials or infrastructure settings in user-facing message content.
- Add Copy AI instructions so a user can bring a prepared request into any agent manually, without installing a runner.
- Extend authenticated agent operations and MCP with get prepared follow-up context, submit revised content, and report draft references/outcomes. Enforce existing permissions and revision conflicts.
- Keep mailbox access external to the tracker. An agent can read/write mail through its own configured tools; the work request does not magically grant that connection.
- Route agent revisions through the same rendering/validation service. Reject stale results after user edits, application closure, or approval changes. Preserve the previous version and identify agent edits in activity history.
- Agent results distinguish revised message, mailbox draft created, skipped, needs clarification, and failure. Mailbox draft creation never records a send. Human Ready approval remains a separate explicit action.

Acceptance: manual copy/paste into Codex or Claude includes all customization options; existing agent routes use the same application creation behavior; an agent result cannot overwrite a newer human revision; the manual workflow remains fully functional with AI disabled.

## Phase 8 — Optional unattended runner with long polling

Depends on Phases 4 and 7. This is a later opt-in capability, not a requirement for the initial manual/mobile release.

Deliverable: scheduled execution by an available Codex or Claude worker without BSM.

- Add an authenticated long-poll endpoint backed by the same persistent scheduled-work queue. The server returns actionable jobs, not an ephemeral wake event that disappears on disconnect.
- Register runner identity and capabilities independently from authentication tokens. Require the selected worker to have the configured mailbox capability before dispatching mailbox work.
- Have a small runner claim work and launch a bounded Codex noninteractive job or Claude Code/Agent SDK job with the complete request. The launcher records structured results so an agent does not need broad tracker access or repository context.
- Add leases, time limits, completion acknowledgement, retry/backoff, cancellation, and worker-health visibility. Poll connections reconnect after network interruption; outstanding jobs remain in the database.
- Revalidate message revision, approval, application status, and job schedule before execution and before accepting a result. Only explicitly authorized work may create a mailbox draft; no automatic sending.
- Keep stable operation IDs and mailbox draft references. If a worker crashes after an external write, reconcile the uncertain outcome before retrying. A database lease cannot guarantee exactly-once external mailbox writes; do not start competing retries while the prior write may still be active.
- Preserve Prepared/Ready/Sent as message states; worker waiting/running/failure belongs to execution history. When no runner is configured, continue human reminders rather than leaving manual jobs indefinitely waiting for an agent.

Acceptance: duplicate wakes do not start ordinary duplicate work; interrupted long polls recover; offline runners catch up; a crash after mailbox draft creation triggers reconciliation; switching Codex/Claude retains the same instructions and approval behavior.

## Delivery and verification

The first independently useful release includes Phases 1–4. The requested hosted-phone release adds Phases 5–6. Shared AI request support can follow or run alongside that work; unattended execution is a separate later increment.

Each phase should update API documentation and user guidance, include meaningful regression tests, and complete visible/manual verification before delivery. Backend checks should cover migration preservation, deterministic variable rendering, creation/import idempotency, revision conflicts, workflow transitions, sent-time/undo behavior, limits, pauses, reminder recovery, authentication, and queue concurrency. Frontend checks should cover token editing, unresolved fields, inherited settings, copy behavior, state invalidation, queue controls, and deep links. Run the frontend type check/build and relevant backend/frontend suites; include the tests in delivered changes.

Real-phone verification is required for the notification phase. Browser simulation alone does not establish iPhone installation, permission, background delivery, or clipboard behavior. Verify both manual use and an AI-disabled configuration throughout implementation.

Before production deployment, identify the selected hosting service and make the actual deployment configuration reviewable.

## Documentation references

- Web Push and background delivery: https://developer.mozilla.org/en-US/docs/Web/API/Push_API
- Mobile notification handling: https://developer.mozilla.org/en-US/docs/Web/API/Notifications_API/Using_the_Notifications_API
- iPhone/iPad Home Screen push requirements: https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/
- Codex noninteractive execution: https://learn.chatgpt.com/docs/non-interactive-mode
- Claude Code programmatic execution: https://code.claude.com/docs/en/headless

These references describe platform capabilities; deployment and account-specific availability must be checked when implementing the relevant phase.
