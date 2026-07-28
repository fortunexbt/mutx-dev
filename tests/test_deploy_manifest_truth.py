from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_railway_api_manifest_uses_real_backend_dockerfile() -> None:
    railway_api = read_text("railway-api.json")

    assert '"dockerfilePath": "infrastructure/docker/Dockerfile.backend"' in railway_api
    assert '"dockerfilePath": "Dockerfile.backend"' not in railway_api


def test_railway_docs_reference_real_backend_dockerfile_paths() -> None:
    railway_docs = read_text("docs/deployment/railway.md")

    assert '"dockerfilePath": "infrastructure/docker/Dockerfile.backend"' in railway_docs
    assert "Create `api/Dockerfile`:" not in railway_docs
    assert '"dockerfilePath": "Dockerfile.backend"' not in railway_docs


def test_production_compose_uses_real_dockerfiles() -> None:
    compose_production = read_text("infrastructure/docker/docker-compose.prod.yml")

    assert "dockerfile: infrastructure/docker/Dockerfile.api.production" in compose_production
    assert "dockerfile: infrastructure/docker/Dockerfile.frontend" in compose_production
    assert "dockerfile: Dockerfile.api" not in compose_production
    assert "dockerfile: Dockerfile.frontend" not in compose_production


def test_production_deploy_scripts_reference_the_checked_in_compose_manifest() -> None:
    deploy_script = read_text("scripts/deploy.sh")
    production_script = read_text("scripts/deploy-production.sh")
    expected_path = "infrastructure/docker/docker-compose.prod.yml"

    assert expected_path in production_script
    assert 'exec bash "${ROOT_DIR}/scripts/deploy-production.sh" "$@"' in deploy_script
    assert not (ROOT / "infrastructure/docker/docker-compose.production.yml").exists()
    assert "docker-compose.production.yml" not in deploy_script
    assert "docker-compose.production.yml" not in production_script


def test_production_environment_example_covers_fail_closed_compose_inputs() -> None:
    environment_example = read_text(".env.production.example")

    for variable in (
        "POSTGRES_PASSWORD",
        "DATABASE_URL",
        "JWT_SECRET",
        "SECRET_ENCRYPTION_KEY",
        "RECEIPT_SIGNING_KEY_ID",
        "RECEIPT_SIGNING_PRIVATE_KEY",
        "RECEIPT_TRUSTED_PUBLIC_KEYS",
        "NEXT_PUBLIC_API_URL",
        "NEXT_PUBLIC_SITE_URL",
    ):
        assert f"{variable}=" in environment_example

    assert "DATABASE_REQUIRED_ON_STARTUP=true" in environment_example
    assert "MUTX_EDGE_BIND_ADDRESS=0.0.0.0" in environment_example
    assert "ALLOWED_HOSTS=api.mutx.dev,api,localhost,127.0.0.1" in environment_example
    assert "MUTX_API_HOST=api.mutx.dev" in environment_example
    assert "FORWARDED_ALLOW_IPS=172.30.40.0/24" in environment_example


def test_production_receipt_signing_contract_reaches_compose_and_preflight() -> None:
    compose = read_text("infrastructure/docker/docker-compose.prod.yml")
    deploy = read_text("scripts/deploy-production.sh")
    smoke = read_text("scripts/smoke-compose-prod.sh")

    for variable in (
        "RECEIPT_SIGNING_KEY_ID",
        "RECEIPT_SIGNING_PRIVATE_KEY",
        "RECEIPT_TRUSTED_PUBLIC_KEYS",
    ):
        assert f"{variable}: ${{{variable}:?" in compose
        assert f'"{variable}"' in deploy
        assert f"export {variable}=" in smoke


def test_production_docker_expands_only_explicit_forwarded_proxy_trust() -> None:
    compose = read_text("infrastructure/docker/docker-compose.prod.yml")
    dockerfile = read_text("infrastructure/docker/Dockerfile.api.production")

    assert "FORWARDED_ALLOW_IPS: ${FORWARDED_ALLOW_IPS:?" in compose
    assert '--forwarded-allow-ips=\\"${FORWARDED_ALLOW_IPS:-127.0.0.1}\\"' in dockerfile
    assert "--forwarded-allow-ips='${FORWARDED_ALLOW_IPS" not in dockerfile
    assert "FORWARDED_ALLOW_IPS=*" not in compose


def test_helm_docs_use_current_values_schema_and_test_command() -> None:
    production_docs = read_text("docs/deployment/production.md")
    kubernetes_docs = read_text("docs/deployment/kubernetes.md")

    for docs in (production_docs, kubernetes_docs):
        assert "api:" in docs
        assert "  env:" in docs
        assert "frontend:" in docs
        assert "api.existingSecret" in docs
        assert "same Secret and database role" in docs or "same `api.existingSecret`" in docs
    assert "helm test mutx-prod --namespace production --logs" in kubernetes_docs
    assert "kubectl apply -f infrastructure/helm/mutx/templates/tests/test-connection.yaml" not in (
        kubernetes_docs
    )
