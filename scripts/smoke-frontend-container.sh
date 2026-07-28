#!/usr/bin/env bash
set -euo pipefail

image_ref="${1:-mutx-frontend:latest}"
container_name="mutx-frontend-smoke-${RANDOM}-$$"

cleanup() {
  docker rm --force "${container_name}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker run --rm --pull never --network none --entrypoint /bin/sh "${image_ref}" -eu -c '
  test -f /app/.next/standalone/server.js
  test -n "$(find /app/.next/standalone/.next/static -type f -print -quit)"
  test -f /app/.next/standalone/public/docs-search-index.json
  test -f /app/docs/index.md
  test -f /app/SUMMARY.md
  test -f /app/security.md
  test -f /app/support.md
  test -f /app/app/fonts/Geist-Regular.ttf
  test ! -e /app/.git
  test ! -e /app/.worktrees
  test ! -e /app/.venv
  test ! -e /app/.env
  test ! -e /app/infrastructure
  test ! -e /app/tests
  test ! -e /app/package-lock.json
  test -z "$(find /app -name .git -print -quit)"
  test -z "$(find /app -name .github -print -quit)"
  test -z "$(find /app -name .worktrees -print -quit)"
  test -z "$(find /app -name .venv -print -quit)"
  test -z "$(find /app -name .env -print -quit)"
  test -z "$(find /app -name .env.local -print -quit)"
  test -z "$(find /app -name .env.production -print -quit)"
  test -z "$(find /app -name .terraform -print -quit)"
  test -z "$(find /app -name .secrets -print -quit)"
  test -z "$(find /app -name \*.tfstate -print -quit)"
'

docker run --detach --name "${container_name}" --pull never --network none \
  --cap-drop ALL --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  "${image_ref}" >/dev/null

for attempt in $(seq 1 30); do
  if docker exec "${container_name}" node -e '
    const http = require("node:http");
    const paths = ["/", "/docs", "/security", "/docs-search-index.json"];
    Promise.all(paths.map((path) => new Promise((resolve, reject) => {
      const request = http.get({ host: "127.0.0.1", port: 3000, path }, (response) => {
        response.resume();
        response.on("end", () => {
          if (response.statusCode >= 200 && response.statusCode < 400) resolve();
          else reject(new Error(`${path} returned ${response.statusCode}`));
        });
      });
      request.setTimeout(2000, () => request.destroy(new Error(`${path} timed out`)));
      request.on("error", reject);
    }))).catch((error) => { console.error(error.message); process.exit(1); });
  ' >/dev/null 2>&1; then
    exit 0
  fi

  if [[ "$(docker inspect --format '{{.State.Running}}' "${container_name}")" != "true" ]]; then
    docker logs "${container_name}" >&2
    exit 1
  fi
  sleep 1
done

docker logs "${container_name}" >&2
echo "Frontend container did not satisfy the standalone HTTP smoke contract." >&2
exit 1
