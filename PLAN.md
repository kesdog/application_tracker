# Application Tracker — V1 Implementation Plan

Target stack: Python 3, FastAPI, SQLAlchemy 2, Alembic, Pydantic, SQLite (WAL), Vue 3, TypeScript, Vite, Pinia, SSE, MCP.

This plan builds V1 in ten incremental releases from `0.1.0` through `0.10.0`.

## Working rules

- Each release must produce a visible, manually testable change.
- Keep each release focused: edit only a small group of files at a time.
- Add or update tests in the same release as the feature.
- Do not begin the next release until the current one starts cleanly and its manual checks pass.
- Prefer extending existing files over introducing abstractions too early.
- Keep domain/business rules in backend services, not in REST, MCP, or Vue components.
- The human UI has no login in V1.
- Agent access requires a bearer token.
- Agents may create/update records and drafts, but may not delete applications.
- No automatic email sending.
- No spreadsheet import in V1.
- No backup/update system in V1.

---

# 0.1.0 — Skeleton + health check

## Goal

Create the smallest runnable full-stack application with a Python backend, Vue frontend, SQLite initialization, and one visible health/status screen.

## Build

Backend:
- Create FastAPI app.
- Add `/api/health` endpoint.
- Create SQLite engine and enable WAL mode.
- Create application settings loader for `.env` values:
  - `APP_HOST`
  - `APP_PORT`
  - `APP_ENV`
  - `APP_DATA_DIR`
  - `LOG_LEVEL`
- Create the initial data directory if missing.

Frontend:
- Create Vue 3 + TypeScript app.
- Add one page showing:
  - application name
  - backend connection status
  - backend version

Initial project files should stay minimal, for example:

```text
backend/
  app/
    main.py
    config.py
    database.py
  tests/
    test_health.py
frontend/
  src/
    App.vue
    api.ts
  package.json
.env.example
pyproject.toml
README.md
```

## Tests

Automated:
- `/api/health` returns HTTP 200.
- Response contains expected version.
- SQLite connection opens successfully.

Manual:
1. Start backend.
2. Start frontend.
3. Open the UI.
4. Confirm it displays `Backend: Connected`.
5. Stop the backend and confirm the UI shows a clear disconnected state after refresh.

## Visible result

A browser page proves that Vue can talk to FastAPI and that the local application data directory/database can initialize.

## Do not add yet

- Application CRUD
- Router library unless already required by Vue scaffold
- Pinia unless needed by scaffold
- MCP
- SSE
- tray executable

---

# 0.2.0 — Application model + create/list workflow

## Goal

Allow the user to create submitted applications and see them in a basic table.

## Domain

Create `Application` with:

Required:
- `id`
- `job_title`
- `company`
- `date_applied`
- at least one of:
  - `job_url`
  - `email_reference`

Optional:
- `location`
- `remote_policy`
- `contract_type`
- `source`
- `description`
- `requirements`

Enums:

```text
ApplicationStatus:
- SUBMITTED
- INTERVIEW
- CLOSED

ApplicationOutcome:
- SUCCESSFUL
- UNSUCCESSFUL
- WITHDRAWN
- JOB_CANCELLED
- GHOSTED
```

Default:
- `status = SUBMITTED`
- `outcome = null`

## Backend

Add:
- SQLAlchemy application model.
- Pydantic create/read schemas.
- Alembic initial migration.
- `POST /api/applications`
- `GET /api/applications`
- Validation requiring `job_url` or `email_reference`.

## Frontend

Add:
- simple application table
- simple create form
- required fields only at first
- source link/reference displayed in the table or row detail

Keep styling minimal.

## Tests

Automated:
- create valid application with URL
- create valid application with email reference
- reject application with neither
- list applications
- default status is `SUBMITTED`

Manual:
1. Create an application from the UI.
2. Refresh the page.
3. Confirm it remains in the table.
4. Click its source URL or inspect its email reference.

## Visible result

The project already replaces the most primitive spreadsheet use case: recording submitted applications persistently.

---

# 0.3.0 — Focus view + edit + lifecycle

## Goal

Make one application fully inspectable and editable, and implement the core lifecycle.

## Backend

Add:
- `GET /api/applications/{id}`
- `PATCH /api/applications/{id}`
- lifecycle validation
- `posting_status`
- `posting_last_checked_at`

Posting enum:

```text
UNKNOWN
LIVE
CLOSED
```

Rules:
- `outcome` may remain null while active.
- setting an outcome should require or set `status = CLOSED`.
- reopening a closed application clears outcome only if explicitly requested.

## Frontend

Add an Application Focus view containing:
- job title
- company
- applied date
- source link/reference
- status
- outcome
- optional metadata
- description
- requirements
- posting state

Add edit controls.

Do not build the timeline yet.

## Tests

Automated:
- update application fields
- transition `SUBMITTED -> INTERVIEW`
- transition to `CLOSED`
- reject invalid outcome/state combinations

Manual:
1. Open an application from the table.
2. Edit company/title/location.
3. Change status to `INTERVIEW`.
4. Close it as `UNSUCCESSFUL`.
5. Return to the table and confirm state is visible.

## Visible result

The user can manage the complete basic lifecycle without touching SQLite or a spreadsheet.

---

# 0.4.0 — Notes + tasks + follow-ups

## Goal

Add the operational work around an application without introducing email/calendar integrations yet.

## Backend

Add lightweight child objects:

### Note
- `id`
- `application_id`
- `content`
- `type`
- `created_by`
- timestamps

Suggested note types:
- `GENERAL`
- `ASSESSMENT`
- `EMAIL_DRAFT`
- `INTERVIEW`
- `AGENT`

### Task
- `id`
- `application_id`
- `title`
- `description`
- `due_at`
- `completed_at`
- `status`

Task status:
- `PENDING`
- `COMPLETED`
- `CANCELLED`

### FollowUp
Keep it deliberately small:
- `id`
- `application_id`
- `sequence_number`
- `due_at`
- `sent_at`
- `status`
- `template_reference`

Follow-up status:
- `PENDING`
- `DRAFTED`
- `SENT`
- `CANCELLED`

Defaults:
- global follow-up delay: 7 days
- global max automatic follow-up suggestions: 2

Per-application overrides may be nullable in this release if implementing them would expand the diff too much; otherwise add them here.

## Frontend

In Application Focus view add simple sections for:
- Notes
- Tasks
- Follow-ups

Allow:
- add/edit note
- add/complete task
- add follow-up
- mark follow-up drafted/sent/cancelled

## Tests

Automated:
- child objects cannot exist without an application
- task completion sets completion timestamp
- follow-up sequence increments correctly
- max follow-up setting does not prevent manual creation

Manual:
1. Add an assessment note.
2. Create a due task.
3. Create two follow-ups.
4. Mark one sent.
5. Confirm all remain associated with the correct application.

## Visible result

A real application can now be actively managed after submission instead of just recorded.

---

# 0.5.0 — Interviews + upcoming work views

## Goal

Add interviews as first-class application context and create useful global Interviews and Tasks views.

## Backend

Add `Interview`:
- `id`
- `application_id` required
- `type`
- `scheduled_at`
- `duration`
- `location`
- `meeting_url`
- `interviewer`
- `email_reference`
- `notes`
- `result`
- timestamps

Interview type:
- `PHONE`
- `HR`
- `TECHNICAL`
- `ONSITE`
- `FINAL`
- `OTHER`

Add:
- interview CRUD except deletion can remain human-only through UI
- `GET /api/interviews`
- `GET /api/tasks`
- date ordering
- an interview-context endpoint that returns the interview plus its parent application, relevant notes/tasks, and attached document metadata available so far

## Frontend

Add top-level views:
- Interviews
- Tasks

Application Focus:
- add Interviews section

Upcoming dates should be prominent.

Example UI wording:

```text
Technical interview — tomorrow at 14:00
Assessment task — due in 3 days
```

## Tests

Automated:
- interview requires valid application
- upcoming interviews are sorted correctly
- global task list only contains application-linked tasks
- context endpoint contains parent application

Manual:
1. Add two interviews to one application.
2. Add one interview to another.
3. Open global Interviews view.
4. Confirm date order and application context are clear.
5. Open global Tasks view and verify due dates.

## Visible result

The tracker now answers: “What do I need to prepare for next?”

---

# 0.6.0 — Timeline + audit + undo

## Goal

Make changes traceable for both humans and agents.

## Backend

Add `TimelineEvent`:
- `id`
- `application_id`
- `event_type`
- `actor_type`
- `actor_reference`
- `summary`
- metadata JSON
- `created_at`

Actor types:
- `HUMAN`
- `AGENT`
- `SYSTEM`

Automatically create timeline events for:
- application created
- status/outcome changed
- note added
- task created/completed
- follow-up created/drafted/sent
- interview created/changed
- posting status changed

Add `AuditEntry` for reversible mutations:
- entity type/id
- field/action
- previous value
- new value
- actor
- timestamp
- reversible flag

Add one simple undo endpoint for the most recent reversible edit on an application.

Deletion:
- human-only
- soft delete using `deleted_at`

## Frontend

Application Focus:
- replace plain activity presentation with a chronological timeline
- use simple icons and semantic colors
- add `Undo last change` only when the backend says an undo is available

## Tests

Automated:
- timeline event created on status change
- agent/human actor preserved
- undo restores previous value
- soft-deleted applications are excluded from normal list
- agent deletion path is rejected

Manual:
1. Change application status.
2. Add a note.
3. Complete a task.
4. Confirm each event appears in timeline order.
5. Undo one reversible field change.

## Visible result

The user can understand what changed and recover from a simple mistake.

---

# 0.7.0 — Search, filters, duplicate warning + dashboard

## Goal

Make hundreds of applications manageable.

## Backend

Expand `GET /api/applications` with filters:
- free text
- status/outcome
- company
- title
- location
- contract type
- source
- remote policy
- application date range
- document filename once documents are added in 0.8.0

For this release, document filtering may return no matches until 0.8.0 rather than introducing document storage early.

Add duplicate detection based on:
- normalized company
- normalized title
- job URL
- recent application dates

Behavior:
- warn
- never block creation

Add dashboard summary endpoint:
- active applications
- follow-ups due/overdue
- tasks due/overdue
- upcoming interviews
- recent activity

No conversion analytics.

## Frontend

Applications table:
- search
- filters
- clear filters
- semantic status/outcome colors

Dashboard:
- operational counts only
- upcoming items
- recent activity

## Tests

Automated:
- combined filters
- free-text search
- duplicate warning does not prevent creation
- dashboard counts only relevant active data

Manual:
1. Create several varied applications.
2. Filter by company/status/date.
3. Search by title.
4. Create a likely duplicate and confirm warning is visible.
5. Verify dashboard changes after adding/completing tasks.

## Visible result

The application becomes usable with a realistically large tracking list.

---

# 0.8.0 — Documents + CSV/XLSX export

## Goal

Support the two document types needed by V1 and let users return to spreadsheet workflows at any time.

## Backend

Add `ApplicationDocument`:
- `id`
- `application_id`
- `type`
- `filename`
- `storage_path`
- `external_reference`
- timestamps

Document type:
- `CV`
- `COVER_LETTER`

Rules:
- allow uploaded file OR reference
- uploaded files live under configured application data directory
- document generation is out of scope

Add document filename filtering to application search.

Add export endpoints:
- CSV — all
- CSV — current filters
- XLSX — all
- XLSX — current filters

XLSX requirements:
- formatted header row
- frozen header
- filter row
- proper date cells
- sensible widths
- status/outcome color coding

## Frontend

Application Focus:
- attach CV
- attach cover letter
- add external/local reference instead of upload
- show document filename

Applications view:
- export all
- export current view
- choose CSV/XLSX

## Tests

Automated:
- document belongs to application
- uploaded file is stored in configured directory
- filename filter works
- CSV contains expected rows
- filtered export only contains matching rows
- XLSX can be opened by library and expected worksheet/cells exist

Manual:
1. Attach a CV to an application.
2. Search using part of its filename.
3. Export current filtered view to CSV.
4. Export same view to XLSX.
5. Open workbook and verify colors, filters, dates and row count.

## Visible result

The tracker can replace Excel without locking the user's information inside the application.

---

# 0.9.0 — Agent REST auth + MCP + live UI invalidation

## Goal

Make the tracker genuinely agent-friendly without embedding an AI model.

## Backend

Add agent token support:
- generate secure random token
- display plaintext only at creation/regeneration time
- store only a hash
- bearer-token middleware/dependency
- regenerate atomically
- previous token becomes invalid immediately

Add configurable permissions:
- read
- create
- edit
- draft
- tasks
- interviews

Deletion remains forbidden to agents.

Expose agent-friendly REST operations over existing services.

Add MCP server exposing the same service layer, including tools such as:
- `list_applications`
- `search_applications`
- `get_application`
- `create_application`
- `update_application`
- `create_note`
- `create_followup`
- `mark_followup_sent`
- `create_interview`
- `update_interview`
- `get_interview_context`
- `create_task`
- `complete_task`
- `get_application_timeline`
- `find_possible_duplicates`
- `get_upcoming_items`

Add SSE endpoint for lightweight UI invalidation.

Events only need enough information to refetch:

```text
application.updated
application.created
interview.updated
task.updated
followup.updated
```

Do not stream full application state.

## Frontend

Settings:
- generate token
- regenerate token
- show token once
- permission toggles

Global app shell:
- connect to SSE
- refetch affected current data when event arrives

## Tests

Automated:
- unauthenticated agent request rejected
- valid token accepted
- regenerated old token rejected
- permission enforcement
- delete rejected for agents
- MCP tool and REST path produce equivalent service behavior
- SSE event emitted after agent mutation

Manual:
1. Open application table in browser.
2. Create/update an application through REST or MCP.
3. Confirm the open UI reflects the change without full browser refresh.
4. Regenerate token.
5. Confirm old token stops working immediately.

## Visible result

An external agent can safely maintain the tracker while a human watches changes appear in the UI.

---

# 0.10.0 — Integrations shell + scheduler + Windows executable + Docker release

## Goal

Turn the project into an installable/useful V1 rather than only a development server.

## Backend/application

Add lightweight scheduler for:
- due follow-ups
- overdue follow-ups
- due tasks
- overdue tasks
- upcoming interviews

Important:
- never send email automatically
- never close applications automatically
- never mark an application ghosted automatically

Follow-up drafting behavior:
1. If connected mail provider supports drafts, create mailbox draft.
2. Otherwise store draft content as an `EMAIL_DRAFT` note.
3. Surface clearly that it was not placed into a mailbox.

Create integration interfaces:

```text
MailProvider
- is_connected
- create_draft
- open_message

CalendarProvider
- is_connected
- create_event
- update_event
```

V1 integration UI can support link/configuration shells even if only one provider is initially implemented.

Calendar behavior:
- interviews/assessment tasks may offer calendar event creation
- user action or agent request creates the event
- no silent external calendar mutation

## Windows desktop host

Create launcher that:
- starts local backend
- hosts built frontend
- starts scheduler
- creates system tray icon
- opens UI

Tray actions:
- Open
- Status
- Copy API address
- Settings
- Exit

`Exit` should shut down the server cleanly.

Default bind:

```text
APP_HOST=127.0.0.1
```

Development/Docker may use:

```text
APP_HOST=0.0.0.0
```

Network exposure remains an environment/startup concern.

## Docker

Create production Docker build using the same backend and compiled Vue frontend.

Persist:
- SQLite database
- documents
- configuration/data directory

## Tests

Automated:
- scheduler identifies due items
- scheduler does not send mail by itself
- provider fallback creates note draft
- graceful shutdown closes server/database cleanly where practical to test
- production build serves frontend
- Docker image starts with mounted data directory

Manual Windows test:
1. Launch executable.
2. Confirm tray icon appears.
3. Confirm UI opens.
4. Close browser and verify tracker remains running.
5. Reopen from tray.
6. Exit from tray and verify API is no longer reachable.

Manual Docker test:
1. Start container with persistent volume.
2. Create application.
3. Restart container.
4. Confirm data and documents remain.
5. Confirm API/MCP bind according to environment configuration.

## Visible result

V1 is distributable, persistent, agent-accessible, and useful as a daily application tracker.

---

# V1 completion checklist

V1 is complete when all of the following work without directly manipulating the database:

- create and edit submitted applications
- preserve source URL or email reference
- track submitted/interview/closed lifecycle
- record successful/unsuccessful/other outcomes
- create notes, tasks, follow-ups and interviews
- show upcoming dates prominently
- show chronological timeline
- audit and undo simple reversible changes
- search/filter hundreds of applications
- warn about possible duplicates without blocking
- attach/reference CV and cover letter
- export all or filtered data to CSV and styled XLSX
- issue/revoke agent token
- manipulate tracker through REST and MCP
- update open UI after external agent changes
- draft follow-up in mailbox when integration exists, otherwise as note
- run as Windows executable with tray behavior
- run in Docker with persistent data

# Deferred to V2

- CSV/XLSX import wizard
- backups and restore
- application update checker
- macOS packaging
- Linux CLI distribution
- richer calendar integrations
- multiple agent tokens/identities
- advanced webhook configuration
- analytics/conversion funnels
- document versioning
- multi-user support
