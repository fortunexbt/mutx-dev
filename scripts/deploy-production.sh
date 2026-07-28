#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env.production"
COMPOSE_FILE="${ROOT_DIR}/infrastructure/docker/docker-compose.prod.yml"
inherited_project_name="${COMPOSE_PROJECT_NAME:-}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "❌ Missing ${ENV_FILE}"
  echo "Create it from .env.production.example and set real secrets first."
  exit 1
fi

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "❌ Missing production compose manifest: ${COMPOSE_FILE}"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "❌ Docker Compose v2 ('docker compose') is required"
  exit 1
fi

for command_name in curl mktemp openssl python3 sed; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "❌ Required deployment command is unavailable: ${command_name}"
    exit 1
  fi
done

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

echo "🔎 Validating required environment variables..."
python3 - "${ENV_FILE}" <<'PY'
import sys
from ipaddress import ip_address, ip_network
from pathlib import Path
from urllib.parse import urlsplit


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[name] = value.strip()
    return values


def is_placeholder(value: str) -> bool:
    normalized = value.casefold()
    return any(
        marker in normalized
        for marker in (
            "change-me",
            "changeme",
            "replace-me",
            "replace-with",
            "replace_with",
            "your-secure",
            "your-distinct",
            "your_resend",
            "64-hex-character",
        )
    )


values = parse_env(Path(sys.argv[1]))
required = (
    "POSTGRES_PASSWORD",
    "DATABASE_URL",
    "JWT_SECRET",
    "SECRET_ENCRYPTION_KEY",
    "RECEIPT_SIGNING_KEY_ID",
    "RECEIPT_SIGNING_PRIVATE_KEY",
    "RECEIPT_TRUSTED_PUBLIC_KEYS",
    "NEXT_PUBLIC_API_URL",
    "NEXT_PUBLIC_SITE_URL",
    "PUBLIC_API_URL",
    "NEXT_PUBLIC_TURNSTILE_SITE_KEY",
    "TURNSTILE_SECRET_KEY",
    "REQUIRE_EMAIL_VERIFICATION",
    "ALLOWED_HOSTS",
    "MUTX_API_HOST",
    "FORWARDED_ALLOW_IPS",
    "MUTX_NETWORK_SUBNET",
)
missing = [name for name in required if not values.get(name)]
if missing:
    for name in missing:
        print(f"❌ Missing required variable in .env.production: {name}", file=sys.stderr)
    raise SystemExit(1)

for name in (
    "POSTGRES_PASSWORD",
    "DATABASE_URL",
    "JWT_SECRET",
    "SECRET_ENCRYPTION_KEY",
    "RECEIPT_SIGNING_PRIVATE_KEY",
    "RECEIPT_TRUSTED_PUBLIC_KEYS",
):
    if is_placeholder(values[name]):
        print(f"❌ Replace the placeholder value for {name} before deployment.", file=sys.stderr)
        raise SystemExit(1)

for name in ("NEXT_PUBLIC_TURNSTILE_SITE_KEY", "TURNSTILE_SECRET_KEY"):
    if is_placeholder(values[name]):
        print(f"❌ Replace the placeholder value for {name} before deployment.", file=sys.stderr)
        raise SystemExit(1)

if len(values["JWT_SECRET"]) < 32 or len(values["SECRET_ENCRYPTION_KEY"]) < 32:
    print("❌ JWT_SECRET and SECRET_ENCRYPTION_KEY must each contain at least 32 characters.", file=sys.stderr)
    raise SystemExit(1)
if values["JWT_SECRET"] == values["SECRET_ENCRYPTION_KEY"]:
    print("❌ JWT_SECRET and SECRET_ENCRYPTION_KEY must be distinct.", file=sys.stderr)
    raise SystemExit(1)

allowed_hosts = [host.strip().lower() for host in values["ALLOWED_HOSTS"].split(",") if host.strip()]
if not allowed_hosts or any("*" in host or host in {"test", "testserver"} for host in allowed_hosts):
    print("❌ ALLOWED_HOSTS must contain exact production API hostnames without wildcards.", file=sys.stderr)
    raise SystemExit(1)

api_host = values["MUTX_API_HOST"].strip().lower().rstrip(".")
try:
    parsed_api_host = urlsplit(f"//{api_host}")
    parsed_api_port = parsed_api_host.port
except ValueError as exc:
    print(f"❌ MUTX_API_HOST must be a valid hostname: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc
if (
    not api_host
    or len(api_host) > 253
    or "*" in api_host
    or parsed_api_host.hostname != api_host
    or parsed_api_port is not None
    or any(
        not label
        or len(label) > 63
        or not label[0].isalnum()
        or not label[-1].isalnum()
        or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in label)
        for label in api_host.split(".")
    )
):
    print("❌ MUTX_API_HOST must be one exact hostname without a scheme, port, or wildcard.", file=sys.stderr)
    raise SystemExit(1)

for url_name in ("PUBLIC_API_URL", "NEXT_PUBLIC_API_URL"):
    try:
        api_url_hostname = (urlsplit(values[url_name]).hostname or "").lower().rstrip(".")
    except ValueError as exc:
        print(f"❌ {url_name} must be a valid URL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    if api_url_hostname != api_host:
        print(f"❌ {url_name} hostname must exactly match MUTX_API_HOST={api_host}.", file=sys.stderr)
        raise SystemExit(1)
if api_host not in allowed_hosts:
    print("❌ ALLOWED_HOSTS must include MUTX_API_HOST.", file=sys.stderr)
    raise SystemExit(1)

try:
    compose_network = ip_network(values["MUTX_NETWORK_SUBNET"], strict=True)
except ValueError as exc:
    print(f"❌ MUTX_NETWORK_SUBNET must be a valid network CIDR: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc
if not compose_network.is_private:
    print("❌ MUTX_NETWORK_SUBNET must use a private address range.", file=sys.stderr)
    raise SystemExit(1)

proxy_entries = [entry.strip() for entry in values["FORWARDED_ALLOW_IPS"].split(",") if entry.strip()]
if not proxy_entries or "*" in proxy_entries:
    print("❌ FORWARDED_ALLOW_IPS must list trusted proxy addresses or CIDRs; '*' is forbidden.", file=sys.stderr)
    raise SystemExit(1)
for entry in proxy_entries:
    try:
        proxy_network = ip_network(entry, strict=False)
    except ValueError as exc:
        print(f"❌ Invalid FORWARDED_ALLOW_IPS entry {entry!r}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    if proxy_network.version != compose_network.version or not proxy_network.subnet_of(compose_network):
        print(
            f"❌ Trusted proxy range {entry} is outside MUTX_NETWORK_SUBNET={compose_network}.",
            file=sys.stderr,
        )
        raise SystemExit(1)

try:
    ip_address(values.get("MUTX_EDGE_BIND_ADDRESS", "0.0.0.0"))
except ValueError as exc:
    print(f"❌ MUTX_EDGE_BIND_ADDRESS must be an IP address: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc

verification_value = values["REQUIRE_EMAIL_VERIFICATION"].casefold()
truthy = {"true", "1", "yes", "on"}
falsey = {"false", "0", "no", "off"}
if verification_value not in truthy | falsey:
    print("❌ REQUIRE_EMAIL_VERIFICATION must be an explicit boolean value.", file=sys.stderr)
    raise SystemExit(1)

if verification_value in truthy:
    resend_key = values.get("RESEND_API_KEY", "")
    resend_ready = bool(resend_key) and not is_placeholder(resend_key)
    smtp_user = values.get("SMTP_USER", "")
    smtp_password = values.get("SMTP_PASSWORD", "")
    smtp_ready = bool(smtp_user and smtp_password) and not is_placeholder(smtp_password)
    if not resend_ready and not smtp_ready:
        print(
            "❌ Email verification requires RESEND_API_KEY or both SMTP_USER and SMTP_PASSWORD.",
            file=sys.stderr,
        )
        raise SystemExit(1)
PY

if [[ "${COMPOSE_PROJECT_NAME}" != "docker" ]]; then
  for volume_variable in MUTX_POSTGRES_VOLUME_NAME MUTX_REDIS_VOLUME_NAME; do
    if [[ -z "${!volume_variable:-}" ]] && ! grep -Eq "^${volume_variable}=.+" "${ENV_FILE}"; then
      echo "❌ Non-legacy COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME} requires an explicit ${volume_variable}." >&2
      echo "This prevents a project-name change from silently selecting empty data volumes." >&2
      exit 1
    fi
  done
fi

echo "🔎 Validating compose configuration..."
"${COMPOSE_CMD[@]}" config --quiet

echo "🔎 Validating nginx and TLS material before changing the stack..."
ssl_dir="$(
  "${COMPOSE_CMD[@]}" config --format json |
    python3 -c '
import json
import sys

config = json.load(sys.stdin)
volumes = config["services"]["nginx"].get("volumes", [])
sources = [
    volume["source"]
    for volume in volumes
    if volume.get("type") == "bind" and volume.get("target") == "/etc/nginx/ssl"
]
if len(sources) != 1:
    raise SystemExit("nginx must have exactly one /etc/nginx/ssl bind mount")
print(sources[0])
'
)"
api_host_port="$(
  "${COMPOSE_CMD[@]}" config --format json |
    python3 -c '
import json
import sys

config = json.load(sys.stdin)
ports = config["services"]["api"].get("ports", [])
matches = [
    port
    for port in ports
    if int(port.get("target", 0)) == 8000
    and port.get("host_ip") == "127.0.0.1"
    and 1 <= int(port.get("published", 0)) <= 65535
]
if len(matches) != 1:
    raise SystemExit("api must publish target 8000 exactly once on 127.0.0.1")
print(matches[0]["published"])
'
)"

nginx_config="${ROOT_DIR}/infrastructure/docker/nginx.prod.conf"
nginx_api_host="$(
  "${COMPOSE_CMD[@]}" config --format json |
    python3 -c '
import json
import sys

config = json.load(sys.stdin)
api_host = config["services"]["nginx"].get("environment", {}).get("MUTX_API_HOST", "")
if not api_host:
    raise SystemExit("nginx MUTX_API_HOST is missing from the rendered Compose config")
print(api_host)
'
)"
rendered_nginx_config="$(mktemp "${TMPDIR:-/tmp}/mutx-nginx-production.XXXXXX")"
cleanup_rendered_nginx_config() {
  rm -f "${rendered_nginx_config}"
}
trap cleanup_rendered_nginx_config EXIT
sed "s/\${MUTX_API_HOST}/${nginx_api_host}/g" "${nginx_config}" >"${rendered_nginx_config}"
if grep -q '\${MUTX_API_HOST}' "${rendered_nginx_config}"; then
  echo "❌ Failed to render MUTX_API_HOST into the nginx production template." >&2
  exit 1
fi
if [[ ! -f "${ssl_dir}/cert.pem" || ! -f "${ssl_dir}/key.pem" ]]; then
  echo "❌ TLS material must contain cert.pem and key.pem in ${ssl_dir}" >&2
  exit 1
fi
bash "${ROOT_DIR}/scripts/verify-production-tls.sh" \
  "${ssl_dir}/cert.pem" \
  "${ssl_dir}/key.pem" \
  "${rendered_nginx_config}"

production_volumes=()
while IFS= read -r volume_name; do
  production_volumes+=("${volume_name}")
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
if [[ "${#production_volumes[@]}" -ne 2 || "${production_volumes[0]}" == "${production_volumes[1]}" ]]; then
  echo "❌ Production PostgreSQL and Redis must use two distinct external volumes." >&2
  exit 1
fi
for volume_name in "${production_volumes[@]}"; do
  if ! docker volume inspect "${volume_name}" >/dev/null 2>&1; then
    echo "❌ Required legacy production volume does not exist: ${volume_name}" >&2
    echo "Refusing to create or initialize an empty replacement volume." >&2
    echo "For a verified first installation, run scripts/bootstrap-production-volumes.sh first." >&2
    exit 1
  fi
done

echo "📦 Pulling latest images..."
"${COMPOSE_CMD[@]}" pull --ignore-buildable

echo "🔎 Verifying legacy production volumes contain initialized data..."
if ! docker run --rm --pull never --read-only --network none \
  --mount "type=volume,src=${production_volumes[0]},dst=/volume,readonly" \
  --entrypoint /bin/sh postgres:16-alpine \
  -eu -c 'test -s /volume/PG_VERSION && test -d /volume/base && test -d /volume/global'; then
  echo "❌ PostgreSQL volume ${production_volumes[0]} is missing initialized cluster data." >&2
  exit 1
fi
if ! docker run --rm --pull never --read-only --network none \
  --mount "type=volume,src=${production_volumes[1]},dst=/volume,readonly" \
  --entrypoint /bin/sh postgres:16-alpine \
  -eu -c 'test -n "$(ls -A /volume)"'; then
  echo "❌ Redis volume ${production_volumes[1]} is empty." >&2
  exit 1
fi

echo "🚀 Deploying production stack..."
"${COMPOSE_CMD[@]}" up -d --build --remove-orphans

echo "🔎 Verifying the migration reached every Alembic head..."
expected_heads="$("${COMPOSE_CMD[@]}" exec -T api alembic heads | awk '{print $1}' | sort)"
database_heads="$("${COMPOSE_CMD[@]}" exec -T api alembic current | awk '/\(head\)/ {print $1}' | sort)"
if [[ -z "${expected_heads}" || "${database_heads}" != "${expected_heads}" ]]; then
  echo "❌ Database revision does not match the checked-in Alembic heads"
  echo "Expected: ${expected_heads:-<none>}"
  echo "Database: ${database_heads:-<none>}"
  exit 1
fi

echo "⏳ Waiting for API health endpoint..."
for i in {1..45}; do
  if health_payload="$(curl -fsS "http://127.0.0.1:${api_host_port}/health" 2>/dev/null)" && \
    python3 -c '
import json
import sys

payload = json.loads(sys.stdin.read())
assert payload.get("status") == "healthy", payload
assert payload.get("database") == "ready", payload
assert payload.get("components", {}).get("database", {}).get("status") == "healthy", payload
' <<<"${health_payload}"; then
    echo "✅ API is healthy"
    break
  fi
  sleep 2
  if [[ $i -eq 45 ]]; then
    echo "❌ API health check failed"
    echo "📄 Last 100 lines of API logs:"
    "${COMPOSE_CMD[@]}" logs --tail 100 migrate api monitor || true
    exit 1
  fi
done

ready_payload="$(curl -fsS "http://127.0.0.1:${api_host_port}/ready")"
python3 -c '
import json
import sys

payload = json.loads(sys.stdin.read())
assert payload.get("status") == "ready", payload
assert payload.get("database") == "ready", payload
' <<<"${ready_payload}"

service_state() {
  local service="$1"
  local service_container
  service_container="$("${COMPOSE_CMD[@]}" ps --quiet "${service}")"
  if [[ -z "${service_container}" ]]; then
    return 1
  fi
  docker inspect --format \
    '{{.Id}}|{{.State.Running}}|{{.State.Restarting}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}|{{.RestartCount}}' \
    "${service_container}"
}

for production_service in postgres redis api monitor frontend nginx; do
  echo "⏳ Waiting for ${production_service} to be running, non-restarting, and healthy..."
  for i in {1..45}; do
    if production_service_snapshot="$(service_state "${production_service}" 2>/dev/null)"; then
      IFS='|' read -r _ service_running service_restarting service_health _ \
        <<<"${production_service_snapshot}"
      if [[ "${service_running}" == "true" && "${service_restarting}" == "false" && "${service_health}" == "healthy" ]]; then
        break
      fi
    fi
    sleep 2
    if [[ $i -eq 45 ]]; then
      echo "❌ ${production_service} never reached its healthy runtime contract." >&2
      "${COMPOSE_CMD[@]}" logs --tail 100 "${production_service}" || true
      exit 1
    fi
  done
done

monitor_snapshot="$(service_state monitor)"
IFS='|' read -r monitor_id _ _ _ monitor_restarts <<<"${monitor_snapshot}"
sleep 12
stable_monitor_snapshot="$(service_state monitor)"
IFS='|' read -r stable_monitor_id stable_monitor_running stable_monitor_restarting \
  stable_monitor_health stable_monitor_restarts <<<"${stable_monitor_snapshot}"
if [[ "${stable_monitor_id}" != "${monitor_id}" || \
  "${stable_monitor_running}" != "true" || \
  "${stable_monitor_restarting}" != "false" || \
  "${stable_monitor_health}" != "healthy" || \
  "${stable_monitor_restarts}" != "${monitor_restarts}" ]]; then
  echo "❌ Monitor worker did not remain healthy and restart-stable for 12 seconds." >&2
  "${COMPOSE_CMD[@]}" logs --tail 100 monitor || true
  exit 1
fi

"${COMPOSE_CMD[@]}" exec -T nginx nginx -t

echo "✅ Production deployment completed"
"${COMPOSE_CMD[@]}" ps
