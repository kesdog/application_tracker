# Opt-in upgrades and recovery

Local tracking remains available without Google, AI, hosted services or sign-in.
An installation upgrade never authorizes an email send, provider connection or
cloud workspace migration. Current releases use manual upgrades. You may upgrade
now, do it later, or skip a version; there is no silent installer or update agent.

## Data locations

| Installed desktop | Default writable directory |
| --- | --- |
| Windows | `%LOCALAPPDATA%\ApplicationTracker` (existing location preserved) |
| macOS | `~/Library/Application Support/ApplicationTracker` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/ApplicationTracker` |

Set `APP_DATA_DIR` or launch with `--data-dir /absolute/path` for an explicit
workspace. Source checkouts still use the repository's `data/` directory and
`.env`; frozen executables do not load bundled dotenv files. Set `APP_PORT` in the
launch environment when using a non-default port. Installed defaults are 8000;
the existing local source checkout can keep its configured 8005.

Older experimental Mac/Linux frozen builds may have used `~/ApplicationTracker`.
Stop that build, create and verify a backup, and restore into the new empty
platform directory. No automatic path guessing or database merging is performed.
Do not put a live database inside an app bundle, installer directory or sync drive.
Only one desktop process may own a workspace; a second owner or occupied port
fails before starting another scheduler. Do not run a source/container writer
against the same SQLite directory as a desktop process.

## Desktop upgrade

1. Choose a published release for your OS/architecture. Review its changelog and
   compatibility notes. Check `SHA256SUMS`, GitHub attestation and the platform
   signature. For Windows check Authenticode; on Mac check Developer ID/Gatekeeper.
2. Stop the running app (tray Exit or terminal Ctrl+C). Download a full backup
   from Settings and validate recovery, or use `application-tracker-backup backup
   --output /new/backup-directory` while the app is stopped. Keep backups outside
   the application data directory and retain the old installer/image digest.
3. On Windows run the user-scoped installer; it detects files held by a running
   process and offers closure. On Linux install the `.deb` with the package
   manager; running the app needs no root. On macOS replace the app from the DMG
   while it is stopped. Uninstall removes program files, preserving user data.
4. Start with the same data directory. Verify health, records, documents and
   background work. A changed database schema may make binary-only downgrade
   unsafe. Never assume replacing the executable reverses a migration.

To recover, stop the new version and use the old version's matching verified
pre-upgrade backup in a **new empty** directory:

```sh
ApplicationTracker --restore-backup /path/to/backup.zip --data-dir /new/workspace
ApplicationTracker --data-dir /new/workspace
```

Directory backups can also use `application-tracker-backup restore --source
/path/to/backup --data-dir /new/workspace`. Keep the failed workspace intact for
review. Restore invalidates provider/session bindings; reconnect explicitly.

## Container/hosted upgrades

One writable SQLite workspace per volume, with exactly one writer. Hosting and
reminders are optional and independent of phone-to-Drive sync. Upgrades require
the workspace owner's approval; GitHub registry promotion alone is not deployment.

Stop the writer, create and validate a database/document backup, retain the old
image digest, pull the approved `ghcr.io/kesdog/application_tracker@sha256:...`,
and restart on the existing volume. Check `/api/health` and workspace records.
For a failed migration restore the matching backup into a new volume with its old
image digest. Never run `docker compose down -v` as an upgrade or rollback step.

## Phone compatibility

Compact sync v1 is independent of the application version. Python and browser
clients accept v1 and reject unsupported protocol versions before importing
mutations. Keep queued edits and recovery material when an incompatible peer is
reported; do not clear storage to suppress an error. The offline/cross-language
tests cover this window; widen it with explicit fixtures before changing protocol.

PWA shell deployment changes caches, not IndexedDB. Reconnect Google and sync
manually after token expiry. Device installation, suspension, offline edits,
conflict review and same-account convergence remain release acceptance checks.
Native store rollback, if introduced later, must use staged repaired builds and
recovery compatible with local data, not an automatic data-format downgrade.
