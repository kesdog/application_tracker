# Testing by feature

Use the project Python environment from the repository root. During development,
run the segments affected by the edit; run the complete gate before pushing.

```powershell
# Choose checks from staged, unstaged, deleted and untracked files.
.\.venv\Scripts\python.exe scripts/test.py --changed

# Also include commits since a branch/ref (plus current worktree edits).
.\.venv\Scripts\python.exe scripts/test.py --changed --base origin/main

# Inspect selection without running anything.
.\.venv\Scripts\python.exe scripts/test.py --files backend/app/push.py --dry-run

# Explicit feature selection, useful during repeated edits.
.\.venv\Scripts\python.exe scripts/test.py --segment applications
.\.venv\Scripts\python.exe scripts/test.py --segment followups notifications

# Required before a push: build/type-check, pip check, all backend/tooling tests,
# then all frontend tests. Stops at the first failed command.
.\.venv\Scripts\python.exe scripts/test.py --full
```

`--list` shows the available segments. `--files` accepts one or more paths,
including absolute paths inside this checkout. Selection unions the affected
segments, so a segment runs once even when several edited files require it.
Documentation-only edits and a clean checkout select no tests.

The runner places isolated pytest workspaces under the ignored `.run/` directory
with a fresh name for each invocation, avoiding stale or inaccessible user temp
folders. They can be removed when no test run is active.

| Segment | Backend coverage | Frontend coverage |
| --- | --- | --- |
| applications | Creation, lifecycle, contacts, deadlines | Wizard, table, filters, status/action presentation, source/mailbox links |
| activity | Timeline, actors, undo, soft deletion | Covered by the shared API contract |
| work | Notes, tasks, scoping, validation, foreign keys | Date labels |
| followups | Prepared messages, revisions, scheduling, legacy compatibility, local drafts | Editor, templates, queue, notices |
| interviews | CRUD, context, global ordering, calendar | Covered by the shared API contract and date labels |
| dashboard | Search, duplicates, counts, work ordering, reminder snapshot | Covered by the shared API contract and action presentation |
| documents | Uploads, references, filename search, CSV/XLSX | Covered by the shared API contract |
| posting | Confirmation extraction, direct/rendered checks, manual reviews | No dedicated component test; shared changes use frontend fallback |
| agent | Permissions, idempotency, REST/MCP, schemas, SSE | Covered by the shared API contract |
| auth | Hosted/local access, sessions, CSRF, backup/restore | Login, session loss, protected UI, CSRF |
| notifications | Push delivery, leases, retries, subscription/auth, restore | Device opt-in/removal and service worker |
| migrations | Populated historical database upgrades and restart preservation | — |
| system | Health, configuration, startup, static serving | — |
| api | — | Health, request route table, response/error handling, multipart and links |
| appearance | — | Palettes, persistence, readability and table preferences |
| shell | — | Sidebar accessibility/persistence and theme controls |
| tooling | Test selector regressions | — |

Backend files live in `backend/tests/<segment>/`, frontend files in
`frontend/tests/<segment>/`, and runner regressions in `tests/`. Cross-feature
tests have one owning segment; automatic selection also includes their consumers.

For a single test or layer, the underlying tools still work:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/applications -q
.\.venv\Scripts\python.exe -m pytest backend/tests/migrations -q
pnpm --dir frontend test tests/applications
pnpm --dir frontend test tests/api/requests.test.ts
```

## How automatic selection works

Backend selection uses the reviewed consumer map in `scripts/test.py`.
Application services/schemas, work, activity, templates, models, database,
configuration, startup and migrations are shared across the backend and select
all backend segments. Smaller modules select their feature and known consumers.
Agent transport changes also select posting, follow-ups and hosted access.

Frontend selection follows local imports transitively through TypeScript and Vue
files, including dynamic imports, test mocks and raw public assets. It selects
the owning segments of dependent tests. This intentionally includes shell/auth
checks when their imported component tree depends on the edit.

Unknown or currently uncovered source files select the entire affected layer;
dependency/build/deployment and runner changes select both layers. This is a
conservative development aid, not a guarantee of impact analysis: it cannot
infer every runtime/data dependency. If a change crosses feature boundaries,
add the relevant segments or use `--full`. When adding a backend module, add its
consumers to the map. Add new tests under an existing segment, or register a new
segment in the runner and its selection tests.

## Review and consolidation

The review started with 248 backend cases and 101 frontend cases. Existing
distinct regression coverage was kept for authentication, data preservation,
transport permissions, concurrent writes, DST, notification retries/leases,
privacy and browser behavior.

- Eight backend modules now share a function-scoped client fixture. Every test
  still gets an isolated temporary database and app lifespan.
- Historical migration tests share the upgrade/seeding fixture and live together.
  Their seeded snapshots exercise distinct schema transitions, so they remain
  separate. The schema-head assertion follows Alembic's current head.
- The smaller due/overdue dashboard check was folded into the richer dashboard
  scenario. The empty-document-filter assertion was folded into document search.
- Free-text search creates one application and checks all nine metadata queries,
  avoiding eight repeated database startups while retaining every assertion.
- Seven small frontend API files were consolidated into request contract tables.
  Read/write paths, encoded IDs, explicit nulls, error payloads, multipart uploads,
  export links and token rotation requests remain checked. Date behavior stays
  in its own utility test.
- Repeated palette mutation assertions were removed from status-tag cases;
  appearance tests already check that behavior. Tag rendering assertions remain.
- Release-number tests were reassigned to their owning features. Static-serving
  checks now create their own assets instead of requiring an old `frontend/dist`;
  the full gate still builds/type-checks the real frontend.

The application suites now have 238 backend cases and 83 frontend cases, plus six
selector regressions. Case counts measure organization, not coverage percentage;
consolidated tables still exercise multiple assertions and inputs. Direct
`pytest` and `pnpm test` continue to run their full respective suites.
