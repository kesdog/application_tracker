# Shared agent and Google integration implementation

The approved revised plan preserves one agent credential (id 1), six permissions,
one Google mailbox, offline tracking, and explicit drafts without sending.

1. Add a populated-database migration for Google metadata, application revisions,
   payload-bound retries and durable mailbox draft receipts.
2. Add fail-closed OS keyring storage, browser OAuth with PKCE/state/nonce and
   verified Google identity, independently selected scopes and reconnect/disconnect.
3. Wire the same Gmail provider into REST, stdio and HTTP MCP; add bounded message
   lookup/search and an encrypted Drive appData test with a user-supplied key.
4. Reject stale application edits, retain both current and proposed values in
   conflicts, retain follow-up revision checks, and prevent uncertain draft retries.
5. Keep one permissions/token panel; add Google controls and client instructions.
6. Validate mocked OAuth/provider failures, simultaneous clients, migrations,
   permissions, token rotation, local fallback, frontend behavior and full gate.

Dependencies: keyring (native safe backends only), google-auth with requests
(signed ID-token validation), cryptography (AES-GCM Drive test), existing httpx.
Google Cloud OAuth credentials and API enablement are operator prerequisites.

Live acceptance requires a user Google consent and real authenticated clients.
Do not advertise consumer remote connectivity, OAuth bridges, or cross-device
sync as verified until tested in the target environment. See GOOGLE_INTEGRATION.md
and AGENT_CONNECTIONS.md for setup, checks and recorded limitations.

## Validation completed

- Full pre-push gate (20 October 2026), run against the exact staged snapshot:
  462 backend/tooling tests and 112 frontend tests passed. The operator opt-in
  Google smoke was skipped, as requested. Production build/type-check and
  dependency consistency passed.
- Final request-correlation/hosted-auth checks: 13 passed. Recipient revision
  preservation across invalidation: 10 focused frontend cases passed; the final
  production build also passed.
- Official PrimeVue MCP: 66 component usages checked, none need review.
- Browser verification used a separate workspace under `.run/` on port 8010:
  one token card, one six-permission panel, both client instructions, disabled
  unconfigured Google controls, and a working refresh action. Screenshot:
  `output/playwright/google-settings.png`. A PrimeUI license warning is visible
  in that preview; no license configuration was changed.
- Real consent, real consumer-client/tunnel flows and packaged desktop execution
  remain unverified. The user selected mocked tests and a live-test checklist.
- Legacy human PATCH callers can omit application preconditions for compatibility;
  agent edits require them and the current UI sends them. No automatic merge is
  performed. Uncertain external drafts require explicit manual reconciliation.
