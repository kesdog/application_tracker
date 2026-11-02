# Changelog

## Unreleased

- Expand the reusable release gate to Windows, Linux and both macOS architectures,
  with native frozen-process, installer, migration/recovery and production phone
  package/offline-shell checks.
- Separate desktop server/UI adapters, use installed platform data directories,
  reject competing desktop workspace owners and occupied ports before startup.
- Add Windows user installers, Linux deb packaging, Mac DMGs, protected signing
  and notarization, coherent release hashes/provenance and draft-only publication.
- Add an approved, atomic public phone PWA deployment workflow and operator
  upgrade/restore guidance. Signing, hosting and real-device acceptance require
  owner configuration; native store apps and automatic updating remain later work.

## 0.13.0 — Phone sync, optional connections and localization

- Add an independent offline phone app with encrypted IndexedDB storage, direct Google Drive sync, compatibility probes and QR pairing from the desktop.
- Add public-only phone packaging and cross-language protocol, recovery and sync coverage.
- Keep Google, ChatGPT and Claude connections optional, with guided setup, secure credential storage and explicit account and usage controls.
- Add optional Google workspace sign-in while preserving local tracking without sign-in.
- Add persisted English/French interface settings, including hints, errors and accessible labels.
- Keep follow-up email language independent of interface language, with saved message versions and explicit review before using rewritten content.
- Improve mailbox scanning, evidence matching, deduplication and date boundaries, with review for ambiguous messages.
- Add pause and priority controls for recipient research, including rejection of results from revoked leases.
- Modernize shared PrimeVue controls, settings navigation, appearance and direct Gmail message links.

Offline checks cover synthetic providers and phone replicas. Live provider consent, production hosting, physical Android/iPhone behavior and signed upgrades require separate acceptance.

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
