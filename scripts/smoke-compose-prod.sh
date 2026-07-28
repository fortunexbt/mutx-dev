#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="infrastructure/docker/docker-compose.prod.yml"
SSL_DIR="$ROOT_DIR/infrastructure/docker/ssl"
TEMP_SSL_DIR_CREATED=0
TEMP_SSL_CERT_CREATED=0

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required for the production compose smoke test."
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is not available. Start Docker or set MUTX_SKIP_COMPOSE_SMOKE=1."
  exit 1
fi

export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-mutx-smoke}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-mutx-smoke-password}"
export JWT_SECRET="${JWT_SECRET:-mutx-smoke-jwt-secret-please-change-32chars}"
export SECRET_ENCRYPTION_KEY="${SECRET_ENCRYPTION_KEY:-$JWT_SECRET}"
export RECEIPT_SIGNING_PRIVATE_KEY="${RECEIPT_SIGNING_PRIVATE_KEY:-$(printf '01%.0s' {1..32})}"

if [ "$SECRET_ENCRYPTION_KEY" = "$JWT_SECRET" ]; then
  export SECRET_ENCRYPTION_KEY="${SECRET_ENCRYPTION_KEY}-enc"
fi
export DATABASE_URL="${DATABASE_URL:-postgresql://mutx:${POSTGRES_PASSWORD}@postgres:5432/mutx}"
export DATABASE_SSL_MODE="${DATABASE_SSL_MODE:-disable}"
export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-https://api.mutx.dev}"
export NEXT_PUBLIC_SITE_URL="${NEXT_PUBLIC_SITE_URL:-https://app.mutx.dev}"
export CORS_ORIGINS="${CORS_ORIGINS:-https://mutx.dev,https://app.mutx.dev}"
export WEB_CONCURRENCY="${WEB_CONCURRENCY:-1}"

cleanup() {
  docker compose -f "$COMPOSE_FILE" down -v --remove-orphans >/dev/null 2>&1 || true
  if [ "$TEMP_SSL_CERT_CREATED" = "1" ]; then
    rm -f "$SSL_DIR/cert.pem" "$SSL_DIR/key.pem"
  fi
  if [ "$TEMP_SSL_DIR_CREATED" = "1" ]; then
    rmdir "$SSL_DIR" >/dev/null 2>&1 || true
  fi
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
  echo "Recent service logs:"
  docker compose -f "$COMPOSE_FILE" logs --tail=200 \
    postgres redis migrate api monitor frontend nginx || true

  exit "$exit_code"
}

wait_for_command() {
  local description="$1"
  local command="$2"

  echo "Waiting for ${description}..."
  for _ in $(seq 1 60); do
    if eval "$command"; then
      return 0
    fi
    sleep 2
  done

  echo "Timed out waiting for ${description}."
  return 1
}

wait_for_postgres_auth() {
  local host="$1"
  local user="$2"
  local db="$3"
  local password="$4"

  echo "Waiting for postgres to accept user '${user}' authentication..."
  for _ in $(seq 1 60); do
    # pg_isready only checks TCP availability; use psql to verify auth works.
    # PGPASSWORD must be passed explicitly — psql's -w flag waits for password
    # auth and will hang indefinitely without it in non-interactive mode.
    if env PGPASSWORD="$password" \
      docker compose -f "$COMPOSE_FILE" exec -T postgres \
      psql -h localhost -U "${user}" -d "${db}" -c "SELECT 1" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done

  echo "Timed out waiting for postgres user '${user}' to authenticate."
  return 1
}

ensure_ssl_material() {
  if [ -f "$SSL_DIR/cert.pem" ] && [ -f "$SSL_DIR/key.pem" ]; then
    return 0
  fi

  if [ -e "$SSL_DIR/cert.pem" ] || [ -e "$SSL_DIR/key.pem" ]; then
    echo "Expected both $SSL_DIR/cert.pem and $SSL_DIR/key.pem for nginx TLS."
    return 1
  fi

  if ! command -v openssl >/dev/null 2>&1; then
    echo "OpenSSL is required to generate temporary nginx certificates for the smoke test."
    return 1
  fi

  if [ ! -d "$SSL_DIR" ]; then
    mkdir -p "$SSL_DIR"
    TEMP_SSL_DIR_CREATED=1
  fi

  echo "Generating temporary self-signed TLS certificate for nginx smoke test..."
  openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout "$SSL_DIR/key.pem" \
    -out "$SSL_DIR/cert.pem" \
    -days 1 \
    -subj "/CN=localhost" >/dev/null 2>&1
  TEMP_SSL_CERT_CREATED=1
}

trap dump_failure_context ERR
trap cleanup EXIT

echo "Starting production compose smoke core services..."
# Clean named volumes before starting to prevent auth failures from stale postgres state.
docker compose -f "$COMPOSE_FILE" down -v --remove-orphans >/dev/null 2>&1 || true

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

wait_for_command \
  "API health endpoint" \
  "docker compose -f \"$COMPOSE_FILE\" exec -T api curl -fsS http://localhost:8000/health >/dev/null 2>&1"

docker compose -f "$COMPOSE_FILE" exec -T api curl -fsS http://localhost:8000/health >/dev/null
docker compose -f "$COMPOSE_FILE" exec -T api curl -fsS http://localhost:8000/ready >/dev/null

echo "Starting production compose smoke edge services..."
docker compose -f "$COMPOSE_FILE" up -d --build frontend

wait_for_command \
  "frontend health endpoint" \
  "docker compose -f \"$COMPOSE_FILE\" exec -T frontend node -e \"require('http').get('http://127.0.0.1:3000', (res) => process.exit(res.statusCode < 500 ? 0 : 1)).on('error', () => process.exit(1))\" >/dev/null 2>&1"

ensure_ssl_material
docker compose -f "$COMPOSE_FILE" up -d nginx

wait_for_command \
  "nginx health endpoint" \
  "docker compose -f \"$COMPOSE_FILE\" exec -T nginx wget -q -O - http://127.0.0.1/health >/dev/null 2>&1"

echo "Production compose smoke test passed."
