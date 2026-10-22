# Backup and recovery

Use **Settings → Data & recovery → Back up and verify recovery → Download full backup**. The ZIP contains the SQLite snapshot, uploaded documents and checksum metadata. It is private and is not encrypted by this download; keep it in protected storage and keep an off-device copy. Ordinary CSV/XLSX exports are application summaries, not complete backups.

Uploads managed by the tracker are immutable and committed after their file is written. The download takes a SQLite snapshot before copying those files. Stop the app before external programs modify its documents directory. Google credentials, hosted password/VAPID secrets and sync recovery keys are deliberately separate; save their recovery material securely. Reconnect Google and re-enable notification devices after restoration.

Before relying on a backup, upload its ZIP to **Verify a backup ZIP**. The app restores it into a temporary, isolated workspace and reports the application count. It never replaces the open workspace. Document checksums are verified for new backups; older version-1 backups retain their original validation rules. Verification accepts up to 100 MiB compressed and 1 GiB expanded. Keep the original file if verification fails.

## Windows app

Exit the tracker from its tray before switching workspaces. Keep the old installation and data directory. In PowerShell, restore into a **new empty directory**:

```powershell
& .\ApplicationTracker.exe --restore-backup 'C:\Backups\application-tracker-backup.zip' --data-dir 'C:\Tracker-Recovered'
```

The restored directory contains `recovery-success.txt` after success. If recovery fails, read `startup-error.log` in the selected directory and keep the original backup. Recovery does not overwrite an existing workspace. Start the recovered copy with:

```powershell
& .\ApplicationTracker.exe --data-dir 'C:\Tracker-Recovered'
```

Use that argument in your shortcut for subsequent launches. Verify record counts, documents, follow-ups and settings before retiring the old workspace. Keep reminders paused while reviewing restored/merged records.

## Source or hosted installations

The command accepts a downloaded ZIP or an extracted backup directory:

```powershell
.\.venv\Scripts\python.exe -m app.backup restore --source .\application-tracker-backup.zip --data-dir .\data-recovered
```

Point `APP_DATA_DIR` in your private `.env` at the recovered directory and restart. Hosted operators should follow [deploy/README.md](deploy/README.md) for volume ownership, secret setup and switching to a new volume. Retain the old volume until the recovered copy is verified.

An older executable must not open a newer incompatible schema. For rollback, restore the pre-update backup together with its matching application version. A backup made before later writes does not contain those writes: preserve and reconcile them before switching back.
