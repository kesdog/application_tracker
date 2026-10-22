# Changelog

## 0.12.0 — Release foundations

- Add reviewed, bounded CSV/XLSX import with column mapping, row validation, duplicate choices and transactional replay receipts.
- Add persistent account-scoped email review with link/create/dismiss actions, explicit employer-reply recording and reminder decisions.
- Add duplicate consolidation that retains original history and avoids reparenting synchronized entity IDs.
- Add Trash restoration, full backup downloads, isolated ZIP recovery verification and packaged Windows recovery commands.
- Verify document checksums and close SQLite backup handles promptly on Windows.
- Prevent spreadsheet formula interpretation, limit document uploads, catch up posting checks after restart and discard checks for changed source URLs.
- Surface application deadlines and other upcoming work on the dashboard.
- Add an optional encrypted hosted credential vault, `.env` setup and a Google Compose overlay. Local OS-vault behavior remains the default.
- Include the pending desktop sync, onboarding and UI improvements in the reviewed release baseline.
- Add hashed runtime/development locks, pinned container bases and a paired Linux/Windows CI candidate gate.
- Give non-editable container installs an explicit migration/UI resource root, verified by the installed-image smoke check.
- Exercise installed artifacts and the Windows executable, including startup, migrations, persistence, uploads and backup/recovery.

Live Google/HTTPS/physical-phone acceptance, the independent offline phone replica, stable publication/signing, and opt-in upgrade installation remain gated work. This release does not claim those capabilities complete.
