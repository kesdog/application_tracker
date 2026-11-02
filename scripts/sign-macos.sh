#!/usr/bin/env bash
# Run only on a disposable protected macOS runner, after the exact tag gate.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${MACOS_CERTIFICATE_P12:?Missing Developer ID certificate}"
: "${MACOS_CERTIFICATE_PASSWORD:?Missing certificate password}"
: "${MACOS_SIGN_IDENTITY:?Missing Developer ID Application identity}"
: "${APPLE_API_KEY_P8:?Missing App Store Connect API key}"
: "${APPLE_API_KEY_ID:?Missing API key ID}"
: "${APPLE_API_ISSUER:?Missing API issuer}"
keychain="$RUNNER_TEMP/tracker-signing.keychain-db"
keychain_password=$(openssl rand -hex 32)
cert="$RUNNER_TEMP/tracker-signing.p12"
api_key="$RUNNER_TEMP/tracker-notary.p8"
cleanup() {
  security delete-keychain "$keychain" || true
  rm -f "$cert" "$api_key"
}
trap cleanup EXIT
printf '%s' "$MACOS_CERTIFICATE_P12" | base64 --decode > "$cert"
printf '%s' "$APPLE_API_KEY_P8" > "$api_key"
security create-keychain -p "$keychain_password" "$keychain"
security set-keychain-settings -lut 21600 "$keychain"
security unlock-keychain -p "$keychain_password" "$keychain"
security import "$cert" -P "$MACOS_CERTIFICATE_PASSWORD" -A -t cert -f pkcs12 -k "$keychain"
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$keychain_password" "$keychain"
security list-keychains -d user -s "$keychain" "$HOME/Library/Keychains/login.keychain-db"
python scripts/build_desktop.py
app=build/macos/ApplicationTracker.app
codesign --force --options runtime --timestamp --entitlements packaging/macos/entitlements.plist --sign "$MACOS_SIGN_IDENTITY" "$app"
codesign --verify --deep --strict --verbose=2 "$app"
ditto -c -k --keepParent "$app" "$RUNNER_TEMP/notary-app.zip"
xcrun notarytool submit "$RUNNER_TEMP/notary-app.zip" --key "$api_key" --key-id "$APPLE_API_KEY_ID" --issuer "$APPLE_API_ISSUER" --wait
xcrun stapler staple "$app"
spctl --assess --type execute --verbose=2 "$app"
python scripts/package_desktop.py --release
for dmg in .run/ApplicationTracker-*-macos-*.dmg; do
  codesign --force --timestamp --sign "$MACOS_SIGN_IDENTITY" "$dmg"
  xcrun notarytool submit "$dmg" --key "$api_key" --key-id "$APPLE_API_KEY_ID" --issuer "$APPLE_API_ISSUER" --wait
  xcrun stapler staple "$dmg"
  xcrun stapler validate "$dmg"
done
