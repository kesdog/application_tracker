# Mail scanning and application updates

**Settings → Connections → Mail scan & updates → Earliest application date**
defaults to **2026-01-01** and cannot be set earlier. This absolute boundary also
applies to legacy Gmail accounts which already have a checkpoint. A recent
delivery containing an older application date is ignored during reconciliation;
it cannot create a pre-boundary application or update a matching older record.
The message receipt is saved as ignored, preventing repeated work.

The first Gmail sync for an account prompts **How many months back should we
check?**, defaulting to **3** and allowing whole numbers from **1–120**. Cancel
starts no job. The backend subtracts calendar months in the workspace timezone,
clamping the day at month end and respecting the absolute date boundary, then saves that exact lower timestamp in
`MailSyncScope`. The saved date survives caps, failures, restarts and later runs;
it does not slide forward while the initial backlog is processed. An account
with an existing completed checkpoint continues from that checkpoint without
resetting its history. The new scope table is migration `0028_mail_sync_scope`.

The start timestamp serves a different purpose: it fixes the **upper** boundary
of a Gmail scan. New mail arriving during that scan waits for a later run, and
only a completed scan can save that timestamp as its checkpoint. It is not just
a log timestamp. The user's month choice fixes the **lower** boundary.

Set **Settings → Connections → Mail scan & updates → Maximum new emails per sync**.
The default is **100** and the allowed range is **1–1,000**. The value is saved in
the existing local general settings and is captured when a job starts. Changing
it during a run affects the next run. No database migration is required for this
setting.

The allowance counts application-related email bodies not yet processed by the tracker, including
messages that need review. Messages with an existing per-account import receipt
do not consume it again. An email can add or update at most one application, so
this also bounds the number of applications Gmail can change during that run.
It is not a limit on all Gmail search results, Google API requests, or changes
downloaded through encrypted device sync. Read retries may make additional API
requests for the same email.

If another unread message exists after the allowance is used, the job reports
`gmail=LIMIT_REACHED`, `limit_reached=true`, and an overall `PARTIAL` result. The
button becomes **Continue sync**. Already committed work stays saved; the
completed-mail checkpoint does not advance. A later run skips receipts and reads
the remaining messages, including after an app restart. If the final unread
message uses the allowance exactly and no unread messages remain, Gmail completes
normally and advances its checkpoint.

## Function-by-function flow

1. **`ApplicationSyncControl.sync()`**
   Refreshes status before starting. If `initial_scan_required` is true, opens
   the month-choice dialog, associated with the currently connected account.
   Confirming rechecks the account and submits the chosen months; changing
   accounts requires a fresh choice. Disables repeated presses, calls
   `startApplicationSync()`, and uses `load()` /
   `accept()` to poll progress. On completion it emits `changed` so the application
   list refreshes. `limit_reached` changes the button to Continue sync.

2. **`startApplicationSync()` → `start_application_sync()`**
   The frontend posts to `/api/applications/sync`. The backend's
   `application_sync_service()` dependency requires the human workspace access
   boundary; this endpoint does not accept an agent bearer token. The optional
   JSON body is `{ "lookback_months": 3 }`. Strict whole-number validation happens
   before starting. A legacy caller without a body receives the bounded
   three-month default; later month values do not replace a saved scope.

3. **`ApplicationSync.start()`**
   Returns the existing job if one is running. Otherwise it reads
   `current_settings()['mail_sync_max_messages']`, snapshots that limit and the
   connected account, and saves a first-run scope if neither scope nor completed
   boundary exists. That write uses the same immediate transaction as the
   settings read. It then resets
   counters, assigns a job ID and schedules `run()` in a single-worker executor.

4. **`ApplicationSync.run()` → `_pull_drive()` → `run_drive()` — preflight**
   If encrypted Drive sync is initialized and does not need recovery, it runs
   before Gmail so records from another device are available for matching. A busy
   Drive worker is polled for up to 120 seconds. A failure is reported and does
   not discard local records or prevent attempting Gmail.

5. **`ApplicationSync._import_gmail()` → `gmail()` → `GmailScan.run()`**
   Requires a connected account with `gmail_read`, hashes its email to select the
   account-specific receipt/checkpoint namespace, and fixes the scan window at
   the scan's start time. After a previously completed scan, it searches from five
   minutes before the saved checkpoint to tolerate indexing delays, without
   crossing the saved initial lower bound. A first run searches from the saved
   month-choice date. Changing accounts during Drive preflight stops this job
   before it reads the new account's mail.

6. **`GmailScan.read()` → `check_account()` → `GoogleConnection.api()`**
   Rechecks the selected account and Gmail permission around reads. Temporary
   rate limits get at most four attempts, honoring a short Retry-After or waiting
   5, 10 and 20 seconds. A delay above 60 seconds is reported for a later retry.
   Authorization and credential handling stay inside the existing Google boundary.

7. **`GoogleMailProvider.application_messages()`**
   Lists up to 500 message IDs per page using the application's fixed recruitment
   query, excluding spam, trash and drafts. Search vocabulary comes from the
   supported message-language packs. The query includes candidature,
   application, postulé, CV forwarding, interview and entretien terms. The result
   can contain irrelevant emails; it is a candidate search, not an exhaustive
   semantic scan of every mailbox message. Pagination uses the same date window.

8. **Receipt check and allowance in `GmailScan.scan_pages()`**
   For each candidate, look up `(account, message_id)` in `MailImportReceipt`.
   Skip known IDs, including already-read review messages. Before a new body read,
   enforce the saved allowance. Repeated pagination tokens are rejected. This
   avoids repeating saved writes or silently jumping over capped work.

9. **`GmailScan.process()` → `GoogleMailProvider.application_message()`**
   Downloads a bounded MIME body and headers. Attachments are not downloaded.
   After another account check it calls `read_evidence()` once, passes the named
   `MailEvidence` object to `reconcile_evidence()`, collects distinct created
   and updated application IDs, and increments the new-email counter. An
   application created and updated in the same job is counted only as created.

10. **`read_evidence()` → `scan_email()`**
    Parses HTML locally, removes quoted-history elements from current evidence,
    dispatches to a provider scanner, extracts a role/employer and direct posting
    URL when supported, and reads the
    original message date. Missing dates or ambiguous details go to review rather
    than being invented. There is no model/API inference call in this path.

11. **`match_application()`**
    Tries an exact saved email reference, prior receipts in the Gmail thread,
    canonical posting URL, normalized company/title, and finally company/title
    text in the message. Multiple matches require review. Deleted records remain
    deleted. A thread candidate must agree with any extracted role and employer,
    preventing different confirmed vacancies in one thread from being merged.
    New application IDs derive from account/message rather than account/thread,
    so those distinct confirmations cannot collide.

12. **`reconcile_evidence()` → `_update_matched_application()`**
    Recognizes supported explicit rejection/interview wording. A supported
    confirmation can create an application through `create_application()`;
    `update_application()` adds missing references/posting details and safe status
    changes. Closed decisions, older conflicting updates and ambiguous matches
    stay for review. The application, receipt and source timeline event commit in
    one message transaction. The source event records scanner and message
    language for traceability. `_reference_changes()` handles missing references
    and posting details; `_lifecycle_changes()` keeps status protections together;
    `_record_source()` avoids duplicate source events. No emails are sent or drafted.

13. **`GmailScan.rematch_pending()`**
    Reconsiders actionable unmatched messages read during this same job after
    older confirmations create matching records. It reuses parsed `MailEvidence`,
    without another parse, Gmail read or allowance charge. Messages left for
    review in a previous capped job are not automatically reread; they remain
    visible under **Settings → Data & recovery**. `mail_reviews.decide()` handles
    explicit ignore/link/create decisions there. An update split from its
    confirmation by the cap can therefore require manual review.

14. **`GmailScan.save_checkpoint()`, final Drive pass and status**
    Only an exhausted Gmail scan advances `MailSyncBoundary.checked_through` to
    the fixed scan-start time. A capped or failed scan keeps the previous value.
    `ApplicationSync._push_drive()` then attempts Drive again to publish/merge
    saved tracker changes, even when Gmail failed after some committed messages.
    `SyncEngine.run()` receives encrypted batches, applies safe local merges,
    prepares queued changes and uploads pending batches. Conflicts are retained
    for review. Overall completion requires both Gmail and Drive to complete;
    missing optional setup, a cap or an error produces a partial result.

## Maintaining the update flow

Follow the dependencies in this order when changing behavior:

| Module | Responsibility |
| --- | --- |
| `application_sync.py` | Start/join a job, snapshot settings, report progress, coordinate Drive → Gmail → Drive. |
| `mailbox_scan.py` | Read-only retries, fixed scan window, pagination, allowance, receipts and checkpoint completion. |
| `mailbox_evidence.py` | Parse once into named evidence; keep current text separate from quoted history and retain date provenance. |
| `mail_scanners/` | Provider and language recognition, with no database or network access. |
| `mailbox_matching.py` | Match strongest identity first; preserve ambiguity and deleted records. |
| `mailbox_import.py` | Apply one message through the existing application services and commit its receipt/history atomically. |

`ImportResult` names the application ID and created/changed flags while retaining
tuple compatibility for existing callers of `reconcile()`. That raw-message
entry point delegates to the same `reconcile_evidence()` transaction used by the
scan worker. Scanners never write records, and reconciliation never fetches mail.
Inline comments explain the safeguards at the points where they are enforced.

## Reading progress

`ApplicationSync.status()` combines the in-memory job counters with the persisted
scope, checkpoint and per-account review receipts. `initial_scan_required`,
`gmail_account`, `gmail_scan_from` and `lookback_months` drive the first-run UI.
It returns the total review count and
the 20 newest review links. The frontend polls while running and stops when the
job finishes. The job's capped flag is in memory; after restarting, pressing
Sync applications still continues safely because receipts and the completed-mail
checkpoint are persistent.

The Gmail path does not read attachments, open job pages, send replies, create
Gmail drafts or change labels/read state. A missing job URL can be filled from an
email; independent posting checks are outside this mailbox allowance. Local
tracking remains usable without Gmail or Drive.

## Provider scanners and message languages

`backend/app/mail_scanners/` contains a storage-independent scanner registry:

- **`LinkedInScanner`** reads the application card and specific job anchor,
  avoiding a repeated preview heading or unrelated suggested jobs.
- **`IndeedScanner`** reads the submitted-application card and named recipient.
- **`FreeWorkScanner`** requires explicit submitted-application wording. A unique
  specific Free-Work vacancy link can supply its posting URL; multiple candidate
  links are not guessed.
- **`GenericScanner`** handles explicit role/employer confirmations for other
  senders and provides the fallback when a known provider's template is unknown.
  It retains the existing ISCOD forwarding rule. Sender branding alone never
  supplies an employer.

`MailContent` cleans current evidence and retains headers and anchors. Each
scanner returns a shared `ScanResult`: extracted `ConfirmationDetails`, explicit
lifecycle decision, scanner name and detected message language.
`extract_confirmation_details()` remains the compatibility interface used by
agent tools, delegating to this same registry.

`languages.py` contains **English and French** packs shared by every scanner.
Provider templates, lifecycle wording, month names and Gmail search vocabulary
are message-language data, independent of the future UI locale. A French email
is parsed in an English interface. Normalization handles accents and punctuation
while retaining other scripts for future packs. Date parsing does not depend on
the machine's locale.

To add a language, register its patterns/month names/search terms and add fixtures
for each provider, generic confirmation and lifecycle outcome. To add a provider,
subclass `MailScanner`, declare its name/source, implement `matches()` and
`scan()`, then register it in `SCANNERS`. Keep extraction separate from database
reconciliation and Google authorization. Unknown templates and contradictory
current-body decisions remain for human review. Fixture coverage supports the
tested formats; it does not imply every historical provider template is parsed.
Message recognition stays independent of UI translations. Mail-boundary and
recipient-queue controls include English and French labels.

## Recipient research queue

Once a local email follow-up has its subject and body prepared, its application
is queued for recipient research in the same transaction. Known recipients,
phone messages, closed/deleted applications and imported device messages do not
trigger automatic public-web searches. Existing searches/results are reused;
explicit retry remains available. No recipient is selected and no email is sent
automatically.

Follow-up messages and default recipient work are ordered by newest application
date first. The recipient worker pool remains limited to five active leases.
The Recipients view exposes the next 20 queued/running/paused jobs and:

- **Pause all searches / Resume searches** persist the global queue state.
- **Pause search** interrupts one application while leaving the others available.
- **Run next** gives an application manual priority and, when all slots are busy,
  interrupts one lower-priority run to free a slot.

Pause and preemption revoke the old lease before cancellation. Workers monitor
their leases, interrupt research without terminating the worker, and reject late
results. Already saved page reports are kept for reuse. A globally paused queue
stays paused across restarts and priority changes until explicitly resumed.
