# Application Tracker

Version **0.3.0** adds an application focus view, editing, lifecycle transitions, and posting state to the FastAPI, SQLite WAL, and Vue 3 + TypeScript tracker.

Use **Add application** to record a job title, company, date applied, and either a job URL or email reference. Saved records appear in a compact table ordered by applied date, newest first. Every new application starts as `SUBMITTED` with no outcome. Job URLs open in a new tab; email references are displayed in the source column. On narrow windows, scroll the table horizontally to see all columns. The health screen remains available under **System status**.

Click a position in the table to open its focus view. **Edit application** lets you update its title, company, date, sources, location, remote policy, contract type, source, description, requirements, status, outcome, and posting state. **Cancel** discards the current draft. Focus URLs use a hash and can be bookmarked or refreshed without a router dependency. Return with **All applications** to see updated status/outcome badges.

Selecting an outcome closes the application. To reopen an application that already has an outcome, select an active status and explicitly check **Clear the existing outcome**. Posting state is independent of the application lifecycle; marking a posting closed does not close the application. Posting checks are recorded manually. Notes and tasks are planned for 0.4.0.

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

Relative data paths resolve against the project root, regardless of the terminal's current directory. The database is `data/tracker.sqlite3` by default. SQLite WAL is enabled and verified at startup; connections also enable foreign keys. The engine is disposed on normal server shutdown. Startup fails clearly if storage cannot initialize.

`GET /api/health` checks the live database connection and returns:

```json
{"status":"ok","version":"0.3.0","database":"connected"}
```

It returns HTTP 503 if the database query fails. The frontend checks on load and when **Check again** is clicked, with a five-second timeout. It clears stale version/database values on a failed check. Continuous polling is not part of this release.

## Applications API and migrations

- `POST /api/applications` creates an application and returns HTTP 201 with the saved record.
- `GET /api/applications` returns the saved records, ordered by applied date descending, then ID.
- `GET /api/applications/{id}` returns a full application or HTTP 404.
- `PATCH /api/applications/{id}` updates only supplied fields and returns the saved application. Omitted fields stay unchanged; explicit null clears an optional field. Required fields cannot be null. Missing records return HTTP 404.
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

Alembic applies pending migrations automatically at backend startup, including upgrades from existing 0.1.0 and 0.2.0 databases. The second migration adds posting fields and the outcome/status constraint while preserving existing application records. Startup stops if migration fails. Tests use temporary databases. To inspect or explicitly apply migrations from the project root:

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
```

Migration commands use the same `.env` settings and database as the application. Run one backend process against the local database during schema upgrades.

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
2. Edit the company, title, and location; save and confirm the focus view reflects the changes.
3. Change status to `INTERVIEW`, then set outcome to `UNSUCCESSFUL` and confirm status becomes `CLOSED`.
4. Return to **All applications** and confirm status/outcome are visible in the table.
5. Reopen the editor, choose `INTERVIEW`, and confirm saving requires explicitly clearing the existing outcome.
6. Record posting state and a checked time, save, and refresh the focus URL. Confirm the changes persist.
7. Cancel an unsaved edit and confirm it is discarded. Attempt to clear both sources and confirm the save is rejected.
8. Expand **System status** and confirm backend version **0.3.0** and **SQLite · Connected**.

Verified for this release: 49 backend tests, 12 frontend tests, and the frontend production build. Browser checks cover opening a record, editing company/title/location, moving to interview, closing as unsuccessful, updated table badges, explicit outcome clearing to reopen, posting checks, and focus-view refresh. Backend tests cover invalid edits without partial writes, direct service lifecycle enforcement, database constraints, UTC timestamps, upgrading populated 0.2.0 databases, restart persistence, and migration/model consistency. Browser sample records were kept in an isolated `.run` database. The Python test client currently emits two upstream deprecation warnings from Starlette; tests pass.

The initial implementation session leaves both development servers running in the background for review. Their process IDs and logs are under the ignored `.run` directory. Before starting your own copies, stop those specific processes (check the command lines first; recorded IDs may be stale after a reboot):

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -in @([int](Get-Content .run/backend.pid), [int](Get-Content .run/frontend.pid)) } | Select-Object ProcessId, CommandLine
Stop-Process -Id ([int](Get-Content .run/backend.pid)), ([int](Get-Content .run/frontend.pid))
```
