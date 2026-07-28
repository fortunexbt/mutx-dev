# MUTX macOS Signing And Notarization

Recommended path: use a Developer ID Application certificate plus an App Store Connect API key.

## What you need

1. Apple Developer Program membership
2. A `Developer ID Application` certificate installed in your login keychain
3. Xcode command line tools (`xcode-select --install`)
4. An App Store Connect API key with permission to submit notarization requests

## Recommended credentials

Set these environment variables before building:

```bash
export APPLE_API_KEY="/absolute/path/to/AuthKey_ABC123XYZ.p8"
export APPLE_API_KEY_ID="ABC123XYZ"
export APPLE_API_ISSUER="00000000-0000-0000-0000-000000000000"
export APPLE_TEAM_ID="TEAMID1234"
```

## GitHub Actions release secrets

The versioned desktop release lane expects these GitHub Actions secrets:

```text
APPLE_DEVELOPER_ID_APP_CERT_B64
APPLE_DEVELOPER_ID_APP_CERT_PASSWORD
APPLE_API_KEY_B64
APPLE_API_KEY_ID
APPLE_API_ISSUER
APPLE_TEAM_ID
APPLE_KEYCHAIN_PASSWORD   # optional override; workflow can fall back to a default
```

- `APPLE_DEVELOPER_ID_APP_CERT_B64` should be the base64-encoded `.p12` for the `Developer ID Application` certificate.
- `APPLE_API_KEY_B64` should be the base64-encoded App Store Connect `.p8` file.
- `desktop/scripts/setup-ci-signing.sh` materializes both files into the runner temp directory, imports the certificate into a temporary keychain, and exports the notarization env vars expected by the existing scripts.

If you already stored credentials in the macOS Keychain with `xcrun notarytool store-credentials`, you can use:

```bash
export APPLE_KEYCHAIN_PROFILE="your-notary-profile"
# optional:
export APPLE_KEYCHAIN="/Users/you/Library/Keychains/login.keychain-db"
```

## Fallback credentials

If you prefer Apple ID auth instead of an API key:

```bash
export APPLE_ID="you@example.com"
export APPLE_APP_SPECIFIC_PASSWORD="xxxx-xxxx-xxxx-xxxx"
export APPLE_TEAM_ID="TEAMID1234"
```

## Build

First verify the environment:

```bash
npm run desktop:signing-check
```

Then build:

```bash
npm run desktop:build
```

If the Developer ID certificate is installed correctly, `electron-builder` will sign the `.app` bundles and produce the release ZIPs. The release packaging script then assembles plain drag-to-Applications DMGs from those already-verified signed apps, and `desktop/scripts/notarize.js` still notarizes each built `.app` automatically during the builder step.

## Faster debug loop

When you are debugging notarization, avoid the multi-arch build first:

```bash
npm run desktop:build:arm64
```

That targeted loop now:

1. builds the signed `arm64` app directory
2. builds the signed `arm64` ZIP with `electron-builder`
3. verifies the app and extracted ZIP recursively
4. assembles the `arm64` DMG from the verified app bundle
5. mounts the DMG and recursively verifies the embedded app before notarization

Check the current status of the generated artifacts:

```bash
npm run desktop:notarize:status
npm run desktop:checksums
```

Retry notarization on the latest built `.app` without rebuilding everything:

```bash
npm run desktop:notarize:latest
```

By default that command now notarizes the newest built `.app` and the newest built `.dmg`, then staples and validates both.

Or target specific artifacts:

```bash
VERSION="$(node -p "require('./package.json').version")"
node desktop/scripts/notarize-existing.js --app dist/desktop/mac-arm64/MUTX.app
node desktop/scripts/notarize-existing.js --dmg "dist/desktop/MUTX-${VERSION}-macos-arm64.dmg"
node desktop/scripts/notarize-existing.js --app dist/desktop/mac-arm64/MUTX.app --dmg "dist/desktop/MUTX-${VERSION}-macos-arm64.dmg"
```

## Release artifact contract

The desktop release lane now standardizes these artifact names:

```text
MUTX-<version>-macos-arm64.dmg
MUTX-<version>-macos-x64.dmg
MUTX-<version>-macos-arm64.zip
MUTX-<version>-macos-x64.zip
MUTX-<version>-SHA256SUMS.txt
```

The website download routes resolve against those names only after GitHub reports all five files as
uploaded and non-empty and the checksum file parses as the exact four-package manifest. Changing the
contract requires updating the website resolver, checksum verifier, and release workflow together.

## Release packaging contract

`npm run desktop:package:release` now runs the release packaging lane in this order:

1. the standalone packager ensures the locked native runtime dependencies for each requested
   architecture are present before `electron-builder` runs
2. `electron-builder` builds signed `.app` bundles plus `arm64` and `x64` ZIPs
3. the release verifier extracts each ZIP, recursively verifies the contained app, and requires the
   exact `arm64` or `x86_64` Mach-O executable declared by its public artifact name
4. the release packager creates simple drag-to-Applications DMGs from the verified signed apps
5. the release verifier mounts each DMG and repeats signature and exact-architecture verification
   before notarization

If the mounted app inside a DMG fails recursive codesign verification, the release stops before any notary submission.
