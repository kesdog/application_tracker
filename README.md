# Application Tracker

Version **0.1.0** implements the skeleton and health check from `PLAN.md`: FastAPI, SQLite with WAL, and a Vue 3 + TypeScript status page. Application records and other features begin in later releases.

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
{"status":"ok","version":"0.1.0","database":"connected"}
```

It returns HTTP 503 if the database query fails. The frontend checks on load and when **Check again** is clicked, with a five-second timeout. It clears stale version/database values on a failed check. Continuous polling is not part of this release.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
pnpm --dir frontend test
pnpm --dir frontend build
```

The frontend build runs the Vue/TypeScript checker and creates `frontend/dist`. To inspect that build, run `pnpm --dir frontend preview` and open <http://127.0.0.1:4173> while the backend is running. Combined production hosting is planned for 0.10.0.

Manual checks:

1. Start both servers and open the UI.
2. Confirm **Backend: Connected**, backend version **0.1.0**, and **SQLite · Connected**.
3. Stop the backend and refresh the UI.
4. Confirm **Backend: Disconnected**, a retry message, and unavailable version/database values.
5. Restart the backend and click **Check again** to recover.

Verified for this release: six backend tests, five frontend tests, dependency consistency, the frontend production build, and the browser connected/disconnected/recovery flow. The Python test client currently emits two upstream deprecation warnings from Starlette; tests pass.

The initial implementation session leaves both development servers running in the background for review. Their process IDs and logs are under the ignored `.run` directory. Before starting your own copies, stop those specific processes (check the command lines first; recorded IDs may be stale after a reboot):

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -in @([int](Get-Content .run/backend.pid), [int](Get-Content .run/frontend.pid)) } | Select-Object ProcessId, CommandLine
Stop-Process -Id ([int](Get-Content .run/backend.pid)), ([int](Get-Content .run/frontend.pid))
```
