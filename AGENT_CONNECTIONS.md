# Connect ChatGPT/Codex and Claude to one tracker agent

Generate **one** token in Settings and configure its **one** set of permissions.
Both clients use it concurrently, through the same MCP tools and `agent_ops`.
No OpenAI/Anthropic inference keys or extra Gmail consent are required by the
tracker. A product login is separate from tracker authorization and Google consent.
Regenerating this token immediately revokes every client using it. Disconnecting
one client does not change the other, the permission profile or the Google account.

## Local Codex (stdio)

Keep the plaintext token in the launching process's protected environment, outside
source control, shell history, model prompts and settings exports. Both processes
must use the same `APP_DATA_DIR` and OS account (to reach the native Google store).
Use an absolute executable path if it is not on PATH. A Codex configuration template:

```toml
[mcp_servers.application_tracker]
command = "D:\\APP_TRCKR\\.venv\\Scripts\\application-tracker-mcp.exe"
cwd = "D:\\APP_TRCKR"
env_vars = ["APPLICATION_TRACKER_AGENT_TOKEN", "APP_DATA_DIR"]
```

The example contains no secret. Verify your installed client's configuration and
call `get_tracker_info` before granting writes.

## Local Claude Code (stdio)

Launch Claude with the same `APPLICATION_TRACKER_AGENT_TOKEN` and `APP_DATA_DIR`
inherited in its environment. Then register the local command:

```powershell
claude mcp add --transport stdio application-tracker -- D:\APP_TRCKR\.venv\Scripts\application-tracker-mcp.exe
```

For clients with JSON MCP configuration, the token-free command template is:

```json
{
  "mcpServers": {
    "application-tracker": {
      "command": "D:\\APP_TRCKR\\.venv\\Scripts\\application-tracker-mcp.exe",
      "args": []
    }
  }
}
```

Environment inheritance varies by desktop launcher. Confirm that it forwards the
token securely; if it does not, use the product's protected configuration facility.
Never commit a populated `env` block containing a real token.

## HTTP and cloud clients

Set `MCP_TRANSPORT=streamable-http` and start `application-tracker-mcp`. Its default
address is `http://127.0.0.1:8001/mcp`; it requires the same bearer token on requests.
Local Codex can use:

```toml
[mcp_servers.application_tracker]
url = "http://127.0.0.1:8001/mcp"
bearer_token_env_var = "APPLICATION_TRACKER_AGENT_TOKEN"
```

ChatGPT can use a supported Secure MCP Tunnel or a secured HTTPS endpoint. Tunnel
setup has its own credentials and environment requirements: keep them separate
from the tracker token. Verify how your tunnel forwards the tracker's required
bearer header before connecting it. A tunnel must never bypass tracker checks.

Claude's remote connection originates outside your laptop, so it requires a
reachable secured HTTPS gateway. Validate your particular client's authorization
flow and read/write capabilities. An OAuth-only client cannot connect directly to
this bearer-only server; no speculative OAuth adapter has been added. A future
tested adapter must map back to `agent_credentials.id=1` and its existing six
permissions. Neither cloud client can reach a laptop-only localhost address merely
because Google is connected. Local stdio and HTTP are separate supported transports
of the same server, rather than model-specific agents.

Real consumer ChatGPT/Claude account, tunnel, plan and workspace compatibility is
**unverified** until the following checks pass in that exact environment. If writes
are unavailable, surface that limitation and use a supported local client. Do not
present a failed write as a successful fallback.

## Conflicts and retries

Application reads include `revision`; agent updates require
`changes.expected_revision`. First write wins a matching revision, stale writes
return HTTP 409 / MCP `REVISION_CONFLICT`, including current and proposed values.
Retain your proposed edit, read the latest record and explicitly review/reapply
safe fields. Status/outcome, delete/edit and follow-up sent conflicts require human
resolution. No automatic last-write-wins or field merge is performed. Existing
legacy human PATCH clients can omit the optional precondition; the current UI
supplies it. Agent edits cannot omit it.

Mutating REST calls may include a stable `request_id` UUID (also used as the retry
key), or an `idempotency_key`. Retries must keep identical arguments. Mailbox draft
operations use durable receipts; uncertain external writes need reconciliation.
Timeline correlation uses request UUIDs and optional client labels
`chatgpt`/`claude`/`codex`/`unknown`. Labels are self-reported, explicitly unverified,
and never affect permissions. A shared token identifies the one tracker principal;
it cannot authenticate which model used it.

## Real two-client acceptance checklist

1. Connect both clients with one token. Read the same application list. Disable
   read, then edit; verify each relevant operation is blocked for both immediately.
2. Create an application in one; read it in the other. Reverse the roles.
3. Read one revision in both, submit different edits concurrently; expect exactly
   one acceptance and one conflict. Review/reapply safe non-conflicting fields.
4. Draft through both clients against the same Google account; retry identical
   operation IDs and confirm no duplicate. Confirm nothing is sent automatically.
5. Rotate the tracker token; both lose access, Google remains connected. Reconfigure
   both with the replacement. Disconnect one; verify the other continues.
6. Stop Google/network connectivity and verify offline tracking/local draft fallback.

Official references checked during implementation:
[Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli),
[OpenAI Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels),
[Claude Code MCP](https://code.claude.com/docs/en/mcp).
