#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "scripts/deploy.sh delegates to the verified production deployment contract."
exec bash "${ROOT_DIR}/scripts/deploy-production.sh" "$@"
