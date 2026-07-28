#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

reviewed_railway_cli_version="5.30.1"
if ! command -v railway >/dev/null 2>&1; then
  echo "Railway CLI ${reviewed_railway_cli_version} is required." >&2
  exit 1
fi
railway_version_output="$(railway --version)"
railway_version="${railway_version_output##* }"
if [[ "${railway_version}" != "${reviewed_railway_cli_version}" ]]; then
  echo "Railway CLI must be the reviewed version ${reviewed_railway_cli_version}." >&2
  exit 1
fi

required_vars=(
  RAILWAY_TOKEN
  RAILWAY_PROJECT_ID
  RAILWAY_FRONTEND_SERVICE_ID
  RAILWAY_API_SERVICE_ID
  RAILWAY_ENVIRONMENT_ID
  RELEASE_TAG
  RELEASE_VERSION
  RELEASE_SHA
)

APP_URL="${APP_URL:-https://app.mutx.dev}"
API_URL="${API_URL:-https://api.mutx.dev}"
FRONTEND_RELEASE_IDENTITY_URL="${FRONTEND_RELEASE_IDENTITY_URL:-${RELEASE_IDENTITY_URL:-${APP_URL}/mutx-release.json}}"
API_RELEASE_IDENTITY_URL="${API_RELEASE_IDENTITY_URL:-${API_URL}/release}"

for var_name in "${required_vars[@]}"; do
  if [[ -z "${!var_name:-}" ]]; then
    echo "Missing required Railway environment variable: ${var_name}" >&2
    exit 1
  fi
done

package_version="$(node -p "require('./package.json').version")"
validated_version="$(
  bash scripts/validate-release-version.sh desktop "${RELEASE_TAG}" "${package_version}"
)"
if [[ "${validated_version}" != "${RELEASE_VERSION}" || "${validated_version}" == *-* ]]; then
  echo "Railway production promotion requires the exact stable package version ${package_version}." >&2
  exit 1
fi
if [[ ! "${RELEASE_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "RELEASE_SHA must be a full lowercase 40-character Git commit SHA." >&2
  exit 1
fi

checkout_sha="$(git rev-parse HEAD)"
tag_sha="$(git rev-list -n 1 "${RELEASE_TAG}")"
if [[ "${RELEASE_SHA}" != "${checkout_sha}" || "${RELEASE_SHA}" != "${tag_sha}" ]]; then
  echo "Release SHA must match both the checkout and ${RELEASE_TAG}." >&2
  exit 1
fi

RELEASE_IDENTITY_FILES=("public/mutx-release.json" "src/api/mutx-release.json")
for release_identity_file in "${RELEASE_IDENTITY_FILES[@]}"; do
  if [[ -e "${release_identity_file}" ]]; then
    echo "Refusing to overwrite existing release identity file: ${release_identity_file}" >&2
    exit 1
  fi
done

cleanup_release_identity() {
  rm -f "${RELEASE_IDENTITY_FILES[@]}"
}
trap cleanup_release_identity EXIT

RELEASE_TAG="${RELEASE_TAG}" \
RELEASE_VERSION="${RELEASE_VERSION}" \
RELEASE_SHA="${RELEASE_SHA}" \
node -e '
const fs = require("node:fs")
const identity = `${JSON.stringify({
  tag: process.env.RELEASE_TAG,
  version: process.env.RELEASE_VERSION,
  sha: process.env.RELEASE_SHA,
})}\n`
for (const path of ["public/mutx-release.json", "src/api/mutx-release.json"]) {
  fs.writeFileSync(path, identity, { flag: "wx" })
}
'

deploy_service() {
  local service_id="$1"
  local label="$2"

  echo "Promoting the ${label} Railway service for release ${RELEASE_TAG}..."
  railway up \
    --ci \
    --project "${RAILWAY_PROJECT_ID}" \
    --environment "${RAILWAY_ENVIRONMENT_ID}" \
    --service "${service_id}" \
    --message "Promote ${RELEASE_TAG} (${RELEASE_SHA})"
}

echo "Checking production version immediately before Railway deployment..."
node scripts/check-production-version.cjs \
  "${RELEASE_VERSION}" \
  "${RELEASE_SHA}" \
  "${API_RELEASE_IDENTITY_URL}" \
  "${FRONTEND_RELEASE_IDENTITY_URL}"

deploy_service "${RAILWAY_API_SERVICE_ID}" "backend"
deploy_service "${RAILWAY_FRONTEND_SERVICE_ID}" "frontend"

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
    if RELEASE_TAG="${RELEASE_TAG}" \
      RELEASE_VERSION="${RELEASE_VERSION}" \
      RELEASE_SHA="${RELEASE_SHA}" \
      node scripts/verify-release-http.mjs release "${identity_url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 5
  done

  RELEASE_TAG="${RELEASE_TAG}" \
    RELEASE_VERSION="${RELEASE_VERSION}" \
    RELEASE_SHA="${RELEASE_SHA}" \
    node scripts/verify-release-http.mjs release "${identity_url}"
}

wait_for_release_identity "API" "${API_RELEASE_IDENTITY_URL}"
wait_for_release_identity "frontend" "${FRONTEND_RELEASE_IDENTITY_URL}"

echo "Railway production promotion complete for ${RELEASE_TAG}."
