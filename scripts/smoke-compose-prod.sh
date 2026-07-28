#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="infrastructure/docker/docker-compose.prod.yml"
SMOKE_TEMP_DIR=""
SSL_DIR=""
MONITOR_FIXTURE_USER_ID="00000000-0000-4000-8000-000000000001"
MONITOR_FIXTURE_AGENT_ID="00000000-0000-4000-8000-000000000002"
SMOKE_POSTGRES_VOLUME_CREATED=0
SMOKE_REDIS_VOLUME_CREATED=0

print_prerequisites() {
  echo "Required prerequisites: a running Docker daemon with Compose v2, access to pull/build"
  echo "container images and OpenSSL. PostgreSQL,"
  echo "Redis, migrations, the API, the"
  echo "monitor worker, the frontend, and nginx must all start successfully; every service"
  echo "with a health contract must pass it."
}

fail_with_prerequisites() {
  echo "$1"
  print_prerequisites
  exit 1
}

if ! command -v docker >/dev/null 2>&1; then
  fail_with_prerequisites "Docker is required for the production compose smoke test."
fi

if ! docker compose version >/dev/null 2>&1; then
  fail_with_prerequisites "Docker Compose v2 ('docker compose') is required for this smoke test."
fi

if ! docker info >/dev/null 2>&1; then
  fail_with_prerequisites "Docker daemon is not available. Start Docker before running this gate."
fi

if ! command -v curl >/dev/null 2>&1; then
  fail_with_prerequisites "curl is required to smoke the published nginx ports from the host."
fi

SMOKE_TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/mutx-compose-smoke.XXXXXX")"
SSL_DIR="${SMOKE_TEMP_DIR}/ssl"
smoke_suffix="$(basename "${SMOKE_TEMP_DIR}" | tr -cd 'a-zA-Z0-9' | tr '[:upper:]' '[:lower:]')-$$"
smoke_network_octet="$(printf '%s' "${smoke_suffix}" | cksum | awk '{print ($1 % 200) + 20}')"

export COMPOSE_PROJECT_NAME="mutx-smoke-${smoke_suffix}"
export COMPOSE_DISABLE_ENV_FILE=1
export MUTX_POSTGRES_VOLUME_NAME="${COMPOSE_PROJECT_NAME}-postgres-data"
export MUTX_REDIS_VOLUME_NAME="${COMPOSE_PROJECT_NAME}-redis-data"
export MUTX_API_HOST_PORT=0
export MUTX_HTTP_HOST_PORT=0
export MUTX_HTTPS_HOST_PORT=0
export MUTX_EDGE_BIND_ADDRESS=127.0.0.1
export MUTX_NETWORK_SUBNET="10.254.${smoke_network_octet}.0/24"
export FORWARDED_ALLOW_IPS="${MUTX_NETWORK_SUBNET}"
export POSTGRES_USER=mutx_smoke
export POSTGRES_DB=mutx_smoke
export POSTGRES_PASSWORD="mutx-smoke-postgres-${smoke_suffix}"
export JWT_SECRET="mutx-smoke-jwt-${smoke_suffix}-minimum-32-chars"
export SECRET_ENCRYPTION_KEY="mutx-smoke-encryption-${smoke_suffix}-minimum-32-chars"
export RECEIPT_SIGNING_KEY_ID="mutx-platform-smoke"
export RECEIPT_SIGNING_PRIVATE_KEY="0101010101010101010101010101010101010101010101010101010101010101"
export RECEIPT_TRUSTED_PUBLIC_KEYS='{"mutx-platform-smoke":"8a88e3dd7409f195fd52db2d3cba5d72ca6709bf1d94121bf3748801b40f6f5c"}'
export DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}"
export DATABASE_SSL_MODE=disable
export NEXT_PUBLIC_API_URL=https://api.invalid.test
export PUBLIC_API_URL=https://api.invalid.test
export NEXT_PUBLIC_SITE_URL=https://app.invalid.test
export CORS_ORIGINS=https://site.invalid.test,https://app.invalid.test
export ALLOWED_HOSTS=api.invalid.test,api.mutx.dev,app.mutx.dev,nginx,api,localhost,127.0.0.1
export MUTX_API_HOST=api.invalid.test
export REQUIRE_EMAIL_VERIFICATION=false
export WEB_CONCURRENCY=1
export MUTX_SSL_DIR="${SSL_DIR}"

cleanup() {
  docker compose -f "$COMPOSE_FILE" down --remove-orphans >/dev/null 2>&1 || true
  if [[ "${SMOKE_POSTGRES_VOLUME_CREATED}" == "1" ]]; then
    docker volume rm "${MUTX_POSTGRES_VOLUME_NAME}" >/dev/null 2>&1 || true
  fi
  if [[ "${SMOKE_REDIS_VOLUME_CREATED}" == "1" ]]; then
    docker volume rm "${MUTX_REDIS_VOLUME_NAME}" >/dev/null 2>&1 || true
  fi
  rm -f "$SSL_DIR/cert.pem" "$SSL_DIR/key.pem"
  rmdir "$SSL_DIR" "$SMOKE_TEMP_DIR" >/dev/null 2>&1 || true
}

dump_failure_context() {
  local exit_code=$?
  if [ "$exit_code" -eq 0 ]; then
    return
  fi

  echo ""
  echo "Production compose smoke test failed. Current service status:"
  docker compose -f "$COMPOSE_FILE" ps || true

  echo ""
  print_prerequisites

  echo ""
  echo "Recent service logs:"
  docker compose -f "$COMPOSE_FILE" logs --tail=200 \
    postgres redis migrate api monitor frontend nginx || true

  exit "$exit_code"
}

wait_for_check() {
  local description="$1"
  shift

  echo "Waiting for ${description}..."
  for _ in $(seq 1 60); do
    if "$@" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done

  echo "Timed out waiting for ${description}."
  "$@" || true
  return 1
}

verify_api_contract() {
  local path="$1"
  local expected_status="$2"

  docker compose -f "$COMPOSE_FILE" exec -T api \
    python -c '
import http.client
import json
import sys

path, expected_status = sys.argv[1:]
connection = http.client.HTTPConnection("localhost", 8000, timeout=5)
connection.request("GET", path)
response = connection.getresponse()
payload = json.load(response)
assert response.status == 200, f"{path} returned HTTP {response.status}"
assert payload.get("status") == expected_status, payload
assert payload.get("database") == "ready", payload
if expected_status == "healthy":
    assert payload.get("components", {}).get("database", {}).get("status") == "healthy", payload
' "$path" "$expected_status"
}

verify_frontend_contract() {
  docker compose -f "$COMPOSE_FILE" exec -T frontend \
    node scripts/verify-release-http.mjs frontend http://127.0.0.1:3000
}

verify_frontend_api_proxy() {
  docker compose -f "$COMPOSE_FILE" exec -T frontend \
    node scripts/verify-release-http.mjs health \
    http://127.0.0.1:3000/api/dashboard/health
}

verify_edge_contract() {
  local mode="$1"
  local url="$2"

  docker compose -f "$COMPOSE_FILE" exec -T \
    -e NODE_TLS_REJECT_UNAUTHORIZED=0 frontend \
    node scripts/verify-release-http.mjs "$mode" "$url"
}

postgres_query() {
  docker compose -f "$COMPOSE_FILE" exec -T \
    -e PGPASSWORD="$POSTGRES_PASSWORD" postgres \
    psql -X -qAt -w \
    -U "${POSTGRES_USER:-mutx}" \
    -d "${POSTGRES_DB:-mutx}" \
    -v ON_ERROR_STOP=1 \
    "$@"
}

verify_migration_contract() {
  local migrate_container
  local expected_heads
  local database_heads

  migrate_container="$(docker compose -f "$COMPOSE_FILE" ps --all --quiet migrate)"
  [ -n "$migrate_container" ]
  [ "$(docker inspect --format '{{.State.ExitCode}}' "$migrate_container")" = "0" ]

  expected_heads="$(
    docker compose -f "$COMPOSE_FILE" exec -T api alembic heads |
      awk '{print $1}' |
      sort
  )"
  database_heads="$(
    docker compose -f "$COMPOSE_FILE" exec -T api alembic current |
      awk '/\(head\)/ {print $1}' |
      sort
  )"
  [ -n "$expected_heads" ]
  [ "$database_heads" = "$expected_heads" ]
}

create_monitor_activity_fixture() {
  postgres_query -c "
    INSERT INTO users (
      id, email, name, password_hash, plan, api_key, created_at, updated_at,
      is_active, is_email_verified
    ) VALUES (
      '${MONITOR_FIXTURE_USER_ID}', 'monitor-smoke@invalid.test',
      'Compose monitor smoke', NULL, 'FREE', NULL,
      NOW() - INTERVAL '10 minutes', NOW() - INTERVAL '10 minutes', TRUE, FALSE
    );
    INSERT INTO agents (
      id, user_id, name, type, status, created_at, updated_at, last_heartbeat
    ) VALUES (
      '${MONITOR_FIXTURE_AGENT_ID}', '${MONITOR_FIXTURE_USER_ID}',
      'compose-monitor-activity', 'OPENAI', 'running',
      NOW() - INTERVAL '10 minutes', NOW() - INTERVAL '10 minutes',
      NOW() - INTERVAL '10 minutes'
    );
  " >/dev/null
}

verify_monitor_activity() {
  [ "$(postgres_query -c "
    SELECT COUNT(*)
    FROM agent_logs
    WHERE agent_id = '${MONITOR_FIXTURE_AGENT_ID}'
      AND message LIKE 'System: Agent marked as FAILED due to heartbeat timeout%';
  ")" -ge 1 ]
}

verify_monitor_container_health() {
  local monitor_container
  local monitor_state

  monitor_container="$(docker compose -f "$COMPOSE_FILE" ps --quiet monitor)"
  [ -n "${monitor_container}" ]
  monitor_state="$(
    docker inspect --format \
      '{{.State.Running}}|{{.State.Restarting}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' \
      "${monitor_container}"
  )"
  [ "${monitor_state}" = "true|false|healthy" ]
}

verify_nginx_tls_contract() {
  docker compose -f "$COMPOSE_FILE" exec -T nginx nginx -t >/dev/null
  docker compose -f "$COMPOSE_FILE" exec -T nginx nginx -T 2>&1 |
    grep -Eq 'ssl_protocols[[:space:]]+TLSv1\.2 TLSv1\.3;'

  docker compose -f "$COMPOSE_FILE" exec -T \
    -e NODE_TLS_REJECT_UNAUTHORIZED=0 frontend \
    node -e '
const tls = require("node:tls")

const socket = tls.connect(
  { host: "nginx", port: 443, rejectUnauthorized: false, minVersion: "TLSv1.2" },
  () => {
    const protocol = socket.getProtocol()
    if (protocol !== "TLSv1.2" && protocol !== "TLSv1.3") process.exitCode = 1
    socket.end()
  }
)
socket.setTimeout(5000, () => socket.destroy(new Error("TLS handshake timed out")))
socket.on("error", () => { process.exitCode = 1 })
' >/dev/null

  docker compose -f "$COMPOSE_FILE" exec -T frontend \
    node -e '
fetch("http://nginx/", { redirect: "manual" }).then((response) => {
  const location = response.headers.get("location") || ""
  if (response.status !== 301 || !location.startsWith("https://")) process.exitCode = 1
}).catch(() => { process.exitCode = 1 })
' >/dev/null
}

published_port() {
  local container_port="$1"
  local endpoint

  endpoint="$(docker compose -f "$COMPOSE_FILE" port nginx "${container_port}" | tail -n 1)"
  if [[ ! "${endpoint}" =~ :([0-9]+)$ ]]; then
    echo "Unable to resolve published nginx port ${container_port}: ${endpoint}" >&2
    return 1
  fi
  printf '%s' "${BASH_REMATCH[1]}"
}

verify_published_edge_contract() {
  local http_port
  local https_port
  local response_headers
  local frontend_html
  local static_asset
  local api_health

  http_port="$(published_port 80)"
  https_port="$(published_port 443)"

  response_headers="$(
    curl -fsS -D - -o /dev/null \
      -H 'Host: app.mutx.dev' \
      "http://127.0.0.1:${http_port}/"
  )"
  grep -Eq '^HTTP/[0-9.]+ 301' <<<"${response_headers}"
  grep -Eiq '^location: https://app\.mutx\.dev/' <<<"${response_headers}"

  frontend_html="$(
    curl --noproxy '*' --insecure --fail --silent --show-error \
      --resolve "app.mutx.dev:${https_port}:127.0.0.1" \
      "https://app.mutx.dev:${https_port}/"
  )"
  grep -q '/_next/static/' <<<"${frontend_html}"
  static_asset="$(grep -Eo '/_next/static/[^"[:space:]]+' <<<"${frontend_html}" | head -n 1)"
  curl --noproxy '*' --insecure --fail --silent --show-error \
    --resolve "app.mutx.dev:${https_port}:127.0.0.1" \
    "https://app.mutx.dev:${https_port}${static_asset}" >/dev/null

  api_health="$(
    curl --noproxy '*' --insecure --fail --silent --show-error \
      --resolve "api.invalid.test:${https_port}:127.0.0.1" \
      "https://api.invalid.test:${https_port}/health"
  )"
  grep -q '"status":"healthy"' <<<"${api_health}"
  grep -q '"database":"ready"' <<<"${api_health}"
}

wait_for_postgres_auth() {
  local service="$1"
  local user="$2"
  local db="$3"
  local password="$4"

  echo "Waiting for ${service} to accept user '${user}' authentication..."
  for _ in $(seq 1 60); do
    # pg_isready only checks TCP availability; use psql to verify auth works.
    # PGPASSWORD must be passed explicitly — psql's -w flag waits for password
    # auth and will hang indefinitely without it in non-interactive mode.
    if docker compose -f "$COMPOSE_FILE" exec -T \
      -e PGPASSWORD="$password" "$service" \
      psql -w -h localhost -U "${user}" -d "${db}" \
      -v ON_ERROR_STOP=1 -c "SELECT 1" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done

  echo "Timed out waiting for ${service} user '${user}' to authenticate."
  return 1
}

ensure_ssl_material() {
  if ! command -v openssl >/dev/null 2>&1; then
    fail_with_prerequisites \
      "OpenSSL is required to generate temporary nginx certificates for the smoke test."
  fi

  mkdir -p "$SSL_DIR"

  echo "Generating temporary self-signed TLS certificate for nginx smoke test..."
  openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout "$SSL_DIR/key.pem" \
    -out "$SSL_DIR/cert.pem" \
    -days 1 \
    -subj "/CN=localhost" >/dev/null 2>&1
}

trap dump_failure_context ERR
trap cleanup EXIT

for smoke_volume in "${MUTX_POSTGRES_VOLUME_NAME}" "${MUTX_REDIS_VOLUME_NAME}"; do
  if docker volume inspect "${smoke_volume}" >/dev/null 2>&1; then
    echo "Refusing to reuse an existing volume in the disposable smoke: ${smoke_volume}" >&2
    exit 1
  fi
done
docker volume create \
  --label "dev.mutx.smoke-project=${COMPOSE_PROJECT_NAME}" \
  "${MUTX_POSTGRES_VOLUME_NAME}" >/dev/null
SMOKE_POSTGRES_VOLUME_CREATED=1
docker volume create \
  --label "dev.mutx.smoke-project=${COMPOSE_PROJECT_NAME}" \
  "${MUTX_REDIS_VOLUME_NAME}" >/dev/null
SMOKE_REDIS_VOLUME_CREATED=1

echo "Starting production compose smoke core services..."
# Phase 1: Start only postgres and redis so we can verify auth before starting
# services that depend on the database. The compose healthcheck uses pg_isready
# which only confirms TCP availability — the initdb scripts that create the user
# may not have finished yet. Starting migrate before auth is ready causes a race.
docker compose -f "$COMPOSE_FILE" up -d --build postgres redis

wait_for_postgres_auth \
  "postgres" \
  "${POSTGRES_USER:-mutx}" \
  "${POSTGRES_DB:-mutx}" \
  "${POSTGRES_PASSWORD}"

# Phase 2: Now that postgres auth is confirmed, start migrate + api + monitor.
docker compose -f "$COMPOSE_FILE" up -d --build migrate api monitor

wait_for_check "API health endpoint to report healthy" verify_api_contract /health healthy
verify_api_contract /ready ready
verify_migration_contract
wait_for_check "monitor worker container health" verify_monitor_container_health
create_monitor_activity_fixture
wait_for_check "monitor worker to record a real monitoring cycle" verify_monitor_activity

echo "Starting production compose smoke edge services..."
docker compose -f "$COMPOSE_FILE" up -d --build frontend

wait_for_check \
  "rendered frontend, Next.js static asset, and API health proxy" \
  verify_frontend_contract
verify_frontend_api_proxy

ensure_ssl_material
docker compose -f "$COMPOSE_FILE" up -d nginx

verify_nginx_tls_contract

wait_for_check \
  "nginx HTTPS frontend and static asset" \
  verify_edge_contract frontend https://nginx/
verify_edge_contract health http://nginx/health
verify_edge_contract ready http://nginx/ready
verify_edge_contract health https://nginx/api/dashboard/health
wait_for_check "nginx frontend, asset, redirect, and API through published host ports" \
  verify_published_edge_contract
verify_monitor_container_health
verify_monitor_activity

echo "Production compose smoke test passed."
