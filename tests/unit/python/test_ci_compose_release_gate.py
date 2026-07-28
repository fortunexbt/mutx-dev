from __future__ import annotations

from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[3]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def load_yaml(relative_path: str) -> dict[str, object]:
    return yaml.safe_load(read_text(relative_path))


def test_frontend_ci_builds_and_smokes_the_standalone_production_artifact() -> None:
    workflow = load_yaml(".github/workflows/ci.yml")
    frontend = workflow["jobs"]["frontend-validation"]
    steps = frontend["steps"]
    commands = [step.get("run", "") for step in steps]

    assert any("playwright install --with-deps chromium" in command for command in commands)
    browser_command = next(
        command for command in commands if "test-release-browser-contract.sh" in command
    )
    assert browser_command == "bash scripts/test-release-browser-contract.sh all"
    assert "MUTX_GITHUB_RELEASES_TOKEN" not in read_text(".github/workflows/ci.yml")

    release_smoke = read_text("tests/releaseFrontend.spec.ts")
    release_fixture = read_text("tests/release-github-fixture.cjs")
    release_runner = read_text("scripts/test-release-browser-contract.sh")
    for contract in (
        "page.goto('/releases'",
        "page.goto('/download/macos'",
        "request.get('/download/macos/arm64'",
        "page.goto('/docs'",
        "search documentation",
        "page.goto('/dashboard/release-smoke-unknown'",
        'data-boundary-surface="dashboard"',
    ):
        assert contract in release_smoke
    for contract in (
        "@release-fixture-unavailable",
        "@release-fixture-available",
        "MUTX_DESKTOP_RELEASE_FIXTURE",
        "MUTX-9.8.7-macos-arm64.dmg",
    ):
        assert contract in release_smoke
    assert "RELEASES_API_URL" in release_fixture
    assert "originalFetch(input, init)" in release_fixture
    assert "npm run build" in release_runner
    assert "run_lane unavailable" in release_runner
    assert "run_lane available" in release_runner


def test_ci_change_selection_covers_full_product_release_inputs() -> None:
    workflow = load_yaml(".github/workflows/ci.yml")
    changes = workflow["jobs"]["changes"]
    filters = changes["steps"][1]["with"]["filters"]

    for path in (
        ".github/workflows/release.yml",
        ".github/workflows/railway-production-promotion.yml",
        "desktop/**",
        "scripts/**",
        "tests/*.spec.ts",
        "tests/release-github-fixture.cjs",
        "tests/*.py",
        "infrastructure/helm/**",
        "docker-compose*.yml",
        "railway*.json",
    ):
        assert f"- '{path}'" in filters

    assert changes["outputs"]["infrastructure"]
    assert "infrastructure-validation" in workflow["jobs"]
    infrastructure_job = workflow["jobs"]["infrastructure-validation"]
    assert "needs.changes.outputs.infrastructure == 'true'" in infrastructure_job["if"]
    assert any(
        "infrastructure/helm/mutx/tests/test_chart.py" in step.get("run", "")
        for step in infrastructure_job["steps"]
    )

    python_commands = "\n".join(
        step.get("run", "") for step in workflow["jobs"]["python-validation"]["steps"]
    )
    assert "tests/test_*.py" in python_commands


def test_compose_smoke_runs_for_all_release_image_surfaces() -> None:
    workflow = load_yaml(".github/workflows/ci.yml")
    jobs = workflow["jobs"]
    compose_job = jobs["compose-smoke"]
    filters = jobs["changes"]["steps"][1]["with"]["filters"]

    assert compose_job["needs"] == "changes"
    assert "needs.changes.outputs.compose == 'true'" in compose_job["if"]
    for path in (
        "scripts/smoke-compose-prod.sh",
        "scripts/deploy-production.sh",
        "scripts/promote-railway-production.sh",
        "scripts/verify-production-release.sh",
        "scripts/verify-release-http.mjs",
        "docker-compose*.yml",
        "infrastructure/docker/docker-compose.prod.yml",
        "infrastructure/docker/nginx.prod.conf",
        "infrastructure/docker/Dockerfile.api.production",
        "infrastructure/docker/Dockerfile.frontend",
        "app/**",
        "src/api/**",
    ):
        assert f"- '{path}'" in filters


def test_release_gate_contract_test_runs_when_its_sources_change() -> None:
    workflow = load_yaml(".github/workflows/ci.yml")
    filters = workflow["jobs"]["changes"]["steps"][1]["with"]["filters"]

    for path in (
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
        ".github/workflows/railway-production-promotion.yml",
        "scripts/smoke-compose-prod.sh",
        "scripts/verify-release-http.mjs",
        "infrastructure/docker/docker-compose.prod.yml",
    ):
        assert f"- '{path}'" in filters

    python_commands = "\n".join(
        step.get("run", "") for step in workflow["jobs"]["python-validation"]["steps"]
    )
    assert "tests/unit/python" in python_commands


def test_compose_healthchecks_are_exact_and_content_aware() -> None:
    compose = load_yaml("infrastructure/docker/docker-compose.prod.yml")
    services = compose["services"]
    api_healthcheck = " ".join(services["api"]["healthcheck"]["test"])
    frontend_healthcheck = " ".join(services["frontend"]["healthcheck"]["test"])
    nginx_healthcheck = " ".join(services["nginx"]["healthcheck"]["test"])
    postgres_healthcheck = " ".join(services["postgres"]["healthcheck"]["test"])
    monitor_healthcheck = " ".join(services["monitor"]["healthcheck"]["test"])

    assert "response.status == 200" in api_healthcheck
    assert "http.client.HTTPConnection" in api_healthcheck
    assert "payload.get('status') == 'ready'" in api_healthcheck
    assert "payload.get('database') == 'ready'" in api_healthcheck

    assert "verify-release-http.mjs frontend" in frontend_healthcheck
    assert "verify-release-http.mjs health" in frontend_healthcheck
    assert "/api/dashboard/health" in frontend_healthcheck
    assert "statusCode < 500" not in frontend_healthcheck
    assert "curl" not in frontend_healthcheck

    assert "/ready" in nginx_healthcheck
    assert '"status":"ready"' in nginx_healthcheck
    assert '"database":"ready"' in nginx_healthcheck
    assert "$${POSTGRES_PASSWORD}" in postgres_healthcheck
    assert "psql -w" in postgres_healthcheck
    assert "src.api.monitor_worker" in monitor_healthcheck
    assert "--healthcheck" in monitor_healthcheck
    assert "/proc/1/cmdline" not in monitor_healthcheck
    assert services["monitor"]["healthcheck"]["retries"] >= 3


def test_one_isolated_compose_manifest_owns_the_production_contract() -> None:
    compose_path = ROOT / "infrastructure/docker/docker-compose.prod.yml"
    legacy_path = ROOT / "infrastructure/docker/docker-compose.production.yml"
    compose = load_yaml("infrastructure/docker/docker-compose.prod.yml")
    services = compose["services"]

    assert compose_path.is_file()
    assert not legacy_path.exists()
    assert {"postgres", "redis", "migrate", "api", "monitor", "frontend", "nginx"} <= set(services)
    assert "alembic upgrade head" in " ".join(services["migrate"]["command"])
    assert services["monitor"]["command"] == ["python", "-m", "src.api.monitor_worker"]
    assert "127.0.0.1:${MUTX_API_HOST_PORT:-8000}:8000" in services["api"]["ports"]
    assert (
        "${MUTX_EDGE_BIND_ADDRESS:-0.0.0.0}:${MUTX_HTTP_HOST_PORT:-80}:80"
        in services["nginx"]["ports"]
    )
    assert (
        "${MUTX_EDGE_BIND_ADDRESS:-0.0.0.0}:${MUTX_HTTPS_HOST_PORT:-443}:443"
        in services["nginx"]["ports"]
    )
    assert services["nginx"]["environment"]["MUTX_API_HOST"].startswith("${MUTX_API_HOST:?")
    assert any(
        volume.endswith(":/etc/nginx/templates/nginx.conf.template:ro")
        for volume in services["nginx"]["volumes"]
    )
    assert "server_name ${MUTX_API_HOST};" in read_text("infrastructure/docker/nginx.prod.conf")
    assert all("container_name" not in service for service in services.values())
    assert "name" not in compose["networks"]["mutx-network"]
    assert any("MUTX_SSL_DIR" in volume for volume in services["nginx"]["volumes"])
    api_env = compose["x-api-env"]
    assert api_env["DATABASE_SSL_MODE"] == "${DATABASE_SSL_MODE:-disable}"
    for variable in (
        "FRONTEND_URL",
        "PUBLIC_API_URL",
        "AUTH_REDIRECT_ORIGINS",
        "REQUIRE_EMAIL_VERIFICATION",
        "RESEND_API_KEY",
        "RESEND_FROM_EMAIL",
        "SMTP_USER",
        "SMTP_PASSWORD",
        "ALLOWED_HOSTS",
        "FORWARDED_ALLOW_IPS",
        "RECEIPT_SIGNING_KEY_ID",
        "RECEIPT_SIGNING_PRIVATE_KEY",
        "RECEIPT_TRUSTED_PUBLIC_KEYS",
    ):
        assert variable in api_env

    frontend_env = services["frontend"]["environment"]
    for variable in (
        "DATABASE_URL",
        "DATABASE_SSL_MODE",
        "NEXT_PUBLIC_TURNSTILE_SITE_KEY",
        "TURNSTILE_SECRET_KEY",
        "RESEND_API_KEY",
        "RESEND_FROM_EMAIL",
        "RESEND_AUDIENCE_ID",
        "RESEND_WAITLIST_TEMPLATE_ID",
        "RESEND_CONTACT_TEMPLATE_ID",
        "CONTACT_NOTIFY_EMAIL",
        "LEAD_DISCORD_WEBHOOK_URL",
    ):
        assert variable in frontend_env

    production_env = read_text(".env.production.example")
    assert "DATABASE_SSL_MODE=disable" in production_env
    assert "REQUIRE_EMAIL_VERIFICATION=true" in production_env
    assert "AUTH_REDIRECT_ORIGINS=" in production_env
    assert "RESEND_API_KEY=" in production_env
    assert "NEXT_PUBLIC_TURNSTILE_SITE_KEY=" in production_env
    assert "TURNSTILE_SECRET_KEY=" in production_env
    assert "MUTX_POSTGRES_VOLUME_NAME=docker_postgres_data" in production_env
    assert "MUTX_REDIS_VOLUME_NAME=docker_redis_data" in production_env
    assert "MUTX_EDGE_BIND_ADDRESS=0.0.0.0" in production_env
    assert "MUTX_API_HOST=api.mutx.dev" in production_env
    assert "MUTX_NETWORK_SUBNET=" in production_env
    assert "FORWARDED_ALLOW_IPS=" in production_env
    assert compose["networks"]["mutx-network"]["ipam"]["config"] == [
        {"subnet": "${MUTX_NETWORK_SUBNET:?MUTX_NETWORK_SUBNET must be set}"}
    ]
    for required_value in (
        compose["x-api-env"]["DATABASE_URL"],
        compose["x-api-env"]["JWT_SECRET"],
        compose["x-api-env"]["SECRET_ENCRYPTION_KEY"],
        compose["x-api-env"]["RECEIPT_SIGNING_KEY_ID"],
        compose["x-api-env"]["RECEIPT_SIGNING_PRIVATE_KEY"],
        compose["x-api-env"]["RECEIPT_TRUSTED_PUBLIC_KEYS"],
        services["postgres"]["environment"]["POSTGRES_PASSWORD"],
    ):
        assert "must be set" in required_value

    assert compose["volumes"]["postgres_data"] == {
        "name": "${MUTX_POSTGRES_VOLUME_NAME:-docker_postgres_data}",
        "external": True,
    }
    assert compose["volumes"]["redis_data"] == {
        "name": "${MUTX_REDIS_VOLUME_NAME:-docker_redis_data}",
        "external": True,
    }

    for consumer in (
        "scripts/deploy-production.sh",
        "scripts/smoke-compose-prod.sh",
        ".github/workflows/ci.yml",
    ):
        content = read_text(consumer)
        assert "docker-compose.prod.yml" in content
        assert "docker-compose.production.yml" not in content

    deploy_wrapper = read_text("scripts/deploy.sh")
    assert 'exec bash "${ROOT_DIR}/scripts/deploy-production.sh" "$@"' in deploy_wrapper
    assert "docker-compose.production.yml" not in deploy_wrapper


def test_smoke_script_verifies_direct_and_edge_release_behavior() -> None:
    smoke = read_text("scripts/smoke-compose-prod.sh")
    verifier = read_text("scripts/verify-release-http.mjs")

    for contract in (
        "verify_api_contract /health healthy",
        "verify_api_contract /ready ready",
        "verify_frontend_contract",
        "verify_frontend_api_proxy",
        "verify_edge_contract frontend https://nginx/",
        "verify_edge_contract health http://nginx/health",
        "verify_edge_contract ready http://nginx/ready",
        "verify_edge_contract health https://nginx/api/dashboard/health",
        'wait_for_check "monitor worker to record a real monitoring cycle" verify_monitor_activity',
        'wait_for_check "monitor worker container health" verify_monitor_container_health',
        "verify_migration_contract",
        "create_monitor_activity_fixture",
        "INSERT INTO agents",
        "FROM agent_logs",
        "verify_nginx_tls_contract",
        "verify_published_edge_contract",
        "published_port 80",
        "published_port 443",
        "nginx -t",
        "TLSv1.2",
        '-e PGPASSWORD="$POSTGRES_PASSWORD"',
    ):
        assert contract in smoke

    assert "Required prerequisites:" in smoke
    assert "env PGPASSWORD" not in smoke
    assert "SMOKE_TEMP_DIR" in smoke
    assert "COMPOSE_DISABLE_ENV_FILE=1" in smoke
    assert 'export COMPOSE_PROJECT_NAME="mutx-smoke-${smoke_suffix}"' in smoke
    assert "export MUTX_API_HOST_PORT=0" in smoke
    assert "export MUTX_EDGE_BIND_ADDRESS=127.0.0.1" in smoke
    assert 'export FORWARDED_ALLOW_IPS="${MUTX_NETWORK_SUBNET}"' in smoke
    assert "export MUTX_API_HOST=api.invalid.test" in smoke
    assert "https://api.invalid.test:${https_port}/health" in smoke
    assert "docker volume create" in smoke
    assert 'docker compose -f "$COMPOSE_FILE" down -v' not in smoke
    assert "${COMPOSE_PROJECT_NAME:-" not in smoke
    assert "${POSTGRES_PASSWORD:-" not in smoke
    assert 'SSL_DIR="$ROOT_DIR/infrastructure/docker/ssl"' not in smoke
    assert "response.status !== 200" in verifier
    assert "_next\\/static" in verifier
    assert "FRONTEND_MARKER" in verifier
    assert "payload.status !== 'healthy'" in verifier
    assert "payload.status !== 'ready'" in verifier


def test_production_deploy_preflights_tls_before_any_stack_change() -> None:
    deploy = read_text("scripts/deploy-production.sh")
    environment_validator = deploy.split(
        'echo "🔎 Validating required environment variables..."\n', 1
    )[1].split("\nPY\n", 1)[0]

    preflight_index = deploy.index("Validating nginx and TLS material")
    pull_index = deploy.index("pull --ignore-buildable")
    up_index = deploy.index("up -d --build --remove-orphans")

    assert preflight_index < pull_index < up_index
    assert "config --format json" in deploy
    assert 'target") == "/etc/nginx/ssl"' in deploy
    assert 'port.get("host_ip") == "127.0.0.1"' in deploy
    assert "http://127.0.0.1:${api_host_port}/health" in deploy
    assert "verify-production-tls.sh" in deploy
    assert 'sed "s/\\${MUTX_API_HOST}/${nginx_api_host}/g"' in deploy
    assert "trap cleanup_rendered_nginx_config EXIT" in deploy
    assert 'COMPOSE_PROJECT_NAME="${file_project_name:-docker}"' in deploy
    assert 'inherited_project_name="${COMPOSE_PROJECT_NAME:-}"' in deploy
    assert "docker volume inspect" in deploy
    assert "Refusing to create or initialize an empty replacement volume" in deploy
    assert "bootstrap-production-volumes.sh" in deploy
    assert 'verification_value = values["REQUIRE_EMAIL_VERIFICATION"].casefold()' in deploy
    assert "Email verification requires RESEND_API_KEY" in deploy
    assert "JWT_SECRET and SECRET_ENCRYPTION_KEY must be distinct" in deploy
    assert "Replace the placeholder value" in deploy
    assert "from ipaddress import ip_address, ip_network" in environment_validator
    assert "from urllib.parse import urlsplit" in environment_validator
    assert 'for url_name in ("PUBLIC_API_URL", "NEXT_PUBLIC_API_URL")' in environment_validator
    assert "ALLOWED_HOSTS must include MUTX_API_HOST" in environment_validator
    assert "PG_VERSION" in deploy
    assert "for production_service in postgres redis api monitor frontend nginx" in deploy
    assert "never reached its healthy runtime contract" in deploy
    assert "Monitor worker did not remain healthy and restart-stable" in deploy

    tls_verifier = read_text("scripts/verify-production-tls.sh")
    for contract in (
        "minimum_validity_seconds=1209600",
        "-checkhost",
        "-verify_hostname",
        "-purpose sslserver",
        "notBefore",
        "ca_file",
    ):
        assert contract in tls_verifier


def test_railway_workflow_promotes_only_after_fail_closed_validation() -> None:
    workflow_text = read_text(".github/workflows/railway-production-promotion.yml")
    workflow = load_yaml(".github/workflows/railway-production-promotion.yml")
    promote_script = read_text("scripts/promote-railway-production.sh")
    verify_script = read_text("scripts/verify-production-release.sh")
    verifier = read_text("scripts/verify-release-http.mjs")

    validate_index = workflow_text.index("Validate release inputs")
    promote_index = workflow_text.index("bash scripts/promote-railway-production.sh")
    verify_index = workflow_text.index("bash scripts/verify-production-release.sh")
    assert validate_index < promote_index < verify_index
    assert "workflow_dispatch:" not in workflow_text
    assert "DIRECT_DISPATCH_RELEASE_TAG" not in workflow_text
    assert "confirm_production" not in workflow_text
    assert "environment: production" in workflow_text
    assert "fetch-depth: 0" in workflow_text
    assert "ref: ${{ inputs.target_commit }}" in workflow_text
    assert workflow["jobs"]["promote"]["steps"][0]["with"]["persist-credentials"] is False
    assert "target_commit" in workflow_text
    assert "validate-release-version.sh" in workflow_text
    assert "published stable GitHub release" in workflow_text
    assert workflow["concurrency"] == {
        "group": "railway-production-promotion",
        "cancel-in-progress": False,
    }
    for secret in (
        "RAILWAY_TOKEN",
        "RAILWAY_PROJECT_ID",
        "RAILWAY_FRONTEND_SERVICE_ID",
        "RAILWAY_API_SERVICE_ID",
        "RAILWAY_ENVIRONMENT_ID",
    ):
        assert secret in workflow_text

    steps = workflow["jobs"]["promote"]["steps"]
    railway_install = next(
        step for step in steps if step.get("name") == "Install checksum-verified Railway CLI"
    )
    assert railway_install["env"]["RAILWAY_CLI_VERSION"] == "5.30.1"
    assert (
        railway_install["env"]["RAILWAY_CLI_SHA256"]
        == "c6169e27e87d95d73fb7a30ec2c6b6c767c042f8a3ba9aa98c92deccda8db10c"
    )
    assert "sha256sum --check" in railway_install["run"]
    assert "npm install" not in railway_install["run"]
    assert "reviewed_railway_cli_version" in promote_script
    assert "railway up" in promote_script
    assert "--ci" in promote_script
    version_guard_index = promote_script.index("node scripts/check-production-version.cjs")
    api_deploy_index = promote_script.index('deploy_service "${RAILWAY_API_SERVICE_ID}"')
    assert version_guard_index < api_deploy_index
    assert promote_script.index(
        'deploy_service "${RAILWAY_API_SERVICE_ID}"'
    ) < promote_script.index('deploy_service "${RAILWAY_FRONTEND_SERVICE_ID}"')
    assert "public/mutx-release.json" in promote_script
    assert "src/api/mutx-release.json" in promote_script
    assert 'wait_for_release_identity "API"' in promote_script
    assert 'wait_for_release_identity "frontend"' in promote_script
    assert "git rev-list" in promote_script
    assert "RELEASE_SHA" in promote_script
    assert "validated_version" in promote_script

    release_workflow = read_text(".github/workflows/release.yml")
    assert "Refusing to move an already-published release back to draft" in release_workflow
    assert "remote_asset_names" in release_workflow
    assert "promote_production == 'true'" in release_workflow
    assert release_workflow.count("secrets: inherit") == 2

    assert 'verify-release-http.mjs" release' in verify_script
    assert 'wait_for_release_identity "API"' in verify_script
    assert 'wait_for_release_identity "frontend"' in verify_script
    assert "expected_sha=${RELEASE_SHA}" in verify_script
    assert "seq 1 60" in verify_script
    assert "Example MUTX governed deployment record" in verify_script
    assert 'verify-release-http.mjs" health' in verify_script
    assert 'verify-release-http.mjs" ready' in verify_script
    assert "payload[key] !== value" in verifier
    assert "unexpected release identity shape" in verifier


def test_deployment_shell_and_workflow_syntax() -> None:
    for script in (
        "scripts/bootstrap-production-volumes.sh",
        "scripts/deploy-production.sh",
        "scripts/deploy.sh",
        "scripts/promote-railway-production.sh",
        "scripts/verify-production-release.sh",
        "scripts/smoke-compose-prod.sh",
        "scripts/verify-production-tls.sh",
        "scripts/validate-release-version.sh",
        "scripts/resolve-release-target.sh",
        "scripts/test-release-browser-contract.sh",
    ):
        subprocess.run(["bash", "-n", str(ROOT / script)], check=True)

    for workflow in (
        ".github/workflows/ci-health.yml",
        ".github/workflows/ci.yml",
        ".github/workflows/infrastructure-drift.yml",
        ".github/workflows/railway-production-promotion.yml",
        ".github/workflows/release.yml",
    ):
        assert load_yaml(workflow)["jobs"]
