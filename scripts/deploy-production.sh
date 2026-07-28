#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env.production"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.production.yml"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "❌ Missing ${ENV_FILE}"
  echo "Create it from .env.production.example and set real secrets first."
  exit 1
fi

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
else
  echo "❌ docker compose is not installed"
  exit 1
fi

echo "🔎 Validating required environment variables..."
required_vars=(POSTGRES_PASSWORD DATABASE_URL JWT_SECRET RECEIPT_SIGNING_PRIVATE_KEY NEXT_PUBLIC_API_URL NEXT_PUBLIC_SITE_URL)
for var_name in "${required_vars[@]}"; do
  if ! grep -Eq "^${var_name}=.+" "${ENV_FILE}"; then
    echo "❌ Missing required variable in .env.production: ${var_name}"
    exit 1
  fi
done

echo "🔎 Validating compose configuration..."
"${COMPOSE_CMD[@]}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" config >/dev/null

echo "📦 Pulling latest images..."
"${COMPOSE_CMD[@]}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" pull

echo "🚀 Deploying production stack..."
"${COMPOSE_CMD[@]}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d --build --remove-orphans

echo "⏳ Waiting for API health endpoint..."
for i in {1..45}; do
  if curl -fsS "http://localhost:8000/health" >/dev/null 2>&1; then
    echo "✅ API is healthy"
    break
  fi
  sleep 2
  if [[ $i -eq 45 ]]; then
    echo "❌ API health check failed"
    echo "📄 Last 100 lines of API logs:"
    "${COMPOSE_CMD[@]}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" logs --tail 100 api || true
    exit 1
  fi
done

echo "✅ Production deployment completed"
"${COMPOSE_CMD[@]}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" ps
