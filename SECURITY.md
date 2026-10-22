# Security and support boundaries

Application Tracker currently operates one workspace, one logical agent/mailbox and one SQLite writer per instance. It is not a multi-tenant hosting service. Core local use requires no Google or AI account.

Keep `.env`, workspace databases, backups, credentials, sync recovery exports and deployment secrets out of Git and public issue attachments. Backups include private workspace information. A credential exposed in chat or source should be replaced through its provider; deleting the text does not revoke it.

For a security report, use GitHub's private vulnerability-reporting facility if it is enabled on the repository. Otherwise contact the repository owner privately to arrange a reporting channel before disclosing sensitive details. Do not include real tokens, private records or exploit data in a public issue.

The hosted deployment requires HTTPS, a workspace password, protected persistent storage and a configured secret store for optional Google access. See [deploy/README.md](deploy/README.md) and [RECOVERY.md](RECOVERY.md). Agent tokens authorize only their configured operations; mailbox drafts never send mail.

## Supported release policy

The current source and its matching packaged artifacts are the verified baseline. No automatic installation/upgrades are enabled. Do not assume cross-version sync compatibility or open a newer database with an older executable. A future stable update mechanism must verify artifacts, preserve a matching backup and provide the agreed Upgrade/Later/Skip choices before activation.
