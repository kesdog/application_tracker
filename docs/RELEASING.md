# Cross-platform releases

The required `release-gate` check calls `ci.yml` on every PR and main push. It
runs the hashed Python/frozen pnpm environment, full offline suite, installed
distribution smoke and native PyInstaller smoke on Windows 2022, Ubuntu 24.04,
macOS 15 Intel and macOS 15 Apple silicon. Phone packaging and Chromium/WebKit
offline shell checks run separately. A failed, cancelled or skipped dependency
fails the aggregate. PR jobs have read-only tokens and receive no signing secrets.

The Python 3.13.17, Node 24.19.0 and pnpm 11.19.0 pins live in
`.github/actions/setup/action.yml`. Python locks include platform markers and
hashes; do not drop `--require-hashes` to work around a missing Mac dependency.
Pip caches follow the lock hash. Review action SHA changes like dependency updates.

## Repository setup (owner action)

Configure branch protection for the existing **Release gate / release-gate**
check. Do not require a matrix job which can change when platforms are added.
Protect `v*` tags with a repository ruleset restricting creation, updates and
deletion to release owners. Require annotated tags; signed tags are preferred.
The workflow rejects tags outside main's history and mismatched versions.

Create the following GitHub environments **before enabling releases**. Restrict
them to protected version tags (or main for phone deployment), add required human
reviewers and prevent self-approval. A YAML `environment:` name alone does not
configure approval protection. Credentials belong only in these environments,
never repository-level secrets available to other workflows or in Git.

| Environment | Secrets | Variables |
| --- | --- | --- |
| `release-signing` | `WINDOWS_CERTIFICATE_PFX` (base64 PFX), `WINDOWS_CERTIFICATE_PASSWORD`; `MACOS_CERTIFICATE_P12` (base64 Developer ID Application P12), `MACOS_CERTIFICATE_PASSWORD`, `MACOS_SIGN_IDENTITY`; `APPLE_API_KEY_P8` (PEM), `APPLE_API_KEY_ID`, `APPLE_API_ISSUER` | `WINDOWS_TIMESTAMP_URL` (certificate provider's RFC 3161 service) |
| `release-publish` | none; scoped GitHub token publishes | none |
| `phone-production` | `PHONE_SSH_KEY` (dedicated deployment key), `PHONE_SSH_KNOWN_HOSTS` (independently verified host keys) | `PHONE_SSH_HOST` (`user@host`), `PHONE_DEPLOY_ROOT` (dedicated absolute directory), `PHONE_PUBLIC_URL` (HTTPS origin, no trailing slash) |

Windows runners need Inno Setup 6 and Windows SDK `signtool`. Native Linux
packages target Ubuntu 24.04 x64 or compatible newer glibc, not arbitrary Linux
distributions. Mac builds run independently per architecture. In routine CI their
DMGs and Windows installers are labelled `unsigned`; they are test candidates.
The Linux desktop launcher opens the browser and runs in a terminal until Ctrl+C.
Windows/macOS use a tray; `--headless` offers a browser/CLI fallback. Smoke tests
exercise the process without requiring a graphical session.

## Prepare and promote a release

1. Update `pyproject.toml`, `backend/app/__init__.py`, `frontend/package.json`,
   both public web manifests and `packaging/application.json` to the same version.
   Update `CHANGELOG.md`. Use `X.Y.Z` or `X.Y.Z-alpha.N`, `-beta.N`, `-rc.N`.
   Compact sync has its own version; application version bumps do not bump it.
2. Run `python scripts/release_check.py`, `scripts/test.py --full` using the
   project venv, then merge to main. Review the four native CI candidates.
3. Create a signed (`git tag -s vX.Y.Z`) or protected annotated
   (`git tag -a vX.Y.Z`) tag at that main commit and push the tag. Do not move or
   reuse a version tag. Manual release dispatch also requires selecting the tag.
4. `release.yml` reruns the entire reusable gate at the tag commit. Only after it
   succeeds do protected jobs build and sign the Windows app/installer, notarize
   and staple both Mac apps/DMGs, and build the Linux `.deb`, OCI image and phone
   public ZIP. Missing secrets fail visibly; there is no unsigned stable fallback.
5. Approve registry promotion. GHCR receives
   `ghcr.io/kesdog/application_tracker:X.Y.Z`; the workflow refuses an existing
   version. `ApplicationTracker-oci.json` records its immutable digest. No `latest`
   tag is updated. Publishing an image does not deploy a workspace.
6. The workflow verifies platform completeness and matching build receipts,
   generates `release-manifest.json` and `SHA256SUMS`, attests the assets, and
   creates a **draft** GitHub Release. Prerelease tags get the prerelease flag.
   Review notes, signatures and acceptance evidence, then publish manually.
   Upload failures can leave an image published and no Release; report that state,
   do not overwrite the image to conceal it. Resolve failed promotion explicitly.

Checksums detect corruption. Verify GitHub provenance as well, for example:

```sh
gh attestation verify ApplicationTracker-phone.zip \
  --repo kesdog/application_tracker \
  --signer-workflow kesdog/application_tracker/.github/workflows/release.yml \
  --source-ref refs/tags/vX.Y.Z --deny-self-hosted-runners
```

## Public phone PWA deployment

PWA distribution works without native app-store projects. Choose a dedicated
public HTTPS **origin**: assets and the worker use `/phone/`, `/assets/`, `/icons/`
at the origin root. A repository-subpath host requires additional routing and is
not the supplied deployment target. Configure a separate Google Web OAuth client
with this origin in the desktop client's Google project; no client secret goes
in the ZIP. Users may supply the public client ID in advanced settings.

On a controlled Linux static host, provision a dedicated deployment user and
`PHONE_DEPLOY_ROOT/releases`, and configure HTTPS nginx using
`packaging/phone/nginx.conf`. Its root points to `PHONE_DEPLOY_ROOT/current`.
Only that deployment root should be writable by the SSH key. The host requires
Python 3, GNU `mv`, SSH and no tracker backend. Other CDNs can deploy the ZIP and
honor its `_headers`; configure equivalent CSP/cache rules when unsupported.

After publishing a Release, dispatch **Approve phone PWA deployment** from main
with its tag. The protected job verifies the published artifact's GitHub
attestation and tag, uploads only the public ZIP, validates members, extracts to
a new version directory, and atomically switches `current`. Old releases remain
available. It checks the deployed manifest version; a failed check leaves the
deployment failed for operator recovery. Roll back by atomically pointing
`current` to a retained version's `dist`; never clear browser IndexedDB.

Install on Android using the browser's Install/Add to Home Screen action. On
iPhone, use Safari → Share → Add to Home Screen. Pair from desktop, keep recovery
material separate, and test offline unlock and edits before relying on it.
The worker refreshes shell caches only; encrypted local data remains in IndexedDB.

## Acceptance and deliberately later work

CI evidence proves synthetic behavior, including old-database backup/restore,
cross-language sync vectors, process persistence, port/workspace collision
rejection, and production PWA shell/offline reload. It does not prove live
OAuth, graphical launch, Gatekeeper on a downloaded installer, physical-phone
storage retention or provider review. Record those checks per release on clean
Windows/Linux and both Mac architectures plus real Android and iPhone devices.
The first four-platform Actions run must pass before claiming Phase 1's exit.

AppImage, MSI, Linux arm64, a signed-manifest automatic update client and optional
Capacitor store tracks remain later enhancements. Desktop upgrades are manual and
opt-in today; see UPGRADING.md. No native Android/iOS binaries are advertised.
If adding Capacitor, wrap only the independent phone UI. Use a system-browser
OAuth/PKCE native Authorization adapter, separate client registrations, protected
store credentials and monotonically increasing Gradle/Xcode build numbers.
Do not reuse the browser popup flow in WKWebView or embed the Python server.
Play/TestFlight upload is not production store approval.

References: [GitHub runner labels](https://docs.github.com/en/actions/reference/runners/github-hosted-runners),
[reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows),
[PyInstaller native bundles](https://pyinstaller.org/en/stable/usage.html),
[Inno running-process handling](https://jrsoftware.org/ishelp/topic_setup_closeapplications.htm),
[Apple notarization](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution).
