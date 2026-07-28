#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env.production"
COMPOSE_FILE="${ROOT_DIR}/infrastructure/docker/docker-compose.prod.yml"
inherited_project_name="${COMPOSE_PROJECT_NAME:-}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "❌ Missing ${ENV_FILE}" >&2
  echo "Create it from .env.production.example and replace every placeholder first." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "❌ Docker Compose v2 ('docker compose') is required" >&2
  exit 1
fi

file_project_name="$(
  python3 - "${ENV_FILE}" <<'PY'
import re
import sys
from pathlib import Path

value = ""
for raw_line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if re.match(r"^COMPOSE_PROJECT_NAME=", raw_line):
        value = raw_line.split("=", 1)[1].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
print(value)
PY
)"
if [[ -n "${inherited_project_name}" ]]; then
  COMPOSE_PROJECT_NAME="${inherited_project_name}"
else
  COMPOSE_PROJECT_NAME="${file_project_name:-docker}"
fi
if [[ ! "${COMPOSE_PROJECT_NAME}" =~ ^[a-z0-9][a-z0-9_-]*$ ]]; then
  echo "❌ Invalid production Compose project name: ${COMPOSE_PROJECT_NAME}" >&2
  exit 1
fi

COMPOSE_CMD=(docker compose --project-name "${COMPOSE_PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}")
"${COMPOSE_CMD[@]}" config --quiet

if [[ -n "$("${COMPOSE_CMD[@]}" ps --all --quiet postgres redis)" ]]; then
  echo "❌ Production database/cache containers already exist for ${COMPOSE_PROJECT_NAME}." >&2
  echo "Use scripts/deploy-production.sh for an existing installation." >&2
  exit 1
fi

volume_names=()
while IFS= read -r volume_name; do
  volume_names+=("${volume_name}")
done < <(
  "${COMPOSE_CMD[@]}" config --format json |
    python3 -c '
import json
import sys

config = json.load(sys.stdin)
for key in ("postgres_data", "redis_data"):
    volume = config.get("volumes", {}).get(key, {})
    if not volume.get("external") or not volume.get("name"):
        raise SystemExit(f"{key} must be an explicitly named external volume")
    print(volume["name"])
'
)

if [[ "${#volume_names[@]}" -ne 2 || "${volume_names[0]}" == "${volume_names[1]}" ]]; then
  echo "❌ Production PostgreSQL and Redis must use two distinct external volumes." >&2
  exit 1
fi

echo "📦 Pulling the database/cache images needed for one-time initialization..."
"${COMPOSE_CMD[@]}" pull postgres redis

for volume_name in "${volume_names[@]}"; do
  if ! docker volume inspect "${volume_name}" >/dev/null 2>&1; then
    docker volume create "${volume_name}" >/dev/null
  fi

  if ! docker run --rm --pull never --read-only --network none \
    --mount "type=volume,src=${volume_name},dst=/volume,readonly" \
    --entrypoint /bin/sh postgres:16-alpine \
    -eu -c 'test -z "$(ls -A /volume)"'; then
    echo "❌ Volume ${volume_name} already contains data." >&2
    echo "Bootstrap is only for a completely empty first installation." >&2
    exit 1
  fi
done

cleanup() {
  "${COMPOSE_CMD[@]}" stop postgres redis >/dev/null 2>&1 || true
  "${COMPOSE_CMD[@]}" rm -f -s postgres redis >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "🚀 Initializing the empty PostgreSQL and Redis volumes..."
"${COMPOSE_CMD[@]}" up -d postgres redis

ready=false
for _attempt in {1..60}; do
  postgres_container="$("${COMPOSE_CMD[@]}" ps --quiet postgres)"
  redis_container="$("${COMPOSE_CMD[@]}" ps --quiet redis)"
  postgres_health="$(docker inspect --format '{{.State.Health.Status}}' "${postgres_container}" 2>/dev/null || true)"
  redis_health="$(docker inspect --format '{{.State.Health.Status}}' "${redis_container}" 2>/dev/null || true)"
  if [[ "${postgres_health}" == "healthy" && "${redis_health}" == "healthy" ]]; then
    ready=true
    break
  fi
  sleep 2
done

if [[ "${ready}" != "true" ]]; then
  echo "❌ PostgreSQL and Redis did not become healthy during bootstrap." >&2
  "${COMPOSE_CMD[@]}" logs --tail 100 postgres redis >&2 || true
  exit 1
fi

cleanup
trap - EXIT

if ! docker run --rm --pull never --read-only --network none \
  --mount "type=volume,src=${volume_names[0]},dst=/volume,readonly" \
  --entrypoint /bin/sh postgres:16-alpine \
  -eu -c 'test -s /volume/PG_VERSION && test -d /volume/base && test -d /volume/global'; then
  echo "❌ PostgreSQL bootstrap did not leave an initialized cluster." >&2
  exit 1
fi
if ! docker run --rm --pull never --read-only --network none \
  --mount "type=volume,src=${volume_names[1]},dst=/volume,readonly" \
  --entrypoint /bin/sh postgres:16-alpine \
  -eu -c 'test -n "$(ls -A /volume)"'; then
  echo "❌ Redis bootstrap did not leave persistent state." >&2
  exit 1
fi

echo "✅ Empty production volumes are initialized and containers are stopped."
echo "Next: bash scripts/deploy-production.sh"
