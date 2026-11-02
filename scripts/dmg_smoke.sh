#!/usr/bin/env bash
set -euo pipefail
mountpoint=$(mktemp -d "${RUNNER_TEMP:-/tmp}/tracker-dmg-XXXXXXXX")
cleanup() {
  hdiutil detach "$mountpoint" || true
  rmdir "$mountpoint" || true
}
trap cleanup EXIT
hdiutil attach "$1" -mountpoint "$mountpoint" -nobrowse -readonly
test -d "$mountpoint/ApplicationTracker.app"
python scripts/desktop_smoke.py "$mountpoint/ApplicationTracker.app/Contents/MacOS/ApplicationTracker" --version "$2"
