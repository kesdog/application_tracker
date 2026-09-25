# Application Tracker

Version **0.7.0** adds application search and combined filters, advisory duplicate warnings, and an operational dashboard to the FastAPI, SQLite WAL, and Vue 3 + TypeScript tracker.

Use **Add application** to record a job title, company, date applied, and either a job URL or email reference. Saved records appear in a compact table ordered by applied date, newest first. Every new application starts as `SUBMITTED` with no outcome. Job URLs open in a new tab; email references are displayed in the source column. On narrow windows, scroll the table horizontally to see all columns. The health screen remains available under **System status**.

Click a position in the table to open its focus view. **Edit application** lets you update its title, company, date, sources, location, remote policy, contract type, source, description, requirements, status, outcome, and posting state. **Cancel** discards the current draft. Focus URLs use a hash and can be bookmarked or refreshed without a router dependency. Return with **All applications** to see updated status/outcome badges.

Selecting an outcome closes the application. To reopen an application that already has an outcome, select an active status and explicitly check **Clear the existing outcome**. Posting state is independent of the application lifecycle; marking a posting closed does not close the application. Posting checks are recorded manually.

The focus view contains **Interviews**, **Notes**, **Tasks**, and **Follow-ups**. Schedule, edit, and delete interviews with preparation notes, meeting details, and results. Add/edit a typed note, add a task with an optional due date, complete/cancel/reopen tasks, and record follow-ups as drafted, sent, or cancelled. Notes retain their creator and creation time when edited. Each application has its own follow-up sequence starting at 1.

The **Timeline** records application, note, task, follow-up, interview, outcome, and posting-state activity with the actor and time. Reversible edits expose **Undo last change**. Undo restores the complete prior field snapshot, including coupled values such as a task status and completion timestamp. Application deletion requires a second human confirmation and sets `deleted_at`; deleted applications and their work disappear from normal lists without removing database records.

Use the top navigation to open **Interviews** or **Tasks**. Interviews are ordered by scheduled date and show their application, meeting context, and near-term wording such as “Technical interview — tomorrow at 14:00.” Tasks are ordered by due date, show their parent application, and can be completed, cancelled, or reopened from the global view.

Use **Dashboard** to see active application count, due and overdue tasks/follow-ups, upcoming interviews, linked work for the next seven days, and recent activity. The Applications page supports free-text search plus status, outcome, company, position, location, contract, source, remote policy, and application-date filters. Filters combine, can be cleared together, and retain the existing newest-first order.

Creation checks normalized company/title and job URLs against existing applications. A likely duplicate is still saved, then shown as an advisory warning with links and reasons so the user can compare records without blocking legitimate repeat applications.

Follow-ups are tracking records: no email is drafted in a mailbox or sent by these actions. To retain draft text, use an `EMAIL_DRAFT` note. Automatic suggestions, scheduling, and external integrations remain later-release features.

## Requirements and installation

Use Python 3.11+ (tested with 3.12), Node.js 22.12+ (tested with 24), and pnpm 11.19.0. Run these PowerShell commands from the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e '.[dev]'
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

## Settings and storage

The backend reads the root `.env` file; process environment variables take precedence.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_HOST` | `127.0.0.1` | Backend bind address |
| `APP_PORT` | `8000` | Backend port, 1–65535 |
| `APP_ENV` | `development` | Environment label available to the app |
| `APP_DATA_DIR` | `./data` | Directory created during backend startup |
| `LOG_LEVEL` | `info` | Uvicorn logging level; case insensitive |
| `FOLLOWUP_DELAY_DAYS` | `7` | Default delay from creation for a follow-up without a supplied due date (0–3650) |
| `MAX_FOLLOWUP_SUGGESTIONS` | `2` | Stored limit for future automatic suggestions (0–100); never restricts manual creation |

Under **Edit application → Follow-up preferences**, set a delay or suggestion limit for one application. Blank values inherit the global settings; zero is a valid override. Changing preferences affects new follow-ups, not existing due dates. Restart the backend after changing global settings in `.env`.

Relative data paths resolve against the project root, regardless of the terminal's current directory. The database is `data/tracker.sqlite3` by default. SQLite WAL is enabled and verified at startup; connections also enable foreign keys. The engine is disposed on normal server shutdown. Startup fails clearly if storage cannot initialize.

`GET /api/health` checks the live database connection and returns:

```json
{"status":"ok","version":"0.7.0","database":"connected"}
```

It returns HTTP 503 if the database query fails. The frontend checks on load and when **Check again** is clicked, with a five-second timeout. It clears stale version/database values on a failed check. Continuous polling is not part of this release.

## Applications API and migrations

- `POST /api/applications` creates an application and returns HTTP 201 with the saved record.
- `GET /api/applications` returns saved records ordered by applied date descending, then ID. Optional query filters are `q`, `status`, `outcome`, `company`, `title`, `location`, `contract_type`, `source`, `remote_policy`, `date_from`, `date_to`, and `document_filename`.
- `GET /api/applications/{id}` returns a full application or HTTP 404.
- `PATCH /api/applications/{id}` updates only supplied fields and returns the saved application. Omitted fields stay unchanged; explicit null clears an optional field. Required fields cannot be null. Missing records return HTTP 404.
- `DELETE /api/applications/{id}` performs a human-only soft deletion and returns HTTP 204. Deleted records return HTTP 404 and are excluded from normal application and global work lists.
- Invalid data returns HTTP 422. Titles and companies must contain non-whitespace text; job URLs must use HTTP or HTTPS. At least one non-empty job URL or email reference is required. Status and outcome cannot be supplied on creation.

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

Alembic applies pending migrations automatically at backend startup, including upgrades from existing 0.1.0–0.6.0 databases. The fifth migration adds `deleted_at`, timeline events, audit entries, actor identity, and undo state while preserving existing records; 0.7.0 requires no schema change. Child tables enforce application foreign keys and valid statuses; follow-up numbers are unique within each application. Startup stops if migration fails. Tests use temporary databases. To inspect or explicitly apply migrations from the project root:

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
```

Migration commands use the same `.env` settings and database as the application. Run one backend process against the local database during schema upgrades.

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
| `PATCH /followups/{id}` | Edit due date/template reference/status |

Creation returns HTTP 201; updates return HTTP 200. Missing parents or child IDs belonging to another application return HTTP 404. Invalid input returns HTTP 422. Child ownership, IDs, sequence numbers, authorship, and completion/sent timestamps cannot be overwritten through request bodies.

Note types are `GENERAL`, `ASSESSMENT`, `EMAIL_DRAFT`, `INTERVIEW`, and `AGENT`. The human REST routes record `created_by=HUMAN`; note type is a category, not an identity. Notes have UTC `created_at` and `updated_at` timestamps.

Task statuses are `PENDING`, `COMPLETED`, and `CANCELLED`. Completing a task sets `completed_at` once; repeating the same status preserves that timestamp. Returning to pending or cancelled clears it. Tasks with due dates appear first, ordered earliest first.

Follow-up statuses are `PENDING`, `DRAFTED`, `SENT`, and `CANCELLED`. Marking sent sets `sent_at` once. Changing away from sent clears it; the current release stores current state, with audit history planned for 0.6.0. Follow-up creation takes a SQLite write lock before allocating the next sequence number, so simultaneous requests receive distinct numbers. The default due date is the creation time plus the effective delay; an explicit due date overrides it. Manual creation always remains available, even when the suggestion limit is zero or already exceeded.

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

The context response currently returns `documents: []` because document storage is introduced in 0.8.0. Global tasks with no due date sort after dated tasks. Interview and task writes remain in the existing application-scoped routes so parent ownership is always checked.

## Timeline, audit, undo, and deletion API

`GET /api/applications/{id}/timeline` returns newest-first events and `undo_available`. Events contain `event_type`, `summary`, `actor_type`, optional `actor_reference`, metadata, and a UTC timestamp. Actor types are `HUMAN`, `AGENT`, and `SYSTEM`; human REST mutations currently record `HUMAN`, while the shared services preserve agent/system identities supplied by future integrations.

`POST /api/applications/{id}/undo` restores the latest reversible mutation and returns the affected entity and fields. One audit entry stores each mutation's complete before/after snapshot, so all fields changed by that operation restore together. Creation and deletion records are audited but are not reversible through this endpoint. A request with no available reversible change returns HTTP 409.

Timeline and audit records are written in the same transaction as their domain mutation. Recorded events include application creation and edits, status/outcome/posting changes, notes, task creation/completion, follow-up creation/drafting/sending, interview creation/changes, deletion, and undo. Application deletion is rejected when the service actor is not `HUMAN`.

## Search, duplicate warnings, and dashboard API

Application filters are combined with AND logic. Text filters are case-insensitive partial matches; `q` searches title, company, location, remote policy, contract type, source, description, requirements, job URL, and email reference. Status/outcome are exact enum matches and date bounds are inclusive. `document_filename` intentionally returns no matches until documents are introduced in 0.8.0.

`POST /api/applications` includes `duplicate_warnings` in its normal application response. A match is reported for the same normalized company/title or normalized job URL, with a recent-date reason when application dates are within 30 days. Warnings never change the HTTP 201 response or prevent persistence. Normal list/detail responses contain an empty warning list.

`GET /api/dashboard` returns operational counts, due/overdue tasks and follow-ups, interviews scheduled within seven days, a due-date-ordered upcoming work list, and the ten most recent timeline events. Soft-deleted applications and their child work are excluded. Completed/cancelled tasks and sent/cancelled follow-ups do not count as due.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
pnpm --dir frontend test
pnpm --dir frontend build
```

The frontend build runs the Vue/TypeScript checker and creates `frontend/dist`. To inspect that build, run `pnpm --dir frontend preview` and open <http://127.0.0.1:4173> while the backend is running. Combined production hosting is planned for 0.10.0.

Manual checks:

1. Start both servers, create an application, and click its position in the table.
2. Create several varied applications, then search by title and filter by company, status, and date. Combine filters and clear them.
3. Create a second record with the same company/title or job URL. Confirm it saves and shows a possible-duplicate warning linking to the first record.
4. Add overdue and upcoming tasks/follow-ups plus an upcoming interview.
5. Open **Dashboard** and confirm counts, due-date order, application links, and recent activity change with the data.
6. Complete a due task, refresh Dashboard, and confirm its count/item disappear.
7. Expand **System status** and confirm backend version **0.7.0** and **SQLite · Connected**.

Verified for this release: 114 backend tests, 24 frontend tests, the frontend production build, Alembic migration consistency, dependency checks, and a browser workflow. Coverage includes combined filters, free-text search, placeholder document filtering, non-blocking duplicate detection, dashboard counts/order, soft-delete exclusion, query serialization, and the existing application/work behavior. The Python test client currently emits two upstream deprecation warnings from Starlette; tests pass.

The initial implementation session leaves both development servers running in the background for review. Their process IDs and logs are under the ignored `.run` directory. Before starting your own copies, stop those specific processes (check the command lines first; recorded IDs may be stale after a reboot):

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -in @([int](Get-Content .run/backend.pid), [int](Get-Content .run/frontend.pid)) } | Select-Object ProcessId, CommandLine
Stop-Process -Id ([int](Get-Content .run/backend.pid)), ([int](Get-Content .run/frontend.pid))
```
