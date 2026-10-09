# Hosted workspace and phone access

This setup supplies a single-workspace password, authenticated browser sessions, an installable phone shell, an HTTPS reverse proxy, portable backups, and optional Web Push. The base stack works without push configuration; the optional setup below enables phone reminders. It does not send emails or wake an AI agent.

The current local installation stays on loopback with no login. Hosting has not been provisioned. Docker is unavailable on the development machine, so the container stack requires the server checks below before going live.

## Server prerequisites

Use one always-on Linux server with Docker Engine and Compose v2, a persistent disk, a domain whose DNS points to that server, and inbound TCP 80/443 (UDP 443 is optional). Keep SSH access restricted. Do not expose port 8000 or the separate MCP server. Run one tracker instance against its SQLite volume; this is not a multi-user or horizontally scaled service.

The Compose stack puts Caddy and the tracker on a private bridge. Caddy provides [automatic HTTPS](https://caddyserver.com/docs/automatic-https), while the tracker accepts proxy headers only from that bridge. If `172.30.86.0/24` conflicts with another network, change both the network subnet and `APP_TRUSTED_PROXY_IPS` in `compose.yaml`. Do not replace the trusted range with `*`.

## First installation

Run these Bash commands from the repository root on the server. Set `TRACKER_DOMAIN` in the copied file to the actual hostname, without a scheme, port, or path.

```bash
cp deploy/hosted.env.example deploy/hosted.env
mkdir -m 700 -p deploy/secrets
docker build -t application-tracker:hosted .
docker run --rm -it --user "$(id -u):$(id -g)" \
  -v "$PWD/deploy/secrets:/secrets" application-tracker:hosted \
  python -m app.human_auth --output /secrets/password.hash
sudo chown 10001:10001 deploy/secrets/password.hash
sudo chmod 400 deploy/secrets/password.hash
docker compose --env-file deploy/hosted.env config --quiet
docker compose --env-file deploy/hosted.env up -d --no-build
docker compose --env-file deploy/hosted.env ps
docker compose --env-file deploy/hosted.env logs --tail 100 tracker caddy
```

The password prompt requires at least 14 characters and confirmation. Store the password in your password manager. Only a salted scrypt hash goes into the file; the command never prints the password or hash. Local Compose secrets retain host file permissions, so ownership `10001` lets the non-root tracker read the file. Keep `deploy/hosted.env`, the secret, backups and data out of version control. Do not use `docker compose down -v`: it deletes persistent volumes.

Open `https://YOUR_DOMAIN/#/followups`. Before signing in, check that the follow-up queue, exports, files, settings, and `/api/events` cannot be read. After signing in, edit a disposable application, refresh, download a test document, then sign out and confirm the workspace closes. Check for console/CSP errors and verify certificate renewal and reboot recovery on the actual server.

Browser sessions use Secure, HttpOnly, SameSite cookies, hashed database tokens, an eight-hour expiry, and origin/CSRF checks on writes. Agent bearer tokens authorize only their existing agent operations. Changing the workspace password invalidates existing sessions after restarting the tracker. The login has persisted per-address and workspace limits. These choices follow [OWASP session guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), [CSRF guidance](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html), and [password storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

## Backups and updates

Stop the tracker before making a complete backup, so uploaded documents and database references cannot change during the copy. Caddy may remain running and will show an unavailable workspace during maintenance. Each output directory must be new; the backup command refuses to overwrite it. It uses SQLite's backup API, checks database integrity, and includes uploaded documents and metadata. Secrets and logs are excluded.

```bash
mkdir -m 700 -p backups
docker compose --env-file deploy/hosted.env stop tracker
docker compose --env-file deploy/hosted.env run --rm --no-deps --user 0 \
  -v "$PWD/backups:/backups" tracker \
  python -m app.backup backup --output /backups/2026-10-09-before-update
docker compose --env-file deploy/hosted.env build tracker
docker compose --env-file deploy/hosted.env up -d --no-build
```

Choose a fresh backup name each time. If backup fails, preserve its partial directory, investigate, and restart the current version if needed; do not treat it as a complete backup. Keep an encrypted off-server copy and exercise restoration periodically. Updates apply schema migrations on startup; restore a pre-update backup together with its matching code/image for rollback.

## Restore or migrate from the PC

On Windows, stop the local tracker and create a full backup with:

```powershell
.\.venv\Scripts\python.exe -m app.backup backup --output .\backups\before-hosting
```

Restart the PC app if it is still your active workspace. Transfer the whole backup directory securely to the server. After switching to hosting, use the hosted workspace as the authoritative copy; two separate databases do not synchronize.

Restore only to a new, empty data volume. For a migration, create `compose.restore.yaml` with the following temporary override, choosing a new volume name each time:

```yaml
services:
  tracker:
    volumes:
      - tracker-restored:/data
volumes:
  tracker-restored:
```

Stop the tracker, then restore. Compose merges volumes by container target, replacing `/data` with the new volume while preserving the old volume.

```bash
docker compose --env-file deploy/hosted.env stop tracker
docker compose --env-file deploy/hosted.env -f compose.yaml -f compose.restore.yaml \
  run --rm --no-deps --user 0 -v "$PWD/backups:/backups:ro" tracker \
  python -m app.backup restore --source /backups/before-hosting --data-dir /data
docker compose --env-file deploy/hosted.env -f compose.yaml -f compose.restore.yaml \
  run --rm --no-deps --user 0 tracker chown -R 10001:10001 /data
docker compose --env-file deploy/hosted.env -f compose.yaml -f compose.restore.yaml up -d --no-build
```

Keep using the override on subsequent commands until the selected volume is made permanent in Compose. Verify application/follow-up counts and document downloads before retiring the old workspace. Restore checks the database checksum, refuses nonempty destinations and symlinks, relocates stored document paths across Windows/Linux, and clears browser sessions and phone registrations. If restoration fails, preserve the original backup and retry with a fresh destination after resolving the error. Existing data is never overwritten. Enable phone devices again after restoration.

For password rotation, generate a new secret into a different filename, set its ownership/permissions as above, stop the tracker, replace the configured secret file, and recreate the tracker container. Verify the old password and sessions are rejected. The tracker reads the hash only at startup.

## Phone installation and acceptance

On the actual HTTPS workspace, sign in from Safari on iPhone/iPad and use Share → Add to Home Screen. On Android, use the browser's Install app/Add to Home screen menu or the installation button in Settings when available. The installed app starts in Follow-ups and preserves message deep links through login.

The service worker caches only public icons and offline guidance, following the [PWA service worker model](https://web.dev/learn/pwa/service-workers). It does not cache private APIs or application records. Reconnect and sign in to work with your data. Installing the app does not request notification permission; enabling a device is a separate explicit action.

Before calling this deployment complete, verify on an iPhone and an Android phone: installation, sign-in, resume after closing the app, follow-up deep links, copy/paste into a mail client, sign-out, expired sessions, and offline/reconnect behavior. Desktop browser checks at a phone-sized viewport cannot establish real-device behavior. Actual background notification checks are still required.

## Optional phone notifications

Use a stable P-256 VAPID secret and an administrator contact email. The app uses [pywebpush](https://github.com/web-push-libs/pywebpush) for standard encrypted Web Push; browser/OS push providers remain necessary. BSM and an application message broker are not required.

After building the current image, generate the secret once. Set `TRACKER_PUSH_CONTACT=mailto:YOUR_ADMIN_EMAIL` in `deploy/hosted.env`.

```bash
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/deploy/secrets:/secrets" application-tracker:hosted \
  python -m app.push_keys --output /secrets/vapid.pem
sudo chown 10001:10001 deploy/secrets/vapid.pem
sudo chmod 400 deploy/secrets/vapid.pem
docker compose --env-file deploy/hosted.env -f compose.yaml -f compose.push.yaml config --quiet
docker compose --env-file deploy/hosted.env -f compose.yaml -f compose.push.yaml up -d --no-build
```

Keep using `compose.push.yaml` on later Compose operations, together with any restore override. Back up this secret separately from workspace backups and keep it stable across redeployments. Regenerating it invalidates old browser subscriptions; devices must enable notifications again. The optional overlay can be removed to stop sending without affecting the manual queue.

Open Settings → Phone notifications on the target phone, name the device, and tap Enable notifications. [iPhone/iPad Web Push](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/) requires a Home Screen web app on supported iOS/iPadOS versions, with permission requested from a user action. The UI feature-detects support and explains denial/unavailability. No permission request or subscription is made on page load. Up to 20 devices may be registered; removal stops new server deliveries. Signing out closes private browser access but leaves separately opted-in generic reminders enabled.

Tap Test notification, close the app, and wait for the notification. The worker scans every 30 seconds. Check notification status afterward: PENDING/RETRY means queued work; ACCEPTED means the push service accepted it, not proof the phone displayed it. FAILED explains a generic failure without exposing endpoint credentials. Tests bypass quiet hours and are limited to one per minute per device.

General · Follow-ups → Reminder preferences controls quiet hours and daily digest. Digest is enabled by default and batches newly available notices once per device per local day at or after the saved reminder time. Without digest, newly available notices are grouped per scan. Existing due work is grouped when a device is enabled or the server returns after downtime. An ordinary notice is not repeatedly sent after acceptance; the in-app queue remains the source of current work. A single-item notification links to the exact message; grouped reminders link to the queue. Opening or dismissing a phone notification never records sending or dismisses in-app notices.

The worker rechecks current job/message state before delivery. Sending, archiving, snoozing, pausing, closing/deleting a job, dismissing in-app notices, or disabling scheduled notices suppresses/defer pending reminders. Retryable timeouts, 429 and server errors use bounded exponential delays and Retry-After; six failed attempts end in FAILED. Invalid/expired subscriptions (404/410) become inactive. Leases recover interrupted work after two minutes. A crash after network acceptance but before recording it may replay a delivery; a stable provider topic and notification tag limit visible duplication, but exactly-once delivery cannot be guaranteed. Messages expire from the outbox after seven days and from the push provider after one hour; phones may suppress or delay notifications independently.

Subscription endpoints and encryption keys are confidential workspace data. APIs expose device labels/status, not endpoint credentials. The sender accepts only HTTPS endpoints from supported Chrome, Firefox, Apple and Windows browser providers, disables redirects, and avoids provider exception text in logs. Keep backups private. Removing a device or restoring a workspace does not recall notifications already delivered to its OS.

Real-device acceptance remains pending until the HTTPS server is deployed. On both target phones verify: permission denial, app-closed delivery, exact-message taps through expired sign-in, quiet-hour deferral, digest grouping, reconnect catch-up, revoked subscriptions and device removal. Use Download calendar reminder in a follow-up as an optional fallback; importing or dismissing the event never changes the message state. Re-export after changing the due date and remove stale imported calendar events yourself.
