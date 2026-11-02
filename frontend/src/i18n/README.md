# Interface languages

English source messages are the catalog keys; `fr.json` supplies French. Call
`t('Message with {p0}', { p0: value })` for interface text. Use `messageText` for
server-provided system labels and `errorText` for error diagnostics. Never pass
authored subjects, email bodies, company names, notes or documents to a translator.
Vue renders translations as text; do not use `v-html` for catalog content.

The locale is reactive, saved per browser and applied to document language, dates,
native validation and PrimeVue's component locale. Use getters or computed values
for shared option labels so they update when language changes. Canonical API enum
values stay unchanged. Literal catalog coverage and interpolation parity are
checked in `tests/shell/i18n.test.ts`.

To add another locale, add its catalog and PrimeVue locale, extend `Locale` and
`languages` in `index.ts`, and register it in the catalog selection and persistence
validation. Add tests for switching, dates and validation. Follow-up email languages
are a separate backend contract in `followup_templates.LOCALIZED_TEMPLATES`.

Settings → Appearance includes separate interface and default email language
controls. An application can set a different preference for future emails; each
follow-up can independently choose its active email language. Interface changes
never change either email preference. AI requests explicitly use the email
preference independently from the interface and the language of incoming mail.

Follow-ups retain exact local subject/body versions, instructions and template
context in `followup_message_versions`. Switching a language uses its most recently
used saved version, or generates a standard message if no version exists. The
history also restores specific earlier edits. A switch preserves the previous
content, clears approval, retains recipients and schedules, and requires review.
Bulk default-language updates skip explicit application/message preferences.
Sent and archived messages remain available for preview but cannot be switched.
Phone-only and remotely stored content are excluded from email switches.

All human edits, agent revisions, template replacements, legacy local drafting,
undo and consolidation preserve message versions. Migration 0029 saves existing
messages and recovers earlier text retained in the audit history. Portable database
backups include versions; compact Drive sync continues to exclude message content.
Versions never trigger provider calls or mailbox writes. New-language generation
uses standard templates; it does not translate arbitrary prose automatically.
