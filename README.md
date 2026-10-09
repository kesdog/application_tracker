# Application Tracker

Version **0.11.0** simplifies posting discovery to **Search manually** and **Agent search**, with a portable search prompt and clickable email references throughout application details, interviews and email timeline entries.

The frontend uses PrimeVue 5 with Aura and a shared appearance layer. **Settings → Appearance** previews and saves colors locally, warns about low text contrast, and offers Default, Dark, High Contrast, Soft and Minimal presets. Presets remain editable. **Table preferences** controls optional columns, density and page size; Date, Company, Position and Status remain visible. Table sorting and pagination apply to the loaded results; filtering and full filtered exports remain backend-owned. Next actions use the existing dashboard window. Server-side pagination is deferred until data volume requires it.

The header includes a **Collapse/Expand sidebar** control and a **Dark theme** switch. Light **Paper** uses warm surfaces with forest-green navigation; dark **Midnight** uses navy surfaces with lavender and cyan accents. Each theme retains its own customized palette across switches and reloads. Sidebar collapse is saved in the browser, with accessible icon links on desktop and folding navigation on narrow screens. See [design.md](design.md) for the current design, palette roles, accessibility targets, and wizard behavior.

Set `VITE_PRIMEUI_LICENSE_KEY` in the root `.env.local` to a valid PrimeUI Community/Commercial key, then restart Vite (or rebuild production assets). Vite exposes this browser license value in the client bundle; do not use a server secret. No license key is included in the repository.

The official `@primevue/mcp` server is installed as a development dependency. From `frontend`, use `pnpm primevue:docs list` to discover its tools, `pnpm primevue:docs get_setup` for setup guidance, and `pnpm primevue:validate` to check component usage over MCP stdio. Validation normalizes Vue's kebab-case props to API names. The server has no standalone Column metadata, and its Button metadata omits anchor attributes shown in its own Link example; those cases are covered by source examples and TypeScript. MCP validation supplements `pnpm build` and `pnpm test`.

The sidebar uses icons for **Dashboard**, **Applications**, **Interviews**, **Tasks**, **Export**, and **Settings**. **Add application** guides you through four screens: Role, Posting, Contact & extras, and Review. Back preserves your entries; only **Save application** on Review creates a record. Job title, company, application date, and either a posting URL or email reference are required. Recruiter details, notes, and follow-up overrides appear behind checkboxes or expandable sections. Remote policy uses a three-way Full remote / Hybrid / In person control and can be cleared.

An application address book derives autocomplete suggestions from saved applications, including locations, companies, roles, contact details, and posting references. Dates, numbers, and longer notes offer previous-value selectors; new values remain allowed. Saved contacts can be reused explicitly. These suggestions stay in your existing tracker database and do not use an external address service. The source defaults to a recognized board from the posting URL—Indeed, LinkedIn, Free-Work, or HelloWork—or Other, and can be changed manually.

Contact details are optional. When adding a contact, choose Email or Phone as the preferred method and optionally include the other method. **Contact email** is validated separately from the **Application email reference**, which may be a message URL, ID, or subject. French national phone numbers and international numbers with a `+` prefix are validated and stored in E.164 format. The backend also validates contacts in human API, agent REST, and MCP requests. An optional deadline records either the application closing date or first-round selection date; it appears in application details and CSV/XLSX exports alongside contact details. Saved records appear newest first, start as `SUBMITTED` with no outcome, and remain accessible in the horizontally scrollable table on narrow windows. **System status** is visible only in Settings.

Click a position in the table to open its focus view. **Edit application** lets you update its title, company, date, contact type, phone number, posting URL or email reference, location, remote policy, contract type, source, description, requirements, status, outcome, and posting state. **Cancel** discards the current draft. Focus URLs use a hash and can be bookmarked or refreshed without a router dependency. Return with **All applications** to see updated status/outcome badges.

Selecting an outcome closes the application. To reopen an application that already has an outcome, select an active status and explicitly check **Clear the existing outcome**. Posting state is independent of the application lifecycle; marking a posting closed does not close the application. Posting checks are recorded manually.

The focus view contains **Documents**, **Interviews**, **Notes**, **Tasks**, and **Follow-ups**. Attach a CV or cover letter by uploading a file into the tracker data directory, or record an external/local reference with its filename. Uploaded files can be downloaded from the focus view. Schedule, edit, and delete interviews with preparation notes, meeting details, and results. Add/edit a typed note, add a task with an optional due date, complete/cancel/reopen tasks, and record email, phone, or combined follow-ups as drafted, completed, or cancelled. Phone and combined options require an application phone number. Email drafting saves a local `EMAIL_DRAFT` note when no mail account is connected; it never sends a message. Interviews have an explicit calendar file download for manual import.

The **Timeline** records application, note, task, follow-up, interview, outcome, and posting-state activity with the actor and time. Add an editable email entry when the exact sent or received time matters; system history remains immutable. Reversible edits expose **Undo last change**. Undo restores the complete prior field snapshot, including coupled values such as a task status and completion timestamp. Application deletion requires a second human confirmation and sets `deleted_at`; deleted applications and their work disappear from normal lists without removing database records.

Use the sidebar to open **Interviews** or **Tasks**. Interviews are ordered by scheduled date and show their application, meeting context, and near-term wording such as “Technical interview — tomorrow at 14:00.” Tasks are ordered by due date, show their parent application, and can be completed, cancelled, or reopened from the global view.

Use **Dashboard** to see active application count, separate due-soon and overdue follow-up lists, due and overdue tasks, upcoming interviews, linked work for the next seven days, and recent activity. The Applications page supports free-text search plus status, outcome, company, position, location, contract, source, remote policy, document filename, and application-date filters. Filters are collapsed by default, combine when shown, can be cleared together, and retain the existing newest-first order. The **Export** screen above Settings downloads all applications or a filtered view as CSV or formatted XLSX. Applied list filters carry over to Export and can be adjusted there. Contract filters group existing French and English descriptions into Full time (CDI), Fixed term (CDD), Part time (Temps partiel), and Apprenticeship / Internship (Alternance / Stage). Rows with overdue pending or drafted follow-ups use a subtle urgency border and tint from the dashboard queue, with an explicit next-action label; closed applications use the closed-posting tone. Source cells use posting and email ref links instead of raw URLs.

Use **Settings** to generate an agent token and choose its read, create, edit, draft, task, and interview permissions. The plaintext token is shown only when generated or regenerated. Agent changes appear in the open Applications, Dashboard, Tasks, Interviews, and application focus views through a small server-sent event that tells the UI what to refetch.

Creation checks normalized company/title and job URLs against existing applications. A likely duplicate is still saved, then shown as an advisory warning with links and reasons so the user can compare records without blocking legitimate repeat applications.

Follow-ups are tracking records. Creating or marking one complete never places a call or sends email. The background scheduler refreshes due/overdue work every minute without changing applications or contacting anyone.

## Requirements and installation

Use Python 3.11+ (tested with 3.12), Node.js 22.12+ (tested with 24), and pnpm 11.19.0. Run these PowerShell commands from the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e '.[dev]'
.\.venv\Scripts\python.exe -m playwright install chromium
pnpm --dir frontend install --frozen-lockfile
Copy-Item .env.example .env
```

Skip the last command if you already have a `.env`; defaults work without it. Python dependencies are isolated in `.venv`, frontend dependencies in `frontend/node_modules`. The lockfiles record the tested dependency versions. TypeScript is pinned to 5.9 because the installed Vue type checker is incompatible with TypeScript 7.

Dependencies are already installed in this workspace. On this machine, Python and pnpm came from the bundled Codex runtime. If they are absent from a new terminal's PATH, the executable paths used for setup were:

```powershell
& 'C:\Users\----\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m venv .venv
& 'C:\Users\----\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd' --dir frontend install --frozen-lockfile
```

## Run locally

In a terminal at the project root, start the backend:

```powershell
.\.venv\Scripts\python.exe -m app.main
```

In a second terminal at the project root, start the frontend:

```powershell
pnpm --dir frontend dev
```

Open <http://127.0.0.1:5173>. The API is at <http://127.0.0.1:8000/api/health> and interactive API documentation at <http://127.0.0.1:8000/docs>. Stop either server with Ctrl+C in its terminal.

Vite proxies `/api` to the configured backend. Restart both servers after changing host/port settings. The frontend remains bound to localhost. No CORS configuration is needed for this development setup.

For a single production process, build the frontend with `pnpm --dir frontend build`, then run `application-tracker` (or `python -m app.main`). The backend serves the compiled UI at <http://127.0.0.1:8000/> and the API under `/api`.

## Settings and storage

The backend reads the root `.env` file; process environment variables take precedence.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_HOST` | `127.0.0.1` | Backend bind address |
| `APP_PORT` | `8000` | Backend port, 1–65535 |
| `APP_ENV` | `development` | Environment label available to the app |
| `APP_MODE` | `local` | Local loopback access, or `hosted` with a required public origin and workspace password |
| `APP_ALLOW_REMOTE_HUMAN` | `false` | Legacy unauthenticated bypass is rejected; use hosted mode for remote human access |
| `APP_PUBLIC_URL` | unset | Hosted origin, e.g. `https://tracker.example.com`; HTTPS required except loopback development |
| `APP_PASSWORD_HASH_FILE` | unset | Hosted secret file generated by `python -m app.human_auth --output PATH` |
| `APP_PASSWORD_HASH` | unset | Alternative secret hash; configure exactly one hash source |
| `APP_SESSION_HOURS` | `8` | Hosted browser session lifetime, 1–168 hours |
| `APP_TRUSTED_PROXY_IPS` | `127.0.0.1` | Proxy addresses/ranges allowed to supply forwarded scheme/client information |
| `APP_DATA_DIR` | `./data` | Directory created during backend startup |
| `APP_STATIC_DIR` | `./frontend/dist` | Compiled Vue frontend served by the backend when present |
| `LOG_LEVEL` | `info` | Uvicorn logging level; case insensitive |
| `FOLLOWUP_DELAY_DAYS` | `7` | Default delay from creation for a follow-up without a supplied due date (0–3650) |
| `MAX_FOLLOWUP_SUGGESTIONS` | `2` | Stored limit for future automatic suggestions (0–100); never restricts manual creation |

Under **Edit application → Follow-up preferences**, set a delay or suggestion limit for one application. Blank values inherit the global settings; zero is a valid override. Changing preferences affects new follow-ups, not existing due dates. Restart the backend after changing global settings in `.env`.

Relative data paths resolve against the project root, regardless of the terminal's current directory. The database is `data/tracker.sqlite3` by default. SQLite WAL is enabled and verified at startup; connections also enable foreign keys. The engine is disposed on normal server shutdown. Startup fails clearly if storage cannot initialize.

`GET /api/health` checks the live database connection and returns:

```json
{"status":"ok","version":"0.11.0","database":"connected"}
```

It returns HTTP 503 if the database query fails. The Settings page checks on load and when **Check again** is clicked, with a five-second timeout. It clears stale version/database values on a failed check. Continuous polling is not part of this release.

## Applications API and migrations

- `POST /api/applications` creates an application and returns HTTP 201 with the saved record.
- `GET /api/applications` returns saved records ordered by applied date descending, then ID. Optional query filters are `q`, `status`, `outcome`, `company`, `title`, `location`, `contract_type`, `source`, `remote_policy`, `date_from`, `date_to`, and `document_filename`.
- `GET /api/applications/{id}` returns a full application or HTTP 404.
- `PATCH /api/applications/{id}` updates only supplied fields and returns the saved application. Omitted fields stay unchanged; explicit null clears an optional field. Required fields cannot be null. Missing records return HTTP 404.
- `DELETE /api/applications/{id}` performs a human-only soft deletion and returns HTTP 204. Deleted records return HTTP 404 and are excluded from normal application and global work lists.
- Invalid data returns HTTP 422. Titles and companies must contain non-whitespace text; job URLs must use HTTP or HTTPS. At least one non-empty job URL or email reference is required. The optional `phone_number` accepts a French national number or a `+` country code and is normalized to E.164. Status and outcome cannot be supplied on creation.

Lifecycle rules are enforced in the backend service and supported by a database constraint:

- Active applications have no outcome. Setting a non-null outcome without a status automatically sets `CLOSED`.
- Explicitly combining an active status with an outcome returns HTTP 422 without changing the record.
- Closing without an outcome is allowed.
- Reopening a closed application with an existing outcome requires an explicit `"outcome": null` in the same request. No outcome is silently discarded.

For example, PATCH `{"status":"INTERVIEW"}` starts interviewing; `{"outcome":"UNSUCCESSFUL"}` closes the application; `{"status":"INTERVIEW","outcome":null}` reopens it.

`posting_status` is `UNKNOWN` (default), `LIVE`, or `CLOSED`. `posting_last_checked_at` is nullable and accepts an ISO 8601 timestamp with a timezone, for example `2026-09-18T14:30:00+02:00`. It is stored and returned in UTC; the UI edits/displays local time. Neither field performs an external posting check.

Example POST body:

```json
{
  "job_title": "Software Engineer",
  "company": "Example Company",
  "date_applied": "2026-09-18",
  "job_url": "https://example.com/jobs/engineer"
}
```

Alembic applies pending migrations automatically at backend startup, including upgrades from existing 0.1.0–0.10.1 databases. Migration `0008_phone_and_followup_channels` adds optional application phone numbers and defaults existing follow-ups to `EMAIL`; migration `0009_application_contact_type` defaults existing applications to `EMAIL` contact. Child tables enforce application foreign keys and valid statuses; follow-up numbers are unique within each application. Startup stops if migration fails. Tests use temporary databases. To inspect or explicitly apply migrations from the project root:

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
```

Migration commands use the same `.env` settings and database as the application. Run one backend process against the local database during schema upgrades.

## Prepared follow-ups

Settings now includes **General · Follow-ups**: one default subject/message template, highlighted variable insertion, live preview, signature, language/tone guidance, instructions, calendar-day delay, automatic limit, timezone and quiet hours. Use `{company_name}` and `{position_name}`; the field picker exposes all application fields and related notes, documents, tasks and interviews. Friendly aliases such as `{company name}` are normalized. Unknown tags are rejected when saving a default template. Missing optional data stays highlighted in an individual message until filled or removed.

Every eligible application created by the UI or an agent immediately gets a prepared message in the same transaction. Its first due date uses the original application date plus the saved delay at the saved local reminder time, including daylight-saving changes. The **Follow-ups** view is the canonical queue; dashboard and application rows link directly to its editor. Copy subject/message into your own mail client, **Mark ready** after review, send there, then **Record already sent** with the actual time. Copying and Ready never record a send. Phone-only follow-ups record completed calls instead.

Message edits invalidate Ready approval. Revision checks reject conflicting saves without overwriting newer text. Saved messages retain their original text when settings or application data changes: preview refreshed variables or the latest template and explicitly apply the replacement. Language and tone are editing/AI preferences, not automatic translation. Per-job preferences and per-message instructions travel with **Copy AI instructions** and the authenticated agent tools. Notes can record replies without a mailbox connection.

Snooze delays a reminder, reschedule changes the due date, pause affects the application's reminders, and archive retains message history. A confirmed automatic send prepares the next message up to the configured limit. Correcting its timestamp updates an untouched successor; undo removes an untouched successor. An edited successor must be archived before reopening the earlier send so its content is preserved.

The scheduler persists in-app notices with a unique follow-up/due-time key. Quiet hours defer their availability; restarting or scanning again does not duplicate them. Due notices appear together in Follow-ups and can be dismissed without changing message state. This increment does **not** deliver phone push notifications. Hosted authentication, phone installation and HTTPS configuration are implemented; [the deployment guide](deploy/README.md) covers server setup and verification. Push subscriptions/delivery retries and the optional long-poll runner remain in [FOLLOWUP_PLAN.md](FOLLOWUP_PLAN.md); `daily_digest` is a reserved delivery preference.

Migration `0016_prepared_followups` maps legacy PENDING/DRAFTED to PREPARED, preserves SENT and its timestamp, and archives CANCELLED records. Startup prepares missing unsent content once and recovers old draft notes only when activity explicitly links them to that follow-up. Historical sent-message text is not fabricated. Back up the SQLite database before upgrading; schema downgrade discards the new message/settings fields.

| Endpoint | Behavior |
| --- | --- |
| `GET/PUT /api/settings/general` | Read/save defaults; PUT accepts `expected_revision` |
| `GET /api/followups/variables` | Canonical template variable registry and aliases |
| `POST /api/followups/preview` | Render subject/body, report missing and unknown fields |
| `GET /api/followups` | Server pagination, status/due/search/paused/archive filters |
| `GET /api/followups/notices` | Available unread in-app notices |
| `POST /api/followups/notices/{id}/read` | Dismiss one notice |
| `GET /api/applications/{app}/followups/{id}/proposal?latest=true` | Preview replacing saved text; false uses its saved template |
| `POST /api/applications/{app}/followups/{id}/apply-template` | Explicit replacement with `expected_revision` and `latest` |
| `GET /api/applications/{app}/followups/{id}/ai-request` | Provider-neutral versioned request for manual copying |

Agent REST/MCP adds `get_followup_request` (read permission) and `revise_followup` (draft permission). The latter requires `expected_revision`, accepts only subject/body/instructions/customization, rejects closed/archived jobs, and cannot approve Ready or send. Existing mailbox tools remain external to the tracker. The legacy mark-followup-sent operation still records an externally completed send when its existing permission allows it; it never sends mail.

## Notes, tasks, and follow-ups API

All work endpoints are scoped to `/api/applications/{application_id}`:

| Method and suffix | Behavior |
| --- | --- |
| `GET /work` | Notes, tasks, follow-ups, and effective follow-up settings |
| `POST /notes` | Create with `content` and optional `type` |
| `PATCH /notes/{id}` | Edit content/type while preserving author and creation time |
| `POST /tasks` | Create with `title`, optional `description` and `due_at` |
| `PATCH /tasks/{id}` | Edit title/description/due date/status |
| `POST /followups` | Create with optional `due_at` and `template_reference` |
| `PATCH /followups/{id}` | Edit message/instructions/customization, reminder controls or PREPARED/READY/SENT; send `expected_revision` |

Creation returns HTTP 201; updates return HTTP 200. Missing parents or child IDs belonging to another application return HTTP 404. Invalid input returns HTTP 422. Child ownership, IDs, sequence numbers, authorship and task completion timestamps cannot be overwritten through request bodies. Follow-ups accept an explicit actual `sent_at` when their status is SENT.

Note types are `GENERAL`, `ASSESSMENT`, `EMAIL_DRAFT`, `INTERVIEW`, and `AGENT`. The human REST routes record `created_by=HUMAN`; note type is a category, not an identity. Notes have UTC `created_at` and `updated_at` timestamps.

Task statuses are `PENDING`, `COMPLETED`, and `CANCELLED`. Completing a task sets `completed_at` once; repeating the same status preserves that timestamp. Returning to pending or cancelled clears it. Tasks with due dates appear first, ordered earliest first.

Follow-up statuses are `PREPARED`, `READY` and `SENT`. Legacy inputs PENDING/DRAFTED map to PREPARED; CANCELLED archives the message. Marking sent sets `sent_at` once unless an actual send time is supplied. Reopening clears it and preserves the change in audit history. Follow-up creation takes a SQLite write lock before allocating the next sequence number, so simultaneous requests receive distinct numbers. For additional manual follow-ups the default due date is creation time plus the effective delay; an explicit date overrides it. Manual creation remains available even when the automatic limit is zero or exceeded.

All input datetimes require an explicit timezone. SQLite stores UTC, API responses include `Z`, and forms/display use local time. To mark a task complete or a follow-up sent, PATCH `{"status":"COMPLETED"}` or `{"status":"SENT"}` to its corresponding endpoint. These operations do not change the parent application's lifecycle.

## Interviews and global work API

Interviews belong to an application and require a type plus a timezone-aware scheduled date. Types are `PHONE`, `HR`, `TECHNICAL`, `ONSITE`, `FINAL`, and `OTHER`. Duration is optional and stored in minutes. Location, meeting URL, interviewer, email reference, preparation notes, and result are optional.

| Method and path | Behavior |
| --- | --- |
| `GET /api/applications/{application_id}/interviews` | List one application's interviews in date order |
| `POST /api/applications/{application_id}/interviews` | Schedule an interview |
| `PATCH /api/applications/{application_id}/interviews/{id}` | Edit supplied interview fields |
| `DELETE /api/applications/{application_id}/interviews/{id}` | Delete an interview through the human UI/API |
| `GET /api/interviews` | List all interviews in date order with application summaries |
| `GET /api/interviews/{id}` | Read one interview |
| `GET /api/interviews/{id}/context` | Read the interview, full parent application, related notes/tasks, and available document metadata |
| `GET /api/tasks` | List all application-linked tasks in due-date order with application summaries |

Interview context includes the application's document metadata. Global tasks with no due date sort after dated tasks. Interview and task writes remain in the existing application-scoped routes so parent ownership is always checked.

## Timeline, audit, undo, and deletion API

`GET /api/applications/{id}/timeline` returns newest-first events and `undo_available`. `POST /api/applications/{id}/timeline` adds a manual email entry with a timezone-aware `occurred_at`; `PATCH /api/applications/{id}/timeline/{event_id}` edits a manual entry. Events contain `event_type`, `summary`, `actor_type`, optional `actor_reference`, metadata, and a UTC timestamp. Actor types are `HUMAN`, `AGENT`, and `SYSTEM`; human REST mutations currently record `HUMAN`, while the shared services preserve agent/system identities supplied by future integrations.

`POST /api/applications/{id}/undo` restores the latest reversible mutation and returns the affected entity and fields. One audit entry stores each mutation's complete before/after snapshot, so all fields changed by that operation restore together. Creation and deletion records are audited but are not reversible through this endpoint. A request with no available reversible change returns HTTP 409.

Timeline and audit records are written in the same transaction as their domain mutation. Recorded events include application creation and edits, status/outcome/posting changes, notes, task creation/completion, follow-up creation/drafting/sending, interview creation/changes, deletion, and undo. Application deletion is rejected when the service actor is not `HUMAN`.

## Search, duplicate warnings, and dashboard API

Application filters are combined with AND logic. Text filters are case-insensitive partial matches; `q` searches title, company, location, remote policy, contract type, source, description, requirements, job URL, email reference, and phone number. Status/outcome are exact enum matches, date bounds are inclusive, and `document_filename` matches attached filenames.

`POST /api/applications` includes `duplicate_warnings` in its normal application response. A match is reported for the same normalized company/title or normalized job URL, with a recent-date reason when application dates are within 30 days. Warnings never change the HTTP 201 response or prevent persistence. Normal list/detail responses contain an empty warning list.

`GET /api/dashboard` returns operational counts, due/overdue tasks and follow-ups, interviews scheduled within seven days, a due-date-ordered upcoming work list, and the ten most recent timeline events. Soft-deleted applications and their child work are excluded. Completed/cancelled tasks and sent/cancelled follow-ups do not count as due.

`GET /api/reminders` returns the background scheduler's last check and grouped due/overdue follow-ups and tasks, plus upcoming interviews. It refreshes every 60 seconds; the scheduler also persists scheduled follow-up notices without changing message state. Follow-ups accept `channel: "EMAIL"`, `"PHONE"`, or `"BOTH"`; legacy records remain `EMAIL`. Phone and combined follow-ups require a saved phone number. The legacy `POST /api/applications/{application_id}/followups/{followup_id}/draft` accepts `{"content":"..."}` for email or combined follow-ups. With no connected provider, it stores an `EMAIL_DRAFT` note, updates the prepared message and returns `location: "LOCAL_NOTE"` with an explicit unsent message. It never marks Ready. `GET /api/integrations` reports mail and calendar connection status.

## Automatic posting checks

`POST /api/applications/{id}/check-posting` runs a deterministic, local check of the saved job URL. It uses HTTPX first, then Schema.org JobPosting metadata through `extruct`, LinkedIn and Indeed job-page identity plus their native Apply controls, and carefully selected visible-page phrases. HTTP 404/410, expired `validThrough`, and strong unavailability phrases can confirm a posting is closed. For an HTTP 401 or 403, or for an otherwise inconclusive successful page, it uses a normal local Chromium session when `POSTING_PLAYWRIGHT_FALLBACK=true`. It does not log in, bypass access restrictions, or solve CAPTCHAs. 429, 5xx, timeouts, malformed metadata, and pages that remain inconclusive return **UNKNOWN**; UNKNOWN does not mean closed and never overwrites a previously confirmed LIVE or CLOSED posting.

Checks store the final URL, HTTP response, method, reason, timestamp, and consecutive inconclusive count. A confirmed state change is added to the timeline, but repeated checks are not. Posting status never changes an application's lifecycle, outcome, or ghosted state. The background scheduler checks eligible non-closed URLs no more often than `POSTING_CHECK_INTERVAL_HOURS=24`, with `POSTING_CHECK_CONCURRENCY=5` by default. It uses a polite local user agent and does not retry aggressively, bypass access restrictions, automate logins, or solve CAPTCHAs.

The normal-browser fallback is enabled by default. Run `python -m playwright install chromium` after installing the project, as shown above. If Chromium is unavailable, the check stays UNKNOWN and records that the browser fallback was unavailable rather than failing the scheduler.

`GET /api/interviews/{interview_id}/calendar.ics` downloads an importable event for an explicit user action. It does not create or update an external calendar event. The code defines `MailProvider` and `CalendarProvider` interfaces for future connected implementations; this release ships disconnected defaults.

## Documents and exports API

`GET /api/applications/{id}/documents` lists CV and cover-letter metadata. `POST` to the same path accepts multipart form data with `document_type` (`CV` or `COVER_LETTER`) and exactly one source: `file`, or `external_reference` plus `filename`. Uploaded files are copied beneath `APP_DATA_DIR/documents/{application_id}`. `GET /api/applications/{id}/documents/{document_id}/content` downloads an uploaded file; referenced documents have no content endpoint payload.

`GET /api/exports/applications.csv` and `GET /api/exports/applications.xlsx` export all active records when called without parameters. Both accept the same query filters as `GET /api/applications`, so the Export screen can export the applied filters exactly. CSV is UTF-8 with a header row. XLSX contains real date cells, a formatted and frozen header, worksheet filters, readable widths, document filenames, phone numbers, and status/outcome colors.

## Agent access and live updates

Open **Settings** in the browser and generate an agent token. Store the shown value in your agent's secure configuration. Only its SHA-256 hash is saved in SQLite. New tokens have read access only; enable other permissions deliberately. Regenerating the token atomically replaces that hash, so the old token is rejected on its next request. Permission toggles take effect immediately. In local mode, human endpoints require loopback access. In hosted mode, all human API routes require a separate browser session, and writes also require the origin and CSRF token. An agent token cannot unlock the human API. Keep loopback defaults for local use; follow [the hosted deployment guide](deploy/README.md) before publishing remote access.

Agent REST operations use `POST /api/agent/tools/{operation}` with `Authorization: Bearer <token>` and a JSON body. `list_applications` and `search_applications` return compact 25-item pages by default; pass `limit` and `cursor` to continue. `get_application` remains the complete record, while `get_application_context` returns the application, work, interviews, documents, recent timeline, and next action in one request. Create operations accept an optional `idempotency_key`; a retry with the same token, operation, and key returns the original result for 30 days. Agent errors use `{ "error": { "code", "message" } }`, and the service records agent identity in the timeline and audits. No agent delete operation exists.

Agent REST and MCP creation, updates, duplicate checks and search filters use `CDI`, `CDD`, `PART_TIME` or `APPRENTICESHIP_INTERNSHIP` for contract types. Recognized French/English wording (for example `Permanent`, `Temps partiel` and `Alternance / Stage`) normalizes to these values; unknown or ambiguous contract facts should be `null`. Existing stored wording remains readable and unchanged by unrelated edits. Agent dates must be ISO `YYYY-MM-DD`; inclusive search bounds require `date_from <= date_to`, and unknown filter fields are rejected. Use the verified application date or the original confirmation email date. Missing job URLs remain allowed when an email reference is available, and agents should leave unknown fields empty rather than add placeholders. `get_tracker_info.application_constraints` and the MCP input schemas advertise these rules.

Compact agent results include `contract_type`, `has_overdue_followup` and `attention_state` (`NORMAL`, `OVERDUE`, `CLOSED`). Overdue means a pending/drafted follow-up in the dashboard queue; closed applications take precedence and have no actionable overdue follow-up. Direct mailbox URLs open as saved; Gmail IDs, RFC Message-IDs and subject references open the message or a Gmail search in the signed-in mailbox. Raw posting/email reference values and nulls stay available as structured data even when the UI displays compact links or omits empty fields.

When importing from an application confirmation email, supply its text or HTML as `confirmation_email` to `create_application`, or call `extract_confirmation_details` first. The shared extractor reads role/employer confirmation patterns from the body, returns the matched text for review, distinguishes ISCOD CV forwarding from an employment offer, and keeps the intermediary separate from the employer. Use the explicit application date when present, otherwise the original email date; never use the import date. An undisclosed ISCOD partner is saved as `Employer not disclosed`, with `intermediary=ISCOD`.

LinkedIn links are reduced to a stable job-ID URL; Indeed tracking links with a `jk` key are reduced to a direct `viewjob` URL. ISCOD partner posting links and explicitly labeled employer vacancy links are also recovered. An Indeed company-confirmation URL remains confirmation evidence only. LinkedIn/Indeed confirmations without a posting URL can retain their source and email reference while the URL is researched.

Posting verification has three steps in the application detail: direct URL inspection, ordinary rendered-browser fallback for inconclusive responses, then **Search manually** (one Google query using the job/position title plus employer) or **Agent search** (copy a prepared prompt for any connected agent), and a recorded browser review. The tracker stores job title and position title as one field, so it is included once in the query. When the employer is undisclosed, the intermediary is only a search clue. The agent prompt directs the agent to use the app data and relevant emails, preserve original email dates, inspect candidate pages in a browser, and save evidence using the agent REST/MCP tools. Copying a prompt does not launch or execute an agent. Clipboard failures expose the prompt for manual copying. The same manual query and prepared prompt are returned by `get_posting_review` over human REST, agent REST and MCP. The same review workflow is available over agent REST/MCP: `check_posting_status`, `get_posting_review`, and `record_posting_review`. The review requires the page URL, notes and (optionally) original check date, plus `same_position=true` for LIVE/CLOSED. Only a verified live match can replace the saved posting URL. Search snippets or missing results alone mean UNKNOWN. Reviews are audited, preserve previous links in the timeline, and never change application lifecycle/outcome.

## AI Agent Integration

Application Tracker exposes one provider-neutral MCP interface backed by `agent_ops.py`:

```text
Application Tracker MCP
        |
        +-- ChatGPT
        +-- Claude
        +-- Claude Desktop
        +-- Codex
        +-- other MCP-compatible agents
```

Every MCP and agent REST operation uses the same validation, permissions, idempotency protection, audit records, and application services. There are no vendor-specific tool sets.

For local MCP clients, leave `MCP_TRANSPORT=stdio` (the default) and configure a command such as:

```json
{
  "mcpServers": {
    "application-tracker": {
      "command": "application-tracker-mcp",
      "env": { "APPLICATION_TRACKER_AGENT_TOKEN": "<generated-token>" }
    }
  }
}
```

For Streamable HTTP, set `MCP_TRANSPORT=streamable-http`. The default endpoint is `http://127.0.0.1:8001/mcp` and requires `Authorization: Bearer <generated-token>`. It exposes the exact same tools as stdio. Keep the loopback default unless TLS and network access controls protect any remote deployment. OAuth 2.1 is intentionally deferred; bearer authentication is isolated at the transport boundary so a future OAuth layer can replace or wrap it without changing the tool layer.

The agent REST endpoint is `http://127.0.0.1:8000/api/agent/`. Generate or regenerate the token in **Settings → Agent access**, then enable the least permissions needed. Plaintext tokens are shown only at generation; SQLite stores only their hashes, and regeneration immediately revokes the old token. **Settings → Agent connection help** displays the actual configured local endpoints without exposing a saved token.

`GET /api/events` streams `application.created`, `application.updated`, `interview.updated`, `task.updated`, and `followup.updated` events after agent mutations. Each event contains only an application ID; the browser refetches current data. Browser EventSource reconnects automatically and resumes from the last event ID.

## Windows executable and Docker

After `pnpm --dir frontend build`, run `./build-windows.ps1` from PowerShell to create `build/windows/ApplicationTracker/ApplicationTracker.exe`. This is a folder-based executable: distribute the entire `ApplicationTracker` folder together. The launcher starts the API on loopback, opens the UI, and keeps running in the system tray when the browser closes. The tray menu has **Open**, **Status**, **Copy API address**, **Settings**, and **Exit**. Exit requests a clean Uvicorn shutdown. By default, the executable stores SQLite and documents under `%LOCALAPPDATA%/ApplicationTracker`; `APP_DATA_DIR` can override this. Startup errors are written to `startup-error.log` in that data directory.

The Docker Compose stack now targets hosted access: Caddy publishes HTTPS, the tracker stays on a private bridge, and SQLite/documents persist in a named volume. It requires a domain and a workspace password hash before startup. Follow [deploy/README.md](deploy/README.md) for secret generation, server checks, backups, updates, restore and phone installation. The password and secret file are never bundled into the image. Local Windows use continues without sign-in; migration `0017_human_sessions` adds hosted sessions and login limits without changing application records.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
pnpm --dir frontend test
pnpm --dir frontend build
```

The frontend build runs the Vue/TypeScript checker and creates `frontend/dist`. The backend then serves that build at its root URL. The automated suite covers phone normalization and rejection through human and agent paths, follow-up channels, reminder classification, local draft fallback, and explicit calendar download.

Manual checks:

1. Start both servers and open the Applications page.
2. In Settings, generate a token and enable the desired permissions.
3. Create and update an application through the agent REST path or MCP while the Applications page remains open. Confirm its table updates without a browser reload.
4. Regenerate the token; confirm the previous token receives HTTP 401 or an MCP tool error immediately.
5. Confirm an agent delete operation is unavailable, and the Settings page never shows the old token again.
6. Expand **System status** and confirm backend version **0.11.0** and **SQLite · Connected**.

The 0.9 agent-token flow remains available but has not been activated in the user's database. The Python test client emits one upstream deprecation warning from Starlette; tests pass.

