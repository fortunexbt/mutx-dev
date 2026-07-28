#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

requested_lane="${1:-all}"
fixture_preload="${ROOT_DIR}/tests/release-github-fixture.cjs"

if [[ ! -f "${fixture_preload}" ]]; then
  echo "Missing deterministic release fixture preload: ${fixture_preload}" >&2
  exit 1
fi

run_lane() {
  local lane="$1"
  local grep_args=(--grep "@release-fixture-${lane}")

  if [[ "${lane}" == "unavailable" && "${requested_lane}" == "all" ]]; then
    grep_args=(--grep-invert '@release-fixture-available')
  fi

  echo "Building the production frontend with deterministic ${lane} release data..."
  MUTX_DESKTOP_RELEASE_FIXTURE="${lane}" \
    NODE_OPTIONS="--require=${fixture_preload}" \
    npm run build

  echo "Running the ${lane} release browser contract..."
  MUTX_DESKTOP_RELEASE_FIXTURE="${lane}" \
    NODE_OPTIONS="--require=${fixture_preload}" \
    npx playwright test \
      --project=chromium \
      --workers=1 \
      "${grep_args[@]}"
}

case "${requested_lane}" in
  all)
    run_lane unavailable
    run_lane available
    ;;
  available | unavailable)
    run_lane "${requested_lane}"
    ;;
  *)
    echo "Usage: $0 [all|available|unavailable]" >&2
    exit 2
    ;;
esac
