#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST_DIR="$ROOT_DIR/dist/desktop"
VERSION="$(node -p "require('$ROOT_DIR/package.json').version")"
OUTPUT_FILE="$DIST_DIR/MUTX-${VERSION}-SHA256SUMS.txt"

if [[ ! -d "$DIST_DIR" ]]; then
  echo "Desktop artifact directory does not exist: $DIST_DIR" >&2
  exit 1
fi

cd "$DIST_DIR"

artifacts=(
  "MUTX-${VERSION}-macos-arm64.dmg"
  "MUTX-${VERSION}-macos-x64.dmg"
  "MUTX-${VERSION}-macos-arm64.zip"
  "MUTX-${VERSION}-macos-x64.zip"
)

for artifact in "${artifacts[@]}"; do
  if [[ ! -f "$artifact" || -L "$artifact" || ! -s "$artifact" ]]; then
    echo "Required desktop artifact must be a non-empty regular file: $DIST_DIR/$artifact" >&2
    exit 1
  fi
done

shasum -a 256 "${artifacts[@]}" >"$OUTPUT_FILE"

echo "Wrote checksums to $OUTPUT_FILE"
