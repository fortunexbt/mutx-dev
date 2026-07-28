#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RELEASE_VERSION="${RELEASE_VERSION:-$(node -p "require('./package.json').version")}"
RELEASE_TAG="${RELEASE_TAG:-}"
RELEASE_SHA="${RELEASE_SHA:-}"
RELEASE_LINE="${RELEASE_VERSION%.*}"
SITE_URL="${SITE_URL:-https://mutx.dev}"
APP_URL="${APP_URL:-https://app.mutx.dev}"
API_URL="${API_URL:-https://api.mutx.dev}"
DOCS_RELEASE_URL="${DOCS_RELEASE_URL:-${SITE_URL}/docs/releases/v${RELEASE_LINE}}"
RELEASE_NOTES_ROUTE="${RELEASE_NOTES_ROUTE:-${SITE_URL}/download/macos/release-notes}"
RELEASE_IDENTITY_URL="${RELEASE_IDENTITY_URL:-${APP_URL}/mutx-release.json}"
API_RELEASE_IDENTITY_URL="${API_RELEASE_IDENTITY_URL:-${API_URL}/release}"
ARM64_DOWNLOAD_ROUTE="${ARM64_DOWNLOAD_ROUTE:-${SITE_URL}/download/macos/arm64}"
INTEL_DOWNLOAD_ROUTE="${INTEL_DOWNLOAD_ROUTE:-${SITE_URL}/download/macos/intel}"
GITHUB_RELEASE_DOWNLOAD_URL="${GITHUB_RELEASE_DOWNLOAD_URL:-https://github.com/mutx-dev/mutx-dev/releases/download/${RELEASE_TAG}}"

package_version="$(node -p "require('./package.json').version")"
validated_version="$(
  bash scripts/validate-release-version.sh desktop "${RELEASE_TAG}" "${package_version}"
)"
if [[ "${validated_version}" != "${RELEASE_VERSION}" || "${validated_version}" == *-* ]]; then
  echo "Production verification requires the exact stable package version ${package_version}." >&2
  exit 1
fi
if [[ ! "${RELEASE_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "RELEASE_SHA must be a full lowercase 40-character Git commit SHA." >&2
  exit 1
fi

normalize_url() {
  local url="$1"
  printf '%s' "${url%/}"
}

require_content() {
  local url="$1"
  local pattern="$2"
  local body

  echo "Checking ${url} contains ${pattern}..."
  body="$(curl -fsSL --retry 3 --retry-delay 2 "${url}")"
  if ! grep -qi "${pattern}" <<<"${body}"; then
    echo "Expected ${url} to contain pattern: ${pattern}" >&2
    exit 1
  fi
}

verify_release_identity() {
  RELEASE_TAG="${RELEASE_TAG}" \
  RELEASE_VERSION="${RELEASE_VERSION}" \
  RELEASE_SHA="${RELEASE_SHA}" \
  node "$ROOT_DIR/scripts/verify-release-http.mjs" release "$1"
}

effective_url() {
  curl -fsSL --retry 3 --retry-delay 2 -o /dev/null -w '%{url_effective}' "$1"
}

verify_architecture_download() {
  local route="$1"
  local expected_asset_url="$2"
  local redirect_url

  echo "Checking ${route} resolves to ${expected_asset_url}..."
  redirect_url="$(
    curl -fsS --retry 3 --retry-delay 2 --max-redirs 0 \
      -o /dev/null -w '%{redirect_url}' "${route}"
  )"
  if [[ "$(normalize_url "${redirect_url}")" != "$(normalize_url "${expected_asset_url}")" ]]; then
    echo "Architecture route ${route} resolved to ${redirect_url:-<none>}, expected ${expected_asset_url}" >&2
    exit 1
  fi

  curl -fsSL --retry 3 --retry-delay 2 --range 0-0 "${route}" -o /dev/null
}

verify_published_artifacts() {
  local release_download_url="$1"
  local expected_packages=(
    "MUTX-${RELEASE_VERSION}-macos-arm64.dmg"
    "MUTX-${RELEASE_VERSION}-macos-x64.dmg"
    "MUTX-${RELEASE_VERSION}-macos-arm64.zip"
    "MUTX-${RELEASE_VERSION}-macos-x64.zip"
  )
  local checksum_file="MUTX-${RELEASE_VERSION}-SHA256SUMS.txt"

  (
    artifact_dir="$(mktemp -d)"
    trap 'rm -rf "${artifact_dir}"' EXIT

    echo "Downloading published checksum manifest and all four desktop artifacts..."
    curl -fsSL --retry 3 --retry-delay 2 --proto '=https' --tlsv1.2 \
      "${release_download_url}/${checksum_file}" \
      -o "${artifact_dir}/${checksum_file}"
    for artifact in "${expected_packages[@]}"; do
      curl -fsSL --retry 3 --retry-delay 2 --proto '=https' --tlsv1.2 \
        "${release_download_url}/${artifact}" \
        -o "${artifact_dir}/${artifact}"
    done

    node "$ROOT_DIR/desktop/scripts/verify-checksum-manifest.js" \
      --dir "${artifact_dir}" \
      --version "${RELEASE_VERSION}"
  )
}

require_content "${SITE_URL}" "Example MUTX governed deployment record"
require_content "${SITE_URL}" "Releases"
require_content "${SITE_URL}/download/macos" "Download MUTX for macOS"
require_content "${APP_URL}/login" "Welcome back"
require_content "${APP_URL}/register" "Create your account"
require_content "${DOCS_RELEASE_URL}" "v${RELEASE_VERSION}"
node "$ROOT_DIR/scripts/verify-release-http.mjs" health "${API_URL}/health"
node "$ROOT_DIR/scripts/verify-release-http.mjs" ready "${API_URL}/ready"

wait_for_release_identity() {
  local label="$1"
  local identity_url="$2"
  local separator="?"

  if [[ "${identity_url}" == *\?* ]]; then
    separator="&"
  fi
  identity_url="${identity_url}${separator}expected_sha=${RELEASE_SHA}"

  echo "Waiting for exact ${label} release identity at ${identity_url%%\?*}..."
  for _ in $(seq 1 60); do
    if verify_release_identity "${identity_url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 5
  done
  verify_release_identity "${identity_url}"
}

wait_for_release_identity "API" "${API_RELEASE_IDENTITY_URL}"
wait_for_release_identity "frontend" "${RELEASE_IDENTITY_URL}"

bash "$ROOT_DIR/scripts/verify-production-seo.sh"

dashboard_effective_url="$(normalize_url "$(effective_url "${APP_URL}/dashboard")")"
expected_dashboard_url="$(normalize_url "${APP_URL}/dashboard")"
expected_login_url="$(normalize_url "${APP_URL}/login")"
if [[ "${dashboard_effective_url}" != "${expected_dashboard_url}" && "${dashboard_effective_url}" != "${expected_login_url}" ]]; then
  echo "Unexpected dashboard redirect target: ${dashboard_effective_url}" >&2
  exit 1
fi

release_notes_effective_url="$(normalize_url "$(effective_url "${RELEASE_NOTES_ROUTE}")")"
expected_release_notes_url="$(normalize_url "${DOCS_RELEASE_URL}")"
if [[ "${release_notes_effective_url}" != "${expected_release_notes_url}" ]]; then
  echo "Release notes route resolved to ${release_notes_effective_url}, expected ${expected_release_notes_url}" >&2
  exit 1
fi

arm64_asset_url="${GITHUB_RELEASE_DOWNLOAD_URL}/MUTX-${RELEASE_VERSION}-macos-arm64.dmg"
intel_asset_url="${GITHUB_RELEASE_DOWNLOAD_URL}/MUTX-${RELEASE_VERSION}-macos-x64.dmg"
verify_architecture_download "${ARM64_DOWNLOAD_ROUTE}" "${arm64_asset_url}"
verify_architecture_download "${INTEL_DOWNLOAD_ROUTE}" "${intel_asset_url}"
verify_published_artifacts "${GITHUB_RELEASE_DOWNLOAD_URL}"

echo "Public release verification passed for ${RELEASE_VERSION}."
