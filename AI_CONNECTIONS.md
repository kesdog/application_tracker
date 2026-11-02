# Optional AI account connections

Onboarding → Connect accounts and Settings → Connections offer the same Google,
ChatGPT and Claude setup. Every connection is optional. The guide resumes its
step after a provider redirect, and Skip for now keeps local tracking available.
Hosted workspace access still uses the workspace password or configured Google
sign-in. Linking an AI account does not issue a workspace session or grant agent
permissions.

## ChatGPT

Direct linking uses OpenAI's supported open-source registration flow. Run the
local installation on `http://127.0.0.1:<APP_PORT>`; the backend must listen there
before beginning authorization. The callback is
`/api/connections/ai/chatgpt/callback`. This direct flow is intentionally unavailable
in hosted mode; hosted users can use the existing MCP connector setup instead.

The tracker registers as **Application Tracker**, persists its own stable host
identifier, and uses `dynamic_agent_client` only for a new registration. Each
verified account retains its issued client ID. Returning authorization reuses that
registration; users can choose a saved registration or add another account.

Authorization uses browser-bound, single-use state, a nonce and PKCE. ID tokens
are verified against OpenAI's JWKS, including signature, issuer, audience, expiry
and nonce. A changed account identity cannot replace an existing registration.
Account identity and permission to use the ChatGPT plan are displayed separately.
Tokens rotate on refresh and stay in the local installation's secure store.

Disconnect attempts to revoke the active renewable session, clears its local
tokens, and retains the account/client mapping for later sign-in. If remote
revocation cannot be confirmed, the UI says so and links to ChatGPT usage settings.
Other saved accounts remain separate. Disconnect those individually if needed.

## Claude

Anthropic does not document a general third-party identity sign-in flow for this
tracker. The direct connection accepts a Claude Console API key, verifies it
against the Models API before saving it, and clears the input after submission.
API billing is separate from a Claude subscription. A subscription can instead be
used in Claude's own app with the existing tracker MCP connector.

## Verification and usage errors

Opening onboarding or Settings reads only saved connection status. It does not
start provider authorization, list models, or generate text automatically.
Refresh models explicitly retrieves the connected account's catalog. Test AI
access explicitly sends only `Reply with OK.` and consumes a small amount of
provider usage. It sends no application records and does not send email or change
follow-ups. AI account linking does not add automatic AI drafting.

ChatGPT tests use the public Responses API with `store=false` and `stream=true`.
Success requires `response.completed`; mid-stream failures and interrupted or
incomplete streams are errors. Usage-limit errors link to ChatGPT Settings →
Usage without guessing a reset time or silently switching billing or providers.
Claude credit/spending failures, temporary rate limits, denied permissions,
expired authorization, and provider outages have separate messages. A numeric
provider Retry-After value is displayed. Failures are not retried automatically.
Temporary failures and usage limits keep the saved connection.

Credentials are namespaced in the existing native credential store, or the
configured encrypted credential vault. ChatGPT tokens are used only in local
mode. API responses, browser storage and callback logs contain no provider tokens
or API keys; validation errors never echo submitted credentials.
For a native OS vault, only a small AES key is stored there: the larger OAuth
bundle is encrypted in the installation's credentials folder and replaced
atomically. This avoids Windows Credential Manager's credential-blob size limit.
The encrypted file is unusable without the original native key. Do not copy
ChatGPT credentials to a hosted runtime.

Run `python scripts/test.py --segment auth shell` while editing, then the full
gate before delivery. Offline fixtures cover OAuth replay/binding, real RSA
signature validation, account preservation, refresh rotation, disconnect,
secret redaction, usage errors and UI onboarding. Live consent, provider account
eligibility, real billing/usage and physical phone acceptance remain operator
checks; mocks do not establish these.

Official references checked 27 October 2026:

- [OpenAI registration and sign-in](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)
- [OpenAI account sessions and refresh](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions)
- [OpenAI models and inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference)
- [OpenAI usage errors and recovery](https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery)
- [Claude authentication options](https://support.claude.com/en/articles/13189465-log-in-to-your-claude-account)
- [Claude API errors](https://platform.claude.com/docs/en/api/errors)
