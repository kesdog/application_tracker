# Workspace sign-in and provider connections

The login panel identifies Google, Claude and ChatGPT and adapts to desktop and
mobile. Local workspaces remain available without signing in. Hosted workspaces
retain password login and can enable Google Identity Services using the
[Google setup guide](GOOGLE_INTEGRATION.md#optional-google-workspace-sign-in).

Google is an account sign-in provider. Its standard GIS button is initialized
with the server's web client ID and a browser-bound nonce; its callback exchanges
the credential for a tracker session. If unavailable, the panel shows a setup
action and password fallback. Blocked scripts, expired attempts, invalid identities
and account restrictions display actionable errors and a retry control.

Onboarding and Settings → Connections expose Google, ChatGPT and Claude setup.
When Google has no registration yet, Connect Google opens an in-app
registration guide and credentials-file import. The imported credentials are saved
in the installation's secure vault and take effect without a backend restart.
Direct ChatGPT linking is available on a local loopback installation. Claude
can connect using a verified Console API key. Both also retain MCP setup links.

The hosted login panel's Claude and ChatGPT controls explain the available
connections after workspace login. They never request provider passwords, accept
API keys as workspace login, or create a tracker session. Sign in to the tracker
first and open Settings → Connections or Agent & system. A remote client needs
a supported, reachable endpoint and authentication; opening guidance does not
mean a connection has been established.

OpenAI now documents a direct open-source ChatGPT linking flow, implemented here
for local installations with the tracker's own dynamic registration. Hosted
identity-provider sign-in is a separate registration and is not configured here.
Claude connectors authorize access to the tracker; they are not a general Sign in
with Claude identity service. See [AI_CONNECTIONS.md](AI_CONNECTIONS.md) for
credential handling, usage-limit recovery and the live acceptance checklist.

Sources checked 2026-10-27:

- [Google GIS button and callback](https://developers.google.com/identity/gsi/web/guides/display-button)
- [Google origins, CSP and popup requirements](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid)
- [ChatGPT website sign-in and registration requirements](https://developers.openai.com/siwc/website)
- [Claude connector authentication](https://support.claude.com/en/articles/11176164-use-connectors-to-extend-claude-s-capabilities)

The ChatGPT logo is the official asset distributed with OpenAI's sign-in guide;
the Claude symbol is the [CC0 Wikimedia asset](https://commons.wikimedia.org/wiki/File:Claude_AI_symbol.svg)
referenced in the requested design. Both are served locally.

Verification: run `python scripts/test.py --segment auth shell` during development
and `python scripts/test.py --full` before delivery. Test live Google using a real
registered web client and allowed identity on the configured HTTPS origin. Verify
the popup, cancellation, restricted-account rejection, reload and logout on desktop
and mobile. Browser mocks and offline token fixtures do not establish live Google
consent or physical-device acceptance.
