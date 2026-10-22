# Development checks

Use the project virtual environment from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/test.py --list
.\.venv\Scripts\python.exe scripts/test.py --changed
.\.venv\Scripts\python.exe scripts/test.py --changed --base origin/main
.\.venv\Scripts\python.exe scripts/test.py --segment applications
.\.venv\Scripts\python.exe scripts/test.py --segment followups toolbox
.\.venv\Scripts\python.exe scripts/test.py --full
```

`--changed` includes staged, unstaged, deleted and untracked files. `--base` also
includes committed changes. Use `--files <paths> --dry-run` to inspect selection.
Use `--segment` for focused iterations and `--full` before pushing.

The full gate builds and type-checks the frontend, checks installed Python
dependencies, then runs all application, toolbox and runner tests. The toolbox
is independent: routine follow-up checks run the app's adapter tests, while
`--segment toolbox` runs the vendored library tests. `--full` runs both once.

For a clean release environment, install `requirements-dev.lock` with
`pip install --require-hashes -r requirements-dev.lock`, then install the app and
vendored toolbox with `--no-deps --no-build-isolation`. The universal lock contains
platform markers and includes the build/test/search dependencies. Regenerate both
locks with uv 0.13.5 and `python scripts/lock.py` after a reviewed dependency change.

`python scripts/artifact_smoke.py` exercises the installed distribution, compiled
UI, migrations, persistence, document upload and backup/recovery with synthetic
data. Windows builds also support `APP_DESKTOP_SMOKE=1` for a noninteractive
start/health/shutdown check. `.github/workflows/release-gate.yml` requires Windows
and Linux gates and retains candidate ZIP/image artifacts and logs. It does not
establish live OAuth, physical-phone acceptance or signing/upgrade readiness.
CI pins Python 3.13.17 on both platforms, which has official Windows and Linux
runner builds; local validation also covers the installed Python 3.12.14 runtime.

Tests belong in `backend/tests/<segment>/` and `frontend/tests/<segment>/`.
`--list` is the current segment registry; runner checks live in `tests/`.
Put reusable setup in support modules or fixtures rather than importing helpers
from collected test modules. Each database-backed test keeps an isolated
workspace and app lifespan. Temporary workspaces are under ignored `.run/`.

Backend source selection follows the consumer map in `scripts/test.py`;
frontend selection follows local imports transitively. Shared and unknown
source files deliberately select broader checks. Dependency, build, deployment,
runner and generic test-support changes select the full applicable suites.
Update the consumer map when adding backend modules or cross-feature consumers.
The selector cannot infer every runtime/data dependency; include extra segments
or run `--full` when a change crosses those boundaries.

Default validation is offline. Live Google probes require explicit operator
opt-in and independently authorized test accounts; they are not part of routine
local or CI runs. Do not give CI a personal mailbox or workspace database.

The detailed coverage inventory and review notes are maintained locally in
ignored `test.md`. It is intentionally separate from this public contributor
guide and must not be force-added to Git or included in application bundles.
