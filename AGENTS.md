# Application Tracker development checks

Use `TESTING.md` for test ownership and commands.

- During edits, run `python scripts/test.py --changed` with the project virtual
  environment, or select the relevant feature with `--segment`. Inspect selection
  with `--dry-run` when useful. For committed changes, include `--base <ref>`.
- Shared/unknown source changes deliberately select broader checks. Include
  additional segments for runtime or data dependencies that imports cannot infer.
- Before pushing, run `.\.venv\Scripts\python.exe scripts/test.py --full` and fix
  failures. This includes the production build/type-check, dependency consistency,
  every backend/frontend test, and the selector regressions.
- Keep tests in the owning feature directory. Consolidate repeated setup and
  genuinely duplicate assertions; preserve distinct behavior and failure cases.
- Update the runner's backend consumer map and selection regressions when adding
  a backend module or changing dependencies between features.
