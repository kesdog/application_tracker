#!/usr/bin/env bash
# Explicit promotion of an already verified public ZIP to a configured HTTPS host.
set -euo pipefail
: "${PHONE_SSH_HOST:?Configure the deployment SSH host}"
: "${PHONE_DEPLOY_ROOT:?Configure an isolated deployment root}"
archive=$1
version=$2
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-(alpha|beta|rc)\.[0-9]+)?$ ]] || exit 1
[[ "$PHONE_SSH_HOST" =~ ^[A-Za-z0-9_][A-Za-z0-9_.@-]*$ ]] || exit 1
[[ "$PHONE_DEPLOY_ROOT" =~ ^/[A-Za-z0-9_./-]+$ && "$PHONE_DEPLOY_ROOT" != / && "$PHONE_DEPLOY_ROOT" != *..* ]] || exit 1
# The remote root must be dedicated to static releases, never a workspace mount.
ssh "$PHONE_SSH_HOST" bash -s -- "$PHONE_DEPLOY_ROOT" "$version" <<'REMOTE'
set -euo pipefail
root=$1
version=$2
test -d "$root/releases"
test ! -e "$root/releases/$version"
mkdir "$root/releases/$version"
REMOTE
scp "$archive" "$PHONE_SSH_HOST:$PHONE_DEPLOY_ROOT/releases/$version/public.zip"
ssh "$PHONE_SSH_HOST" bash -s -- "$PHONE_DEPLOY_ROOT" "$version" <<'REMOTE'
set -euo pipefail
root=$1
version=$2
python3 - "$root/releases/$version" <<'PY'
import pathlib, re, sys, zipfile
root = pathlib.Path(sys.argv[1])
fixed = {'index.html', 'DEPLOY.txt', '_headers', 'phone/index.html', 'phone/sw.js', 'phone/manifest.webmanifest', 'icons/icon-192.png', 'icons/icon-512.png'}
with zipfile.ZipFile(root / 'public.zip') as archive:
    names = archive.namelist()
    assert fixed.issubset(names) and len(names) == len(set(names))
    assert all(name in fixed or re.fullmatch(r'assets/[A-Za-z0-9_.-]+\.(?:js|css|woff2?|ttf|svg|png|jpe?g|webp|ico)', name) for name in names)
    assert sum(item.file_size for item in archive.infolist()) < 50 * 1024 * 1024
    archive.extractall(root / 'dist')
PY
test ! -e "$root/current" || test -L "$root/current"
ln -s "$root/releases/$version/dist" "$root/current-$version"
# GNU mv atomically replaces the entry symlink; retain every prior release.
mv -Tf "$root/current-$version" "$root/current"
REMOTE
